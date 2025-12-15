"""SDE Client for managing SDE downloads and change detection.

Handles:
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import zipfile
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from utils.exceptions import SDEDownloadError
from utils.progress_callback import ProgressCallback, ProgressPhase, ProgressUpdate

if TYPE_CHECKING:
    from utils.config import Config

logger = logging.getLogger(__name__)


# Tables we care about for change detection
CARED_TABLES = {
    "types",
    "invTypes",
    "groups",
    "invGroups",
    "categories",
    "invCategories",
    "marketGroups",
    "invMarketGroups",
    "blueprints",
    "industryActivityMaterials",
    "industryActivityProducts",
    "npcStations",
    "stations",
    "regions",
    "constellations",
    "solarSystems",
}


class SDEBuildMetadata:
    """Metadata about an SDE build."""

    def __init__(
        self,
        build_id: str,
        version: str | None = None,
        checksum: str | None = None,
        applied_at: str | None = None,
        source: str = "rift",
    ):
        self.build_id = build_id
        self.version = version
        self.checksum = checksum
        self.applied_at = applied_at or datetime.now(UTC).isoformat()
        self.source = source

    def to_dict(self) -> dict[str, Any]:
        return {
            "build_id": self.build_id,
            "version": self.version,
            "checksum": self.checksum,
            "applied_at": self.applied_at,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SDEBuildMetadata:
        return cls(
            build_id=data["build_id"],
            version=data.get("version"),
            checksum=data.get("checksum"),
            applied_at=data.get("applied_at"),
            source=data.get("source", "rift"),
        )


class SDEClient:
    """Client for SDE downloads and change management."""

    def __init__(
        self,
        config: Config,
        progress_callback: ProgressCallback | None = None,
    ):
        self.config = config
        self.progress_callback = progress_callback
        self.sde_dir = config.sde.sde_dir_path
        self.metadata_file = config.app.user_data_dir / "sde_build_metadata.json"

        # Ensure directories exist
        self.sde_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file.parent.mkdir(parents=True, exist_ok=True)

    def _emit_progress(
        self,
        phase: ProgressPhase,
        current: int,
        total: int,
        message: str,
        detail: str | None = None,
    ) -> None:
        """Emit progress update if callback is configured."""
        if self.progress_callback:
            update = ProgressUpdate(
                operation="sde_update",
                character_id=None,
                phase=phase,
                current=current,
                total=total,
                message=message,
                detail=detail,
            )
            self.progress_callback(update)

    def load_metadata(self) -> SDEBuildMetadata | None:
        """Load the last applied SDE build metadata.

        Returns:
            SDEBuildMetadata if available, None otherwise.
        """
        if not self.metadata_file.exists():
            return None

        try:
            with open(self.metadata_file, encoding="utf-8") as f:
                data = json.load(f)
            return SDEBuildMetadata.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load SDE metadata: {e}")
            return None

    def save_metadata(self, metadata: SDEBuildMetadata) -> None:
        """Save SDE build metadata.

        Args:
            metadata: Build metadata to persist.
        """
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata.to_dict(), f, indent=2)
            logger.info(f"Saved SDE metadata: build {metadata.build_id}")
        except Exception as e:
            logger.error(f"Failed to save SDE metadata: {e}")

    async def check_for_updates(self) -> tuple[bool, str | None]:
        """Check if SDE updates are available.

        Returns:
            Tuple of (update_available, latest_build_id).
        """
        current_metadata = self.load_metadata()
        current_build = current_metadata.build_id if current_metadata else None

        # Check if SDE files actually exist in the directory
        sde_files = list(self.sde_dir.glob("*.jsonl"))
        sde_files_exist = len(sde_files) > 0

        try:
            latest_build = await self._fetch_latest_build_id()

            # SDE needs update if:
            # 1. No metadata exists (never downloaded), OR
            # 2. Build ID doesn't match latest, OR
            # 3. Metadata exists but SDE files are missing (corrupted/deleted)
            needs_update = (
                current_build is None
                or latest_build != current_build
                or (current_build and not sde_files_exist)
            )

            if needs_update:
                if not sde_files_exist and current_build:
                    logger.warning(
                        f"SDE files missing for build {current_build}; "
                        f"will download {latest_build}"
                    )
                else:
                    logger.info(
                        f"SDE update available: {current_build} -> {latest_build}"
                    )
            else:
                logger.debug(f"SDE is up to date: {current_build}")

            return needs_update, latest_build if needs_update else None
        except Exception as e:
            logger.error(f"Failed to check for SDE updates: {e}")
            # If we can't check, but SDE files are missing, trigger a download
            if not sde_files_exist:
                logger.warning("Could not check SDE updates and SDE files are missing")
                return True, None
            return False, None

    async def _fetch_latest_build_id(self) -> str:
        """Fetch the latest SDE build ID from CCP (via config)."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await self._retry_request(
                    client, "GET", self.config.sde.ccp_latest_url, max_retries=3
                )
                response.raise_for_status()
                for line in response.text.strip().split("\n"):
                    if line:
                        data = json.loads(line)
                        if data.get("_key") == "sde":
                            build_number = data.get("buildNumber")
                            if build_number:
                                return str(build_number)
                raise SDEDownloadError("No SDE build number found in latest.jsonl")
            except Exception as e:
                raise SDEDownloadError(f"Failed to fetch latest build: {e}") from e

    async def download_sde(self, build_id: str | None = None) -> bool:
        """Download SDE files from RIFT enhanced source (always use RIFT for download)."""
        try:
            self._emit_progress(
                ProgressPhase.STARTING, 0, 100, "Starting SDE download..."
            )
            if build_id is None:
                build_id = await self._fetch_latest_build_id()
            logger.info(f"Downloading SDE build: {build_id} from RIFT")
            await self._download_rift_sde(build_id)
            metadata = SDEBuildMetadata(
                build_id=build_id,
                version=build_id,
                source="rift",
            )
            self.save_metadata(metadata)
            self._emit_progress(
                ProgressPhase.COMPLETE, 100, 100, f"SDE {build_id} downloaded"
            )
            return True
        except Exception as e:
            logger.error(f"SDE download failed: {e}")
            self._emit_progress(ProgressPhase.ERROR, 0, 100, f"Download failed: {e}")
            return False

    async def _download_rift_sde(self, build_id: str) -> None:
        """Download SDE files from RIFT enhanced source."""
        download_url = self.config.sde.rift_download_url_template.format(
            build_id=build_id
        )
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                self._emit_progress(
                    ProgressPhase.FETCHING,
                    0,
                    100,
                    "Downloading SDE archive...",
                )

                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    total_bytes = int(response.headers.get("Content-Length", 0))
                    downloaded_bytes = 0
                    archive_bytes = bytearray()

                    async for chunk in response.aiter_bytes(64 * 1024):
                        archive_bytes.extend(chunk)
                        downloaded_bytes += len(chunk)
                        progress = (
                            int(downloaded_bytes * 100 / total_bytes)
                            if total_bytes > 0
                            else 0
                        )
                        detail = (
                            f"{downloaded_bytes / (1024 * 1024):.1f}/{total_bytes / (1024 * 1024):.1f} MB"
                            if total_bytes > 0
                            else f"{downloaded_bytes / (1024 * 1024):.1f} MB"
                        )
                        self._emit_progress(
                            ProgressPhase.FETCHING,
                            min(progress, 100),
                            100,
                            "Downloading SDE archive...",
                            detail=detail,
                        )

                archive_bytes = bytes(archive_bytes)
                total_size_mb = len(archive_bytes) / (1024 * 1024)

                self._emit_progress(
                    ProgressPhase.PROCESSING,
                    50,
                    100,
                    f"Extracting SDE files... ({total_size_mb:.1f} MB)",
                )
                with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                    members = [m for m in zf.namelist() if m.endswith(".jsonl")]
                    total = len(members)
                    extracted_size_mb = 0
                    for idx, member in enumerate(members):
                        file_data = zf.read(member)
                        extracted_size_mb += len(file_data) / (1024 * 1024)
                        output_path = self.sde_dir / member.split("/")[-1]
                        temp_path = output_path.with_suffix(".tmp")
                        temp_path.write_bytes(file_data)
                        temp_path.replace(output_path)
                        if (idx + 1) % 5 == 0:
                            progress = 50 + int((idx + 1) / total * 40)
                            self._emit_progress(
                                ProgressPhase.PROCESSING,
                                progress,
                                100,
                                f"Extracted {idx + 1}/{total} files... ({extracted_size_mb:.1f}/{total_size_mb:.1f} MB)",
                            )
                logger.info(
                    f"Extracted {len(members)} SDE files ({extracted_size_mb:.1f} MB)"
                )
            except Exception as e:
                raise SDEDownloadError(f"Failed to download/extract SDE: {e}") from e

    async def _retry_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make HTTP request with retry logic for rate limits and server errors.

        Args:
            client: HTTP client to use.
            method: HTTP method (GET, POST, etc).
            url: URL to request.
            max_retries: Maximum retry attempts.
            **kwargs: Additional arguments for request.

        Returns:
            HTTP response.

        Raises:
            SDEDownloadError: If all retries fail.
        """
        delay = 1.0
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                response = await client.request(method, url, **kwargs)

                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", delay))
                    logger.warning(
                        f"Rate limited (429), retrying after {retry_after}s..."
                    )
                    await asyncio.sleep(retry_after)
                    delay = min(delay * 2, 60)
                    continue

                # Handle server errors (5xx)
                if 500 <= response.status_code < 600:
                    logger.warning(
                        f"Server error ({response.status_code}), retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
                    continue

                # Success or client error (4xx other than 429)
                return response

            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)

        raise SDEDownloadError(
            f"Request failed after {max_retries} retries: {last_error}"
        ) from last_error

    async def scan_changes(self, from_build: str, to_build: str) -> set[str]:
        """Scan SDE changes between builds to determine if update is needed.

        Iterates backwards through change feeds from to_build until from_build,
        checking if any tables we care about have changed.

        Args:
            from_build: Current build ID.
            to_build: Target build ID.

        Returns:
            Set of changed table names that we care about.
        """
        logger.info(f"Scanning changes from build {from_build} to {to_build}")

        if from_build == to_build:
            return set()

        changed_tables: set[str] = set()
        current_build = int(to_build)
        target_build = int(from_build)

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Iterate backwards through change feeds
            while current_build > target_build:
                try:
                    changes_url = self.config.sde.ccp_changes_url_template.format(
                        build_id=current_build
                    )
                    response = await self._retry_request(
                        client, "GET", changes_url, max_retries=3
                    )
                    response.raise_for_status()

                    # Parse JSONL change feed
                    meta_found = False
                    next_build = None

                    for line in response.text.strip().split("\n"):
                        if not line:
                            continue

                        data = json.loads(line)
                        key = data.get("_key")

                        # First line should be metadata
                        if key == "_meta":
                            meta_found = True
                            last_build = data.get("lastBuildNumber")
                            if last_build:
                                next_build = last_build
                        elif key in CARED_TABLES:
                            # This table changed and we care about it
                            has_changes = (
                                data.get("added")
                                or data.get("removed")
                                or data.get("changed")
                            )
                            if has_changes:
                                changed_tables.add(key)
                                logger.debug(
                                    f"Build {current_build}: {key} changed "
                                    f"(+{len(data.get('added', []))} "
                                    f"-{len(data.get('removed', []))} "
                                    f"~{len(data.get('changed', []))})"
                                )

                    if not meta_found:
                        logger.warning(
                            f"No metadata found in changes for build {current_build}"
                        )
                        break

                    # Move to previous build
                    if next_build and int(next_build) >= target_build:
                        current_build = int(next_build)
                    else:
                        break

                except Exception as e:
                    logger.error(
                        f"Failed to fetch changes for build {current_build}: {e}"
                    )
                    # If we can't fetch changes, assume everything changed to be safe
                    return CARED_TABLES

        logger.info(
            f"Found {len(changed_tables)} changed tables we care about: "
            f"{', '.join(sorted(changed_tables))}"
        )
        return changed_tables

    def should_apply_build(self, changed_tables: set[str]) -> bool:
        """Determine if a build should be applied based on changed tables.

        Args:
            changed_tables: Set of tables that changed in the build.

        Returns:
            True if the build affects tables we care about.
        """
        return bool(changed_tables & CARED_TABLES)
