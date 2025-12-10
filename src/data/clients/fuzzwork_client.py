"""Single-file Fuzzwork market data client.

This module consolidates the previous client/cache implementation into a
single `FuzzworkClient` that stores CSV and simple metadata (no separate
cache class). Behavior:

- Stores CSV at <cache_dir>/aggregatecsv.csv and metadata at metadata.json
- Uses `last_modified` (ISO datetime in metadata) to determine whether to
  check the remote ETag. Only attempts an ETag check 31 minutes after the
  recorded `last_modified` time. If a check is requested but the last ETag
  check happened less than 5 minutes ago, the client will avoid another
  remote request and report that the local copy will be used.
- If ETag differs, the client downloads fresh CSV and updates metadata.
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from utils import global_config
from utils.progress_callback import ProgressCallback, ProgressPhase, ProgressUpdate

logger = logging.getLogger(__name__)

# Constants
AGGREGATE_CSV_URL = "https://market.fuzzwork.co.uk/aggregatecsv.csv.gz"
DEFAULT_CACHE_VALIDITY_MINUTES = 30
ETAG_WAIT_MINUTES = 31
MIN_FETCH_INTERVAL_SECONDS = 5 * 60  # 5 minutes between ETag fetches
HTTP_TIMEOUT = 30.0


class FuzzworkClient:
    """Simple async client for Fuzzwork aggregate CSV with metadata baked-in.

    The client stores files under `cache_dir` (defaults to
    `global_config.app.user_data_dir / "fuzzwork"`). CSV and metadata are
    persisted so the client can operate across restarts.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        cache_validity_minutes: int = DEFAULT_CACHE_VALIDITY_MINUTES,
        request_timeout: float = HTTP_TIMEOUT,
    ) -> None:
        self.request_timeout = request_timeout
        self.cache_validity_minutes = cache_validity_minutes

        if cache_dir is None:
            cache_dir = global_config.app.user_data_dir / "fuzzwork"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.csv_path = self.cache_dir / "aggregatecsv.csv"
        self.metadata_path = self.cache_dir / "metadata.json"

        self._http_client: httpx.AsyncClient | None = None

    def get_cache_metadata(self) -> dict[str, Any] | None:
        """Return cached metadata (if present)."""
        return self._read_metadata()

    def clear_cache(self) -> None:
        """Remove stored CSV and metadata."""
        try:
            if self.csv_path.exists():
                self.csv_path.unlink()
            if self.metadata_path.exists():
                self.metadata_path.unlink()
            logger.info("Fuzzwork client cache cleared (CSV and ETag metadata removed)")
        except Exception as e:
            logger.warning("Failed to clear files: %s", e)

    async def fetch_aggregate_csv(
        self,
        force: bool = False,
        check_etag: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> str:
        """Fetch aggregate CSV data respecting metadata timing rules.

        Rules implemented:
        - If local CSV exists and not forced, normally use it.
        - Only perform a remote ETag check when the current time is at least
          31 minutes past the recorded `last_modified` time (if present);
          otherwise, return local CSV immediately.
        - If past the 31-minute boundary and an ETag check is requested,
          ensure at least 5 minutes have passed since the last ETag check to
          avoid frequent remote checks.
        - If ETag differs, download fresh content.

        Args:
            force: If True, download fresh CSV regardless of cache.
            check_etag: If True, perform ETag check when cache is old.
            progress_callback: Optional callback to report progress updates.
        """
        self._initialize_http_client()

        # If no local file or forced -> download
        local_csv = self._read_csv()
        metadata = self._read_metadata() or {}

        if force or local_csv is None:
            return await self._download_and_save(progress_callback)

        # We have a local file. Determine whether to check ETag based on last_modified
        last_modified_iso = metadata.get("last_modified")

        if last_modified_iso:
            try:
                last_modified_dt = datetime.fromisoformat(last_modified_iso)
                if last_modified_dt.tzinfo is None:
                    last_modified_dt = last_modified_dt.replace(tzinfo=UTC)
            except Exception:
                # If parsing fails, fall back to last_updated
                try:
                    last_updated_iso = metadata.get("last_updated")
                    last_modified_dt = (
                        datetime.fromisoformat(last_updated_iso)
                        if last_updated_iso
                        else datetime.now(UTC)
                    )
                except Exception:
                    last_modified_dt = datetime.now(UTC)
        else:
            # No last_modified header stored; use last_updated as fallback
            try:
                last_updated_iso = metadata.get("last_updated")
                last_modified_dt = (
                    datetime.fromisoformat(last_updated_iso)
                    if last_updated_iso
                    else datetime.now(UTC)
                )
                if last_modified_dt.tzinfo is None:
                    last_modified_dt = last_modified_dt.replace(tzinfo=UTC)
            except Exception:
                last_modified_dt = datetime.now(UTC)

        now = datetime.now(UTC)

        # If it's been less than ETAG_WAIT_MINUTES after last_modified, use local copy
        if now <= last_modified_dt + timedelta(minutes=ETAG_WAIT_MINUTES):
            logger.debug(
                "Local CSV considered fresh based on last_modified; using cached copy"
            )
            return local_csv

        # We are beyond the 31-minute window; consider ETag check if requested
        if not check_etag:
            logger.debug("ETag check not requested; using local CSV")
            return local_csv

        # Throttle HEAD checks to be at least MIN_FETCH_INTERVAL_SECONDS apart
        last_checked_iso = metadata.get("last_checked")
        if last_checked_iso:
            try:
                last_checked_dt = datetime.fromisoformat(last_checked_iso)
                if last_checked_dt.tzinfo is None:
                    last_checked_dt = last_checked_dt.replace(tzinfo=UTC)
            except Exception:
                last_checked_dt = datetime.now(UTC) - timedelta(
                    seconds=MIN_FETCH_INTERVAL_SECONDS + 1
                )
        else:
            last_checked_dt = datetime.now(UTC) - timedelta(
                seconds=MIN_FETCH_INTERVAL_SECONDS + 1
            )

        if now <= last_checked_dt + timedelta(seconds=MIN_FETCH_INTERVAL_SECONDS):
            logger.debug(
                "Recent ETag check performed %.1fs ago; using cached copy",
                (now - last_checked_dt).total_seconds(),
            )
            return local_csv

        # Perform HEAD to get ETag
        try:
            assert self._http_client is not None
            head_resp = await self._http_client.head(AGGREGATE_CSV_URL)
            head_resp.raise_for_status()
            remote_etag = head_resp.headers.get("etag")
        except Exception as e:
            logger.debug(
                "Failed to perform ETag HEAD request: %s; using cached copy", e
            )
            # Update last_checked to avoid rapid retries
            metadata["last_checked"] = now.isoformat()
            self._write_metadata(metadata)
            return local_csv

        # Update last_checked timestamp
        metadata["last_checked"] = now.isoformat()

        cached_etag = metadata.get("etag")
        if not cached_etag:
            # Case (a): Cached ETag is missing (first time or cleared)
            logger.info(
                "ETag not previously cached (first download or cache cleared); "
                "downloading fresh CSV"
            )
            metadata["etag_present"] = False
            return await self._download_and_save(progress_callback)
        if remote_etag and remote_etag != cached_etag:
            # Case (b): Remote ETag differs from cached ETag - data was updated
            logger.info(
                "Remote ETag changed from '%s' to '%s'; downloading fresh CSV",
                cached_etag,
                remote_etag,
            )
            metadata["etag_present"] = True
            return await self._download_and_save(progress_callback)
        if remote_etag and remote_etag == cached_etag:
            # ETag match - use cached copy
            logger.info("ETag match (%s) - using cached CSV", remote_etag)
            metadata["etag_present"] = True
            self._write_metadata(metadata)
            return local_csv
        # Remote ETag missing but we have a cached one - use cached
        logger.debug(
            "Remote ETag missing but cached copy available (cached: %s); "
            "using cached CSV",
            cached_etag,
        )
        metadata["etag_present"] = True
        self._write_metadata(metadata)
        return local_csv

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()

    def _initialize_http_client(self) -> None:
        if self._http_client is not None:
            return
        headers = {"User-Agent": global_config.app.computed_user_agent}
        self._http_client = httpx.AsyncClient(
            timeout=self.request_timeout, headers=headers
        )

    def _read_metadata(self) -> dict[str, Any] | None:
        if not self.metadata_path.exists():
            return None
        try:
            return json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug("Failed to read metadata: %s", e)
            return None

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        try:
            self.metadata_path.write_text(
                json.dumps(metadata, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning("Failed to write metadata: %s", e)

    def _read_csv(self) -> str | None:
        if not self.csv_path.exists():
            return None
        try:
            return self.csv_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.debug("Failed to read cached CSV: %s", e)
            return None

    def _write_csv(self, csv_text: str) -> None:
        try:
            self.csv_path.write_text(csv_text, encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to write CSV file: %s", e)

    async def _download_and_save(
        self, progress_callback: ProgressCallback | None = None
    ) -> str:
        """Download the gzipped CSV, decompress, save and update metadata.

        Args:
            progress_callback: Optional callback to report progress updates.
        """
        self._initialize_http_client()
        assert self._http_client is not None

        # Progress: Starting
        if progress_callback:
            progress_callback(
                ProgressUpdate(
                    operation="Fuzzwork CSV Download",
                    character_id=None,
                    phase=ProgressPhase.STARTING,
                    current=0,
                    total=0,
                    message="Connecting to Fuzzwork server...",
                )
            )

        # Progress: Fetching/Downloading
        if progress_callback:
            progress_callback(
                ProgressUpdate(
                    operation="Fuzzwork CSV Download",
                    character_id=None,
                    phase=ProgressPhase.FETCHING,
                    current=0,
                    total=0,
                    message="Downloading compressed CSV...",
                )
            )

        resp = await self._http_client.get(AGGREGATE_CSV_URL)
        resp.raise_for_status()

        # Progress: Processing/Decompressing
        if progress_callback:
            progress_callback(
                ProgressUpdate(
                    operation="Fuzzwork CSV Download",
                    character_id=None,
                    phase=ProgressPhase.PROCESSING,
                    current=0,
                    total=0,
                    message="Decompressing CSV data...",
                    detail=f"Downloaded {len(resp.content)} bytes",
                )
            )

        # Decompress
        csv_bytes = gzip.decompress(resp.content)
        csv_text = csv_bytes.decode("utf-8")

        # Parse Last-Modified into ISO if present
        last_modified_raw = resp.headers.get("last-modified")
        last_modified_iso = None
        if last_modified_raw:
            try:
                dt = parsedate_to_datetime(last_modified_raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                last_modified_iso = dt.astimezone(UTC).isoformat()
            except Exception:
                last_modified_iso = None

        # Progress: Saving
        if progress_callback:
            progress_callback(
                ProgressUpdate(
                    operation="Fuzzwork CSV Download",
                    character_id=None,
                    phase=ProgressPhase.SAVING,
                    current=0,
                    total=0,
                    message="Saving CSV to cache...",
                    detail=f"Decompressed size: {len(csv_text.encode('utf-8'))} bytes",
                )
            )

        metadata = {
            "last_updated": datetime.now(UTC).isoformat(),
            "last_checked": datetime.now(UTC).isoformat(),
            "etag": resp.headers.get("etag"),
            "last_modified": last_modified_iso,
            "file_size": len(csv_text.encode("utf-8")),
        }

        # Persist
        self._write_csv(csv_text)
        self._write_metadata(metadata)

        logger.info(
            "Downloaded and cached fresh fuzzwork CSV (%d bytes)", metadata["file_size"]
        )

        # Progress: Complete
        if progress_callback:
            progress_callback(
                ProgressUpdate(
                    operation="Fuzzwork CSV Download",
                    character_id=None,
                    phase=ProgressPhase.COMPLETE,
                    current=1,
                    total=1,
                    message="CSV download complete",
                    detail=f"Saved {metadata['file_size']} bytes",
                )
            )

        return csv_text
