"""Main ESI client with caching, rate limiting, and authentication."""

import asyncio
import inspect
import json
import logging
import os
import re
import tempfile
import warnings
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from aiopenapi3 import OpenAPI

from utils import global_config

from .auth import ESIAuth
from .cache import ESICache
from .endpoints import (
    AssetsEndpoints,
    CharacterEndpoints,
    ContractsEndpoints,
    CorporationEndpoints,
    IndustryEndpoints,
    LocationEndpoints,
    MarketEndpoints,
    SkillsEndpoints,
    UniverseEndpoints,
    WalletEndpoints,
)
from .rate_limit import RateLimitTracker

# Configure logger for ESI client
logger = logging.getLogger(__name__)

# Constants
HTTP_TIMEOUT = 30.0
OPENAPI_LOAD_TIMEOUT = 60.0
MAX_LOAD_ATTEMPTS = 2
MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 2
HTTP_STATUS_NOT_MODIFIED = 304
HTTP_STATUS_UNAUTHORIZED = 401
HTTP_STATUS_TOO_MANY_REQUESTS = 429
SERVER_ERROR_CODES = frozenset({500, 502, 503, 504})


def _load_openapi_blocking(url_or_path: str) -> OpenAPI:
    """Blocking helper to load OpenAPI spec inside a worker thread.

    Runs an independent event loop in the thread because aiopenapi3
    provides an async loader. This returns the parsed OpenAPI object.

    Args:
        url_or_path: URL (http/https) or local file path to load from

    Raises:
        Exception: If OpenAPI spec cannot be loaded
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)

        # Check if this is a local file path
        path = Path(url_or_path)
        if path.exists() and path.is_file():
            file_url = path.resolve().as_uri()
            file_path = str(path.resolve())
            logger.debug("Loading OpenAPI spec from local file via URL: %s", file_url)
            try:
                # Always use aiopenapi3's file loader for file:// URLs
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="The 'default' attribute with value",
                        module=r"pydantic\._internal\._generate_schema",
                    )
                    return loop.run_until_complete(OpenAPI.load_async(file_url))
            except Exception:
                # Fallback: read the file and construct OpenAPI from dict
                logger.debug(
                    "file:// failed, constructing OpenAPI from local file: %s",
                    file_path,
                )
                try:
                    txt = path.read_text(encoding="utf-8")
                    spec_data = json.loads(txt)
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            "ignore",
                            message="The 'default' attribute with value",
                            module=r"pydantic\._internal\._generate_schema",
                        )
                        return OpenAPI(file_url, spec_data)
                except Exception:
                    logger.exception(
                        "Failed to construct OpenAPI from local file: %s", file_path
                    )
                    raise

        # For URLs, use async loading. Suppress the specific pydantic
        # UnsupportedFieldAttributeWarning during schema generation which
        # is expected for some OpenAPI specs and is otherwise harmless.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The 'default' attribute with value",
                module=r"pydantic\._internal\._generate_schema",
            )
            return loop.run_until_complete(OpenAPI.load_async(url_or_path))
    finally:
        # Clean up event loop resources
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.debug("Error during shutdown_asyncgens: %s", e)
        try:
            loop.close()
        except Exception as e:
            logger.debug("Error closing event loop: %s", e)
        # Only clear event loop if we're in a worker thread
        try:
            asyncio.set_event_loop(None)
        except RuntimeError as e:
            logger.debug("Could not clear event loop: %s", e)


class ESIClient:
    """EVE Online ESI client with caching, rate limiting, and auth support.

    The client organizes endpoints into namespaces (characters, corporations, etc.)
    for cleaner API access and returns typed Pydantic models.

    Example:
        ```python
        from models.eve import EveAsset, EveLocation

        # Initialize client
        client = ESIClient(client_id="your_client_id")

        # Authenticate a character
        await client.authenticate_character()

        # Get character assets (type-safe, all pages combined)
        character_id = 123456789
        assets: list[EveAsset] = await client.assets.get_assets(character_id)
        print(f"Got {len(assets)} total assets")

        # Get character location
        location: EveLocation = await client.location.get_character_location(
            character_id
        )
        print(f"Character in system {location.solar_system_id}")

        await client.close()
        ```
    """

    def __init__(
        self,
        client_id: str | None = None,
        cache_dir: str | Path | None = None,
        token_file: str | Path | None = None,
        datasource: str | None = None,
        callback_url: str | None = None,
        cache_expiry_warning: int | None = None,
        compatibility_date: str | None = None,
        request_timeout: float = HTTP_TIMEOUT,
    ):
        """Initialize ESI client with PKCE authentication.

        Args:
            client_id: EVE application client ID (required for auth). Falls back to config/env.
            cache_dir: Directory for cache storage. Falls back to config/env.
            token_file: Path to token storage. Falls back to config/env.
            datasource: EVE datasource (tranquility or singularity). Falls back to config/env.
            callback_url: OAuth callback URL (must match app registration). Falls back to config/env.
            cache_expiry_warning: Seconds before expiry to warn. Falls back to config/env.
            compatibility_date: ESI compatibility date (YYYY-MM-DD). Falls back to config/env.
            request_timeout: HTTP request timeout in seconds (default: 30.0).

            All parameters fall back to configuration values from .env or hardcoded defaults
            if not explicitly provided.
        """
        self.request_timeout = request_timeout
        # Use config values as defaults, allow override via parameters
        self.datasource = datasource or global_config.esi.datasource
        # Use path properties from config (PyInstaller-aware), but allow explicit overrides
        if cache_dir is None:
            cache_dir = global_config.esi.cache_dir_path
        if token_file is None:
            token_file = global_config.esi.token_file_path

        # Normalize Path objects to strings for downstream consumers (ESICache, ESIAuth)
        if isinstance(cache_dir, Path):
            cache_dir = str(cache_dir)
        if isinstance(token_file, Path):
            token_file = str(token_file)
        # Rate limit file always uses config (no override parameter)
        rate_limit_file = global_config.esi.rate_limit_file_path
        callback_url = callback_url or global_config.esi.callback_url
        client_id = client_id or global_config.esi.client_id or None

        self.cache = ESICache(cache_dir)
        self.rate_limiter = RateLimitTracker(
            max_backoff_delay=global_config.esi.max_backoff_delay,
            persist_file=rate_limit_file,
        )

        # How many seconds before expiry to warn
        self.cache_expiry_warning = (
            cache_expiry_warning
            if cache_expiry_warning is not None
            else global_config.esi.cache_expiry_warning
        )
        # ESI compatibility date header (X-Compatibility-Date). When None,
        # the client will not force a header and will rely on server defaults.
        # Provide a date like '2020-01-01' to pin compatibility behaviour.
        self.compatibility_date = (
            compatibility_date or global_config.esi.compatibility_date
        )

        # API URLs from config
        self.base_url = global_config.esi.esi_base_url
        self.spec_url = global_config.esi.esi_spec_url

        self._cache_alerts: dict[str, asyncio.Task] = {}

        self.auth = None
        if client_id:
            self.auth = ESIAuth(
                client_id=client_id,
                callback_url=callback_url,
                token_file=token_file,
            )

        self._http_client: httpx.AsyncClient | None = None
        self._api: OpenAPI | None = None
        self._openapi_lock: asyncio.Lock = asyncio.Lock()
        self._metadata_loaded: bool = False

        self._endpoint_metadata: dict[str, dict] = {}

        self.assets = AssetsEndpoints(self)
        self.characters = CharacterEndpoints(self)
        self.contracts = ContractsEndpoints(self)
        self.corporations = CorporationEndpoints(self)
        self.industry = IndustryEndpoints(self)
        self.location = LocationEndpoints(self)
        self.market = MarketEndpoints(self)
        self.skills = SkillsEndpoints(self)
        self.universe = UniverseEndpoints(self)
        self.wallet = WalletEndpoints(self)

        self._path_pattern_cache: dict[str, re.Pattern] = {}
        self._background_tasks: set[asyncio.Task] = set()

        # Image cache directory
        self._image_cache_dir = (
            Path(cache_dir) / "images"
            if cache_dir
            else Path(global_config.esi.cache_dir_path) / "images"
        )
        self._image_cache_dir.mkdir(parents=True, exist_ok=True)

    def _initialize_http_client(self) -> None:
        """Initialize HTTP client with default headers."""
        if self._http_client is not None:
            return

        default_headers = {}
        if self.compatibility_date:
            default_headers["X-Compatibility-Date"] = str(self.compatibility_date)
        self._http_client = httpx.AsyncClient(
            timeout=self.request_timeout, headers=default_headers
        )

    async def _load_cached_openapi_spec(
        self, spec_cache_path: Path
    ) -> tuple[str | None, str | None]:
        """Load local OpenAPI spec and return (version, None).

        Validates cache file before attempting to load:
        - Checks file exists and is readable
        - Validates JSON format
        - Verifies required OpenAPI fields

        Returns:
            Tuple of (local_version, None)
        """
        if not spec_cache_path.exists():
            logger.debug("Cache file does not exist: %s", spec_cache_path)
            return None, None

        try:
            file_size = spec_cache_path.stat().st_size
            if file_size == 0:
                logger.warning("Cache file is empty: %s", spec_cache_path)
                return None, None
        except OSError as e:
            logger.debug("Could not check cache file size: %s", e)

        try:
            txt = spec_cache_path.read_text(encoding="utf-8")
            spec_data = json.loads(txt)

            if not isinstance(spec_data, dict):
                logger.warning(
                    "Cache file is not a valid JSON object: %s", spec_cache_path
                )
                return None, None

            if "openapi" not in spec_data:
                logger.warning(
                    "Cache file missing OpenAPI version field: %s",
                    spec_cache_path,
                )
                return None, None

            if "info" not in spec_data:
                logger.warning("Cache file missing info section: %s", spec_cache_path)
                return None, None

            local_version = spec_data.get("info", {}).get("version")
            logger.debug("Cache file validated, version: %s", local_version)
            return local_version, None

        except json.JSONDecodeError as e:
            logger.warning(
                "Cache file contains invalid JSON: %s (error: %s)", spec_cache_path, e
            )
            return None, None
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Could not read local OpenAPI cache: %s", e)
            return None, None

    async def _fetch_remote_openapi_spec(
        self,
    ) -> tuple[str | None, str | None]:
        """Fetch remote OpenAPI spec and return (version, spec_text).

        Returns:
            Tuple of (remote_version, remote_spec_text)
        """
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http_client:
                resp = await http_client.get(self.spec_url)
                resp.raise_for_status()
                remote_spec_text = resp.text
                try:
                    remote_version = resp.json().get("info", {}).get("version")
                    return remote_version, remote_spec_text
                except (json.JSONDecodeError, KeyError, AttributeError) as e:
                    logger.debug("Could not parse remote spec version: %s", e)
                    return None, remote_spec_text
        except (httpx.HTTPError, httpx.RequestError) as e:
            logger.debug("Could not fetch remote OpenAPI spec: %s", e)
            return None, None

    def _persist_openapi_spec(
        self, spec_text: str, spec_cache_path: Path, spec_cache_dir: Path
    ) -> bool:
        """Atomically persist OpenAPI spec to cache file.

        Returns:
            True if successful, False otherwise
        """
        try:
            fd, tmp = tempfile.mkstemp(
                dir=spec_cache_dir,
                prefix=".openapi_",
                suffix=".json.tmp",
                text=True,
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(spec_text)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, spec_cache_path)
                return True
            except OSError:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except OSError as e:
            logger.debug("Failed to persist OpenAPI spec: %s", e)
            return False

    async def _load_openapi_with_timeout(self, load_target: str) -> OpenAPI | None:
        """Load OpenAPI spec with timeout protection.

        Args:
            load_target: Path or URL to load from

        Returns:
            Loaded OpenAPI object or None on failure
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_load_openapi_blocking, load_target),
                timeout=OPENAPI_LOAD_TIMEOUT,
            )
        except TimeoutError:
            logger.error("Timeout while loading OpenAPI spec from %s", load_target)
            return None
        except Exception:
            # Catch any exception raised during threaded loading (including
            # unexpected ones when asyncio.to_thread is patched/mocked in tests)
            logger.exception("Failed to load OpenAPI spec from %s", load_target)
            return None

    async def _ensure_initialized(self) -> None:
        """Ensure HTTP client and OpenAPI spec are loaded."""
        self._initialize_http_client()

        # Load OpenAPI spec once with proper locking to prevent concurrent loads
        if not self._metadata_loaded:
            async with self._openapi_lock:
                # Re-check under lock (another coroutine may have loaded it)
                if not self._metadata_loaded:
                    await self._load_openapi_spec()

    async def _load_openapi_spec(self) -> None:
        """Load OpenAPI specification with caching and version checking.

        This method handles:
        - Local cache checking and version comparison
        - Remote spec fetching with fallback
        - Atomic cache persistence
        - Background thread loading to avoid blocking
        - Graceful degradation when loading fails
        """
        # Simplified startup behaviour:
        # - If a valid cache exists, load it immediately for fast startup.
        # - Schedule a best-effort background refresh to update the cache.
        # - If no cache, perform a single remote fetch and persist.
        logger.info("Loading OpenAPI spec from %s", self.spec_url)

        try:
            spec_cache_dir = Path(global_config.esi.cache_dir_path).parent
            spec_cache_dir.mkdir(parents=True, exist_ok=True)
            spec_cache_path = spec_cache_dir / "openapi.json"

            # Prefer using a validated local cache for fast startup. If we have
            # a valid cached OpenAPI spec, load it immediately and perform a
            # best-effort background refresh so the app doesn't wait on network.
            local_version, _ = await self._load_cached_openapi_spec(spec_cache_path)

            if local_version is not None:
                # Fast path: cache exists and is valid. Parse metadata directly
                # from JSON without constructing the expensive OpenAPI/Pydantic models.
                try:
                    txt = spec_cache_path.read_text(encoding="utf-8")
                    spec_data = json.loads(txt)
                    self._parse_endpoint_metadata_from_spec_dict(spec_data)
                    self._metadata_loaded = True
                except Exception:
                    logger.debug("Failed to parse cached OpenAPI spec metadata")
                    return

                # Best-effort: check remote version once to avoid unnecessary
                # full-spec downloads. Tests expect a single remote check here.
                try:
                    (
                        remote_version,
                        remote_spec_text,
                    ) = await self._fetch_remote_openapi_spec()
                except Exception:
                    remote_version, remote_spec_text = None, None

                # If we couldn't determine remote version, schedule a background
                # refresh (non-fatal) and continue using cached metadata.
                if remote_version is None:
                    try:
                        loop = asyncio.get_event_loop()
                        task = loop.create_task(
                            self._background_refresh_openapi_spec(spec_cache_path)
                        )
                        self._background_tasks.add(task)
                        task.add_done_callback(
                            lambda t: self._background_tasks.discard(t)
                        )
                    except Exception:
                        logger.debug("Could not schedule background OpenAPI refresh")

                    logger.debug(
                        "Using cached OpenAPI metadata, skipping full load on startup"
                    )
                    return

                # If remote version matches local, nothing to do (we already have metadata)
                if local_version == remote_version:
                    logger.debug(
                        "Using cached OpenAPI spec (version %s)", local_version
                    )
                    return

                # Version mismatch: prefer persisting remote spec (if present) and
                # load the full OpenAPI object from the persisted cache. Fall
                # through to the load attempts below by setting load_target.
                load_target = self._determine_openapi_load_target(
                    local_version,
                    remote_version,
                    remote_spec_text,
                    spec_cache_path,
                    spec_cache_dir,
                )

            # No valid cache; perform a synchronous remote fetch and persist
            # so startup can proceed with a known spec.
            remote_version, remote_spec_text = await self._fetch_remote_openapi_spec()

            if local_version is None and remote_version is None:
                logger.warning("Both cache and remote spec version checks failed")
                if spec_cache_path.exists():
                    logger.info(
                        "Attempting to use cached spec despite version check failure"
                    )
                    load_target = str(spec_cache_path)
                else:
                    logger.info("No cache available, will load from URL")
                    load_target = self.spec_url
            else:
                load_target = self._determine_openapi_load_target(
                    local_version,
                    remote_version,
                    remote_spec_text,
                    spec_cache_path,
                    spec_cache_dir,
                )

            # No valid cache - must load OpenAPI object for metadata
            attempt = 0
            while attempt < MAX_LOAD_ATTEMPTS:
                attempt += 1
                logger.debug(
                    "OpenAPI loading attempt %d/%d from: %s",
                    attempt,
                    MAX_LOAD_ATTEMPTS,
                    load_target,
                )

                self._api = await self._load_openapi_with_timeout(load_target)

                if self._api:
                    logger.info(
                        "Loaded OpenAPI spec: %s",
                        getattr(self._api.info, "title", "<unknown>"),
                    )
                    self._parse_endpoint_metadata()
                    self._metadata_loaded = True
                    return

                if attempt < MAX_LOAD_ATTEMPTS:
                    if load_target != self.spec_url:
                        logger.warning("Load failed, falling back to remote URL")
                        load_target = self.spec_url
                        await asyncio.sleep(1)
                    else:
                        logger.error("Remote URL load failed")
                        break

            logger.warning(
                "OpenAPI spec failed to load after %d attempts - metadata unavailable",
                attempt,
            )
            logger.info(
                "Application will continue without OpenAPI metadata (direct API calls will still work)"
            )

        except Exception:
            logger.exception("Unexpected error loading OpenAPI spec")
            logger.info("Application will continue without OpenAPI metadata")

    async def _background_refresh_openapi_spec(self, spec_cache_path: Path) -> None:
        """Best-effort background refresh of the remote OpenAPI spec.

        This does a simple GET, compares body to existing cache, and
        atomically persists & reparses if different. Failures are logged
        at debug level and do not raise.
        """
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http_client:
                resp = await http_client.get(self.spec_url)
                # Respect 304 if server returns it
                if resp.status_code == 304:
                    logger.debug("OpenAPI remote returned 304 Not Modified")
                    return
                resp.raise_for_status()
                remote_text = resp.text

            # If identical to existing cache, nothing to do
            try:
                existing = spec_cache_path.read_text(encoding="utf-8")
                if existing == remote_text:
                    logger.debug("Remote OpenAPI identical to cache; no update")
                    return
            except (OSError, UnicodeDecodeError):
                pass

            if self._persist_openapi_spec(
                remote_text, spec_cache_path, spec_cache_path.parent
            ):
                api = await self._load_openapi_with_timeout(str(spec_cache_path))
                if api:
                    self._api = api
                    try:
                        self._parse_endpoint_metadata()
                    except (AttributeError, KeyError, TypeError) as e:
                        logger.debug(
                            "Failed to parse OpenAPI metadata after refresh: %s", e
                        )
                    logger.info("Updated OpenAPI spec from remote in background")

        except (httpx.HTTPError, httpx.RequestError, OSError) as e:
            logger.debug("Background OpenAPI refresh failed: %s", e)

    def _determine_openapi_load_target(
        self,
        local_version: str | None,
        remote_version: str | None,
        remote_spec_text: str | None,
        spec_cache_path: Path,
        spec_cache_dir: Path,
    ) -> str:
        """Determine which OpenAPI spec source to load from.

        Args:
            local_version: Version string from local cache
            remote_version: Version string from remote spec
            remote_spec_text: Full text of remote spec
            spec_cache_path: Path to cache file
            spec_cache_dir: Directory for cache storage

        Returns:
            Path or URL to load OpenAPI spec from
        """
        # Use local cache if versions match
        if local_version and remote_version and local_version == remote_version:
            logger.debug("Using cached OpenAPI spec (version %s)", local_version)
            return str(spec_cache_path)

        # Persist and use remote spec if available
        if remote_spec_text:
            if self._persist_openapi_spec(
                remote_spec_text, spec_cache_path, spec_cache_dir
            ):
                logger.debug(
                    "Persisted remote OpenAPI spec (version %s)", remote_version
                )
                return str(spec_cache_path)

        # Fallback: load directly from URL
        logger.debug("Loading OpenAPI spec directly from URL")
        return self.spec_url

    def _get_rate_group_from_extensions(self, extensions: object) -> str | None:
        """Return rate-group name from operation `x-rate-limit` extension.

        Accepts either the structured form `{... 'group': 'name' ...}` or
        the historical shorthand string `'name'`. Returns None for other
        shapes.
        """
        if not isinstance(extensions, Mapping):
            return None

        ext = extensions.get("x-rate-limit")  # type: ignore[arg-type]

        if isinstance(ext, Mapping):
            grp = ext.get("group")  # type: ignore[arg-type]
            if isinstance(grp, str) and grp:
                return grp

        if isinstance(ext, str) and re.fullmatch(r"[A-Za-z0-9_-]+", ext):
            return ext

        return None

    def _parse_endpoint_metadata_from_spec_dict(self, spec: dict) -> None:
        """Extract endpoint metadata (auth requirement, rate-group) from
        a raw OpenAPI spec dictionary without constructing OpenAPI models.

        This is a fast, best-effort parser used at startup when a cached
        spec JSON is available. It populates `self._endpoint_metadata`.
        """
        try:
            paths = spec.get("paths") or {}
            global_security = spec.get("security")
            for path, path_item in paths.items():
                # path_item is a dict mapping methods to operation objects
                for method in (
                    "get",
                    "post",
                    "put",
                    "delete",
                    "patch",
                    "options",
                    "head",
                ):
                    op = path_item.get(method)
                    if not op:
                        continue

                    requires_auth = False
                    if op.get("security"):
                        requires_auth = True
                    elif path_item.get("security"):
                        requires_auth = True
                    elif global_security:
                        requires_auth = True

                    rate_group = None
                    # Many OpenAPI specs use vendor extension 'x-rate-limit'
                    xr = op.get("x-rate-limit")
                    if isinstance(xr, dict):
                        grp = xr.get("group")
                        if isinstance(grp, str) and grp:
                            rate_group = grp

                    endpoint_key = f"{method.upper()} {path}"
                    self._endpoint_metadata[endpoint_key] = {
                        "rate_group": rate_group,
                        "requires_auth": requires_auth,
                    }

            logger.info(
                "Parsed metadata for %d endpoints (fast)", len(self._endpoint_metadata)
            )
        except Exception:
            logger.debug("Failed fast-parse of OpenAPI spec dict")

    def _parse_endpoint_metadata(self) -> None:
        """Parse OpenAPI spec to extract endpoint metadata.

        Extracts for each endpoint:
        - Auth requirement (presence of 'security' field)
        - Rate limit group (from x-rate-limit extension)

        Note: Pagination style is determined at runtime from response headers/content,
        not from OpenAPI metadata.
        """
        if not self._api:
            return

        # Access the paths from the OpenAPI spec
        if not hasattr(self._api, "paths"):
            return

        paths_obj = self._api.paths

        if hasattr(paths_obj, "_root") and isinstance(paths_obj._root, dict):  # noqa: SLF001
            paths_dict = paths_obj._root  # noqa: SLF001
        elif hasattr(paths_obj, "__iter__"):
            try:
                paths_dict = (
                    dict(paths_obj.items())
                    if hasattr(paths_obj, "items")
                    else {k: getattr(paths_obj, k) for k in paths_obj}
                )
            except Exception:
                return
        else:
            return

        for path, path_item in paths_dict.items():
            for method in ("get", "post", "put", "delete", "patch", "options", "head"):
                op = getattr(path_item, method, None)
                if not op:
                    continue

                # Check if endpoint requires auth by checking for 'security' field
                # (either at operation, path, or API level)
                requires_auth = False
                if getattr(op, "security", None):
                    requires_auth = True
                elif getattr(path_item, "security", None):
                    requires_auth = True
                elif self._api and getattr(self._api, "security", None):
                    requires_auth = True

                rate_group = self._get_rate_group_from_extensions(
                    getattr(op, "extensions", None) or {}
                )

                endpoint_key = f"{method.upper()} {path}"
                self._endpoint_metadata[endpoint_key] = {
                    "rate_group": rate_group,
                    "requires_auth": requires_auth,
                }

        logger.info("Parsed metadata for %d endpoints", len(self._endpoint_metadata))

    def _normalize_path_to_template(self, path: str) -> str:
        """Convert a real path with IDs to OpenAPI template format.

        Examples:
            /characters/96947097/assets → /characters/{character_id}/assets
            /corporations/98682702/projects → /corporations/{corporation_id}/projects

        Note: Always strips trailing slashes to match OpenAPI spec format.
        """
        path = path.rstrip("/")
        return re.sub(r"/\d+", "/{id}", path)

    def _compile_path_pattern(self, template: str) -> re.Pattern | None:
        """Compile OpenAPI path template to regex pattern with caching.

        Args:
            template: OpenAPI path template (e.g., '/characters/{character_id}/assets')

        Returns:
            Compiled regex pattern or None if invalid
        """
        if template in self._path_pattern_cache:
            return self._path_pattern_cache[template]

        try:
            # Convert '/foo/{bar}/baz' -> '^/foo/[^/]+?/baz/?$'
            pattern_str = "^" + re.sub(r"\{[^}]+\}", r"[^/]+?", template) + r"/?$"
            compiled = re.compile(pattern_str)
            self._path_pattern_cache[template] = compiled
            return compiled
        except re.error as e:
            logger.warning("Invalid regex pattern from template '%s': %s", template, e)
            return None

    def _get_endpoint_metadata(self, method: str, path: str) -> dict:
        """Get endpoint metadata with cached regex matching.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path (may contain IDs)

        Returns:
            Dict with endpoint metadata (rate_group, requires_auth)
        """
        endpoint_key = f"{method.upper()} {path}"
        endpoint_meta = self._endpoint_metadata.get(endpoint_key)
        if endpoint_meta:
            return endpoint_meta

        norm_path = path.rstrip("/")
        method_prefix = f"{method.upper()} "

        for key, meta in self._endpoint_metadata.items():
            if not key.startswith(method_prefix):
                continue

            template = key[len(method_prefix) :].rstrip("/")
            pattern = self._compile_path_pattern(template)

            if pattern and pattern.match(norm_path):
                logger.debug(
                    "Matched endpoint metadata: %s %s -> template %s",
                    method.upper(),
                    norm_path,
                    template,
                )
                return meta

        logger.debug(
            "No metadata found for %s %s",
            method.upper(),
            norm_path,
        )
        return {}

    async def authenticate_character(self, scopes: list[str] | None = None) -> dict:
        """Authenticate a character via OAuth.

        Args:
            scopes: List of ESI scopes (defaults to assets read)

        Returns:
            Character info dict

        Raises:
            ValueError: If client_id not provided
        """
        if not self.auth:
            raise ValueError(
                "Authentication requires client_id. "
                "Initialize ESIClient with client_id parameter."
            )

        return await self.auth.authenticate_interactive(scopes)

    def _cache_key(
        self, method: str, path: str, params: dict | None, json_body: Any = None
    ) -> str:
        """Return the cache key for a request (delegates to ESICache)."""
        return self.cache.make_key(method, path, params, json_body)

    def _cancel_cache_alert(self, key: str) -> None:
        task = self._cache_alerts.pop(key, None)
        if task and not task.done():
            task.cancel()

    def _schedule_cache_expiry_alert(
        self,
        method: str,
        path: str,
        params: dict | None,
        expires_at: datetime,
        json_body: Any = None,
    ) -> None:
        """Schedule a warning before cache expiry."""
        if not expires_at:
            return

        key = self._cache_key(method, path, params, json_body)
        self._cancel_cache_alert(key)

        seconds_left = (expires_at - datetime.now(UTC)).total_seconds()
        warn_before = float(self.cache_expiry_warning)

        if seconds_left <= 0:
            return

        if seconds_left <= warn_before:
            logger.info(
                "Cache expiring soon: %s %s expires in %.0fs",
                method,
                path,
                seconds_left,
            )
            return

        delay = seconds_left - warn_before

        async def _alert():
            try:
                await asyncio.sleep(delay)
                logger.info(
                    "Cache expiry alert: %s %s will expire in %.0fs",
                    method,
                    path,
                    warn_before,
                )
            except asyncio.CancelledError:
                return

        task = asyncio.create_task(_alert())
        self._cache_alerts[key] = task

    def list_authenticated_characters(self) -> list[dict]:
        """List all authenticated characters.

        Returns:
            List of character info dicts
        """
        if not self.auth:
            return []
        return self.auth.list_authenticated_characters()

    def _validate_request_params(
        self,
        owner_id: int | None,
        max_retries: int,
    ) -> None:
        """Validate request parameters.

        Args:
            owner_id: Character ID for authenticated requests
            max_retries: Maximum retry attempts

        Raises:
            ValueError: If parameters are invalid
        """
        if owner_id is not None and owner_id <= 0:
            raise ValueError(f"Invalid owner_id: {owner_id} (must be positive)")

        if max_retries < 0 or max_retries > 10:
            raise ValueError(f"Invalid max_retries: {max_retries} (must be 0-10)")

    async def _ensure_auth_token(self, owner_id: int) -> None:
        """Ensure valid authentication token for character.

        Args:
            owner_id: Character ID

        Raises:
            ValueError: If authentication not configured
            Exception: If token refresh fails
        """
        if self.auth is None:
            raise ValueError(
                "Authentication not configured on ESIClient. "
                "Initialize with client_id parameter to enable authentication."
            )

        try:
            await self.auth.get_token(owner_id)
        except Exception as e:
            logger.error(
                "Failed to get/refresh token for character %s: %s", owner_id, e
            )
            raise

    def _check_cached_response(
        self,
        method: str,
        path: str,
        params: dict | None,
        use_cache: bool,
    ) -> tuple[Any | None, dict | None, str | None]:
        """Check cache for existing response.

        Args:
            method: HTTP method
            path: Request path
            params: Query parameters
            use_cache: Whether caching is enabled

        Returns:
            Tuple of (cached_data, cached_headers, cached_etag)
        """
        if not use_cache:
            return None, None, None

        cached = self.cache.get(method, path, params)
        if not cached:
            return None, None, None

        try:
            cached_data, cached_headers, cached_etag, _ = cached
            cached_headers = cached_headers or {}

            if cached_data is None:
                return None, None, None

            # If cache returns a value, it's valid (diskcache handles expiry)
            if cached_etag:
                logger.debug("Cache hit: %s %s (ETag)", method, path)
                return (
                    cached_data,
                    cached_headers,
                    None,
                )  # Return data, don't need ETag

            # No ETag, return cached data
            logger.debug("Cache hit: %s %s", method, path)
            return cached_data, cached_headers, None

        except Exception as e:
            logger.error("Cache format error: %s", e)
            return None, None, None

    def _prepare_request_headers(
        self,
        headers: dict | None,
        cached_etag: str | None,
        method: str,
        use_cache: bool,
    ) -> dict:
        """Prepare request headers with conditional request support.

        Args:
            headers: User-provided headers
            cached_etag: ETag from cache for conditional requests
            method: HTTP method
            use_cache: Whether caching is enabled

        Returns:
            Prepared headers dict
        """
        request_headers = headers.copy() if headers else {}

        # Ensure compatibility date header
        if self.compatibility_date and "X-Compatibility-Date" not in request_headers:
            request_headers["X-Compatibility-Date"] = self.compatibility_date

        # Add If-None-Match for conditional GET requests
        if cached_etag and use_cache and method.upper() == "GET":
            request_headers["If-None-Match"] = cached_etag

        return request_headers

    async def _add_auth_header(
        self,
        request_headers: dict,
        requires_auth: bool,
        owner_id: int | None,
    ) -> None:
        """Add Authorization header if authentication is required.

        Args:
            request_headers: Headers dict to modify
            requires_auth: Whether endpoint requires authentication
            owner_id: Character ID for authenticated requests
        """
        if not requires_auth or owner_id is None:
            return

        if self.auth is None:
            raise ValueError(
                "Authentication not configured on ESIClient. "
                "Initialize with client_id parameter to enable authentication."
            )

        try:
            token = await self.auth.get_token(owner_id)
            if token:
                request_headers["Authorization"] = f"Bearer {token}"
        except Exception as e:
            logger.debug(
                "Could not obtain/refresh access token for owner %s: %s",
                owner_id,
                e,
            )
            # Let request proceed without Authorization for proper error handling

    def _determine_rate_limit_key(
        self,
        rate_group: str | None,
        requires_auth: bool,
        owner_id: int | None,
    ) -> str | None:
        """Determine rate limit key for tracking.

        Args:
            rate_group: Rate limit group from endpoint metadata
            requires_auth: Whether endpoint requires authentication
            owner_id: Character ID

        Returns:
            Rate limit key or None for unmigrated endpoints
        """
        if not rate_group:
            return None

        if requires_auth and owner_id is not None:
            return f"{rate_group}:{owner_id}"

        return rate_group

    def _handle_304_response(
        self,
        method: str,
        path: str,
        params: dict | None,
        cached_data: Any,
        cached_headers: dict | None,
        cached_etag: str | None,
        response_headers: dict,
        group_key: str | None = None,
        json_body: Any = None,
    ) -> tuple[Any, dict]:
        """Handle 304 Not Modified response by returning cached data with updated headers.

        Args:
            method: HTTP method
            path: Request path
            params: Query parameters
            cached_data: Cached response data
            cached_headers: Cached response headers
            cached_etag: Cached ETag
            response_headers: Response headers from 304
            group_key: Rate limit group key for backoff reset
            json_body: JSON body for POST/PUT requests (for cache key)

        Returns:
            Tuple of (cached_data, merged_headers)
        """
        # Served-by indicator for observability
        logger.debug("Served by API 304 (validated cache): %s %s", method, path)
        self.rate_limiter.reset_backoff(group_key=group_key)

        if cached_data is not None:
            # Merge response headers into cached headers
            merged_headers = {**(cached_headers or {}), **response_headers}
            # Ensure ETag remains present
            if "etag" not in merged_headers and cached_etag:
                merged_headers["etag"] = cached_etag
            self.cache.set(method, path, cached_data, merged_headers, params, json_body)
            return cached_data, merged_headers

        # Fallback if no cached data (shouldn't happen)
        return None, response_headers

    def _parse_response_data(
        self, response: Any, method: str, url: str
    ) -> tuple[Any, dict]:
        """Parse response with error handling.

        Args:
            response: HTTP response object
            method: HTTP method
            url: Request URL

        Returns:
            Tuple of (parsed_data, normalized_headers)
            For JSON responses, data is the parsed JSON object.
            For binary responses (images), data is bytes.
        """
        data = None
        if response.content:
            content_type = response.headers.get("content-type", "")
            # For images and other binary content, return raw bytes
            if content_type.startswith(("image/", "application/octet-stream")):
                data = response.content
            else:
                # Try to parse as JSON
                try:
                    data = response.json()
                except (ValueError, json.JSONDecodeError) as e:
                    preview = response.text[:200] if response.text else "<empty>"
                    logger.warning(
                        "Failed to parse JSON response for %s %s (status=%d, content-type=%s): %s. "
                        "Response preview: %s",
                        method,
                        url,
                        response.status_code,
                        content_type,
                        e,
                        preview,
                    )
                    data = None

        headers_dict = {k.lower(): v for k, v in response.headers.items()}
        return data, headers_dict

    async def _handle_401_retry(
        self,
        owner_id: int | None,
        requires_auth: bool,
    ) -> bool:
        """Handle 401 Unauthorized by attempting token refresh.

        Args:
            owner_id: Character ID
            requires_auth: Whether endpoint requires auth

        Returns:
            True if should retry request, False otherwise
        """
        if not requires_auth or owner_id is None:
            return False

        logger.warning(f"401 Unauthorized for character {owner_id}, refreshing token")
        try:
            if self.auth:
                await self.auth.refresh_token(str(owner_id))
                logger.debug(
                    "Token refreshed successfully for character %s",
                    owner_id,
                )
                return True
        except Exception as refresh_error:
            logger.error(
                "Token refresh failed for character %s: %s",
                owner_id,
                refresh_error,
            )
        return False

    async def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        headers: dict | None = None,
        json_body: Any = None,
        use_cache: bool = True,
        max_retries: int = 3,
        owner_id: int | None = None,
        full_url: str | None = None,
    ) -> tuple[Any, dict]:
        """Generic request method with caching and rate limiting.

        Args:
            method: HTTP method
            path: API path (e.g., /characters/{character_id}/assets/)
            params: Query parameters
            headers: Additional headers
            json_body: JSON body for POST/PUT requests
            use_cache: Whether to use cache
            max_retries: Maximum retry attempts
            owner_id: Character ID for authenticated endpoints (None for public)

        Returns:
            Tuple of (response_data, response_headers)

        Raises:
            httpx.HTTPStatusError: On HTTP errors after retries
        """
        await self._ensure_initialized()

        # Validate request parameters
        self._validate_request_params(owner_id, max_retries)

        endpoint_meta = self._get_endpoint_metadata(method, path)
        requires_auth = endpoint_meta.get("requires_auth", False)
        rate_group = endpoint_meta.get("rate_group")

        # Force auth if owner_id provided (handles metadata parsing mismatches)
        if owner_id is not None and not requires_auth:
            logger.warning(
                "Owner_id provided (%s) but endpoint marked as public: %s %s -> %s; forcing auth",
                owner_id,
                method,
                path,
                endpoint_meta,
            )
            requires_auth = True

        # Check cache for existing response
        cached_data, cached_headers, cached_etag = self._check_cached_response(
            method, path, params, use_cache
        )

        # Ensure authentication token is valid if required
        if requires_auth and owner_id is not None:
            await self._ensure_auth_token(owner_id)

        original_params = params or {}
        request_params = dict(original_params)
        request_params.setdefault(
            "datasource", str(self.datasource) if self.datasource is not None else None
        )

        # Return cached data if still valid
        if (
            cached_data is not None
            and cached_headers is not None
            and cached_etag is None
        ):
            return cached_data, cached_headers

        # Determine rate limit key for backoff check
        rate_limit_key = self._determine_rate_limit_key(
            rate_group, requires_auth, owner_id
        )

        # Check rate limits before request (context-aware)
        await self.rate_limiter.wait_if_needed(rate_limit_key)

        # Make request with retries
        token_refresh_attempted = False  # Track if we've already tried refreshing token
        for attempt in range(max_retries):
            # Prepare headers fresh on each attempt so refreshed tokens are applied
            request_headers = self._prepare_request_headers(
                headers, cached_etag, method, use_cache
            )

            # Add authentication header if required
            await self._add_auth_header(request_headers, requires_auth, owner_id)

            try:
                url = full_url if full_url else f"{self.base_url}{path}"

                # _http_client is guaranteed to be initialized by _ensure_initialized()
                if self._http_client is None:
                    raise RuntimeError(
                        "HTTP client not initialized. Call _ensure_initialized() first."
                    )

                # Log whether Authorization header will be sent (avoid logging token value)
                logger.debug(
                    "Sending HTTP request: %s %s (requires_auth=%s owner=%s) Authorization=%s",
                    method,
                    url,
                    requires_auth,
                    owner_id,
                    "present" if "Authorization" in request_headers else "missing",
                )

                # Use the configured HTTP client. Tests should patch `self._http_client`
                # with an AsyncMock when simulating responses.
                client_to_use = self._http_client
                if client_to_use is None:
                    raise RuntimeError(
                        "HTTP client not initialized. Call _ensure_initialized() first."
                    )

                # Normalize header keys to lowercase for consistent testing and
                # downstream handling (tests expect lowercase keys).
                request_headers = {k.lower(): v for k, v in request_headers.items()}

                # Call the client's request method. Some test harnesses inject a
                # Mock whose .request() is not awaitable, while real httpx AsyncClient
                # returns an awaitable. Handle both cases gracefully.
                maybe_awaitable = client_to_use.request(
                    method,
                    url,
                    params=request_params,
                    headers=request_headers,
                    json=json_body if json_body is not None else None,
                )
                if inspect.isawaitable(maybe_awaitable):
                    response = await maybe_awaitable
                else:
                    response = maybe_awaitable

                # Normalize headers to lowercase keys for consistent parsing
                headers_dict = {k.lower(): v for k, v in response.headers.items()}

                # Determine rate group key based on endpoint auth requirements
                # - Public endpoints: use <group> only (shared per application)
                # - Authenticated endpoints: use <group>:<character_id> (per character)
                rate_group = headers_dict.get("x-ratelimit-group")
                override_key = None
                if rate_group:
                    if requires_auth and owner_id is not None:
                        # Authenticated endpoint - scope to character
                        override_key = f"{rate_group}:{owner_id}"
                    else:
                        # Public endpoint - use group alone
                        override_key = rate_group

                # Update rate limit tracking (includes token bucket system)
                self.rate_limiter.update_from_headers(
                    headers_dict, group_key=override_key
                )

                # Inline debug logging for rate limit status
                try:
                    has_token_bucket = headers_dict.get("x-ratelimit-group") is not None
                    has_error_limit = (
                        headers_dict.get("x-esi-error-limit-remain") is not None
                    )

                    if has_token_bucket and override_key:
                        grp_info = self.rate_limiter.rate_limit_groups.get(override_key)
                        if grp_info:
                            limit = grp_info.get("limit")
                            remaining = grp_info.get("remaining")
                            used = grp_info.get("used")
                            rps = grp_info.get("requests_per_second")
                            tps = grp_info.get("tokens_per_second")
                            if rps:
                                logger.debug(
                                    "[ESI LIMIT RATE] group=%s remaining=%d/%d used=%d rps=%.3f tps=%.3f",
                                    override_key,
                                    remaining,
                                    limit,
                                    used,
                                    rps,
                                    tps,
                                )
                            else:
                                logger.debug(
                                    "[ESI LIMIT RATE] group=%s remaining=%d/%d used=%d",
                                    override_key,
                                    remaining,
                                    limit,
                                    used,
                                )
                    elif has_error_limit:
                        err = self.rate_limiter.error_remain
                        reset = (
                            self.rate_limiter.error_reset.isoformat()
                            if self.rate_limiter.error_reset
                            else None
                        )
                        logger.debug(
                            "[ESI ERROR LIMIT] remaining=%d reset_at=%s", err, reset
                        )
                except Exception:
                    # Non-fatal monitoring errors should not break requests
                    pass

                # Handle 304 Not Modified - return cached data
                if response.status_code == 304:
                    resp_headers = {k.lower(): v for k, v in response.headers.items()}
                    return self._handle_304_response(
                        method,
                        path,
                        params,
                        cached_data,
                        cached_headers,
                        cached_etag,
                        resp_headers,
                        override_key,
                        json_body,
                    )

                # Handle 429 Too Many Requests
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    await self.rate_limiter.handle_429(
                        retry_after=retry_after, group_key=override_key
                    )
                    continue

                # Check for HTTP errors (MUST be inside try block to catch 401)
                response.raise_for_status()

                # Success - reset backoff and parse response
                self.rate_limiter.reset_backoff(group_key=override_key)

                # Parse JSON response with error handling
                data, headers_dict = self._parse_response_data(response, method, url)

                # Cache successful response (only if we got valid data)
                if use_cache and data is not None:
                    self.cache.set(method, path, data, headers_dict, params, json_body)
                    logger.debug(
                        "Served by API 200 (fresh, cached): %s %s", method, path
                    )
                else:
                    logger.debug("Served by API 200 (fresh): %s %s", method, path)

                return data, headers_dict

            except httpx.HTTPStatusError as e:
                # Handle 401 Unauthorized - token may have expired
                if e.response.status_code == 401:
                    # Only attempt token refresh once per request
                    if not token_refresh_attempted and await self._handle_401_retry(
                        owner_id, requires_auth
                    ):
                        token_refresh_attempted = True
                        continue  # Retry with refreshed token
                    # If we already tried refreshing or refresh wasn't applicable, this is a genuine auth failure
                    # Don't spam logs - structures often have restricted ESI access
                    logger.debug(
                        "401 Unauthorized for %s %s (character %s) - access denied (not in structure ACL or insufficient permissions)",
                        method,
                        path,
                        owner_id,
                    )

                # Check if it's a server error that should be retried
                if attempt == max_retries - 1:
                    raise
                if e.response.status_code in (500, 502, 503, 504):
                    # Server error - retry with backoff
                    await asyncio.sleep(2**attempt)
                    continue
                raise

            except httpx.RequestError:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
                continue

        # Should never reach here due to raises above, but satisfy type checker
        raise RuntimeError("Request failed after all retries")

    async def paginated_request(
        self,
        method: str,
        path: str,
        headers: dict | None = None,
        use_cache: bool = True,
        owner_id: int | None = None,
        full_url: str | None = None,
    ) -> AsyncIterator[Any]:
        """Generic paginated request handler.

        Detects pagination style from the actual response:
        - X-Pages header → page-based pagination
        - 'cursor' object in response body → cursor-based pagination
        - Neither → single-page response

        Args:
            method: HTTP method
            path: API path
            headers: Request headers
            use_cache: Whether to use cache
            owner_id: Character ID for authenticated endpoints

        Yields:
            Response data for each page
        """
        await self._ensure_initialized()

        # Make initial request to detect pagination style from response
        data, response_headers = await self.request(
            method,
            path,
            params={"page": 1},  # Start with page 1 in case it's x-pages pagination
            headers=headers,
            use_cache=use_cache,
            owner_id=owner_id,
            full_url=full_url,
        )

        # Detect pagination from response
        x_pages = response_headers.get("x-pages")
        has_cursor = isinstance(data, dict) and "cursor" in data

        if x_pages:
            # X-Pages pagination detected from response header
            yield data

            total_pages = int(x_pages)
            for page in range(2, total_pages + 1):
                page_data, _ = await self.request(
                    method,
                    path,
                    params={"page": page},
                    headers=headers,
                    use_cache=use_cache,
                    owner_id=owner_id,
                    full_url=full_url,
                )
                yield page_data

        elif has_cursor:
            # Cursor-based pagination detected from response body
            # ESI cursor responses: {"cursor": {"before":"...","after":"..."}, "projects": [...]}
            cursor = data["cursor"].get("after") or data["cursor"].get("next")

            # Find the primary list key (projects, data, items, results)
            list_key = None
            for candidate in ("projects", "data", "items", "results"):
                if candidate in data and isinstance(data[candidate], list):
                    list_key = candidate
                    break

            # Yield first page data
            if list_key:
                yield data[list_key]
            else:
                yield data

            # Iterate remaining pages
            while cursor:
                page_data, _ = await self.request(
                    method,
                    path,
                    params={"after": cursor},
                    headers=headers,
                    use_cache=use_cache,
                    owner_id=owner_id,
                    full_url=full_url,
                )

                if not isinstance(page_data, dict):
                    yield page_data
                    break

                # Yield the list portion if present
                if list_key and list_key in page_data:
                    yield page_data[list_key]
                else:
                    yield page_data

                # Update cursor for next iteration
                if "cursor" not in page_data or not isinstance(
                    page_data["cursor"], dict
                ):
                    break
                cursor = page_data["cursor"].get("after") or page_data["cursor"].get(
                    "next"
                )

        else:
            # No pagination detected - single-page response
            # Remove the page=1 param we added speculatively
            if isinstance(data, dict) and not x_pages and not has_cursor:
                # Re-request without page param to get clean response
                data, _ = await self.request(
                    method,
                    path,
                    headers=headers,
                    use_cache=use_cache,
                    owner_id=owner_id,
                    full_url=full_url,
                )
            yield data

    def get_rate_limit_status(self) -> dict:
        """Get current rate limit status.

        Returns:
            Dict with token bucket and error limit info
        """
        return self.rate_limiter.get_rate_limit_info()

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        # Cancel any scheduled cache expiry alert tasks
        for key, task in list(self._cache_alerts.items()):
            try:
                if task and not task.done():
                    task.cancel()
            finally:
                self._cache_alerts.pop(key, None)

        # Cancel any background tasks started by the client (e.g., OpenAPI refresh)
        for task in list(self._background_tasks):
            try:
                if task and not task.done():
                    task.cancel()
            finally:
                self._background_tasks.discard(task)

        if self._http_client:
            await self._http_client.aclose()

        # Close cache storage
        self.cache.close()

    def _get_image_cache_path(
        self, entity_type: str, entity_id: int, size: int, image_type: str = "portrait"
    ) -> Path:
        """Get the cache file path for an image.

        Args:
            entity_type: Type of entity ('characters', 'corporations', 'alliances', 'types')
            entity_id: Entity ID
            size: Image size (1024, 512, 256, 128, 64, 32)
            image_type: Type of image ('portrait', 'logo', 'icon', 'render')

        Returns:
            Path to cache file
        """
        # Create subdirectory for entity type
        entity_dir = self._image_cache_dir / entity_type
        entity_dir.mkdir(parents=True, exist_ok=True)

        # Use entity_id and size as filename
        filename = f"{entity_id}_{image_type}_{size}.png"
        return entity_dir / filename

    async def _get_image(
        self,
        entity_type: str,
        entity_id: int,
        size: int,
        image_type: str = "portrait",
        use_cache: bool = True,
    ) -> bytes | None:
        """Get an image from EVE image server with disk caching.

        Args:
            entity_type: Type of entity ('characters', 'corporations', 'alliances', 'types')
            entity_id: Entity ID
            size: Image size (1024, 512, 256, 128, 64, 32)
            image_type: Type of image ('portrait' for characters, 'logo' for corps/alliances, 'icon'/'render' for types)
            use_cache: Whether to use disk cache

        Returns:
            Image data as bytes, or None if not found

        Example:
            ```python
            # Get character portrait
            img_data = await client.get_image("characters", 96947097, 128, "portrait")

            # Get corporation logo
            img_data = await client.get_image("corporations", 98682702, 64, "logo")

            # Get alliance logo
            img_data = await client.get_image("alliances", 1900696668, 64, "logo")
            ```
        """
        await self._ensure_initialized()

        # Check disk cache first
        cache_path = self._get_image_cache_path(
            entity_type, entity_id, size, image_type
        )
        if use_cache and cache_path.exists():
            try:
                return cache_path.read_bytes()
            except OSError as e:
                logger.debug("Failed to read cached image %s: %s", cache_path, e)

        # Construct image URL
        # https://images.evetech.net/characters/{character_id}/portrait?tenant=tranquility&size=128
        # https://images.evetech.net/corporations/{corporation_id}/logo?tenant=tranquility&size=64
        # https://images.evetech.net/alliances/{alliance_id}/logo?tenant=tranquility&size=64
        # https://images.evetech.net/types/{type_id}/icon?tenant=tranquility&size=64
        image_url = f"https://images.evetech.net/{entity_type}/{entity_id}/{image_type}"

        try:
            # Request image from EVE image server
            data, _ = await self.request(
                "GET",
                "",  # Empty path since we're using full_url
                params={"tenant": self.datasource, "size": size},
                use_cache=False,  # Don't use ESI cache for images
                full_url=image_url,
            )

            if data and isinstance(data, bytes):
                # Save to disk cache
                if use_cache:
                    try:
                        cache_path.write_bytes(data)
                        logger.debug("Cached image: %s", cache_path)
                    except OSError as e:
                        logger.debug("Failed to cache image %s: %s", cache_path, e)

                return data

        except Exception as e:
            logger.debug(
                "Failed to fetch image: %s/%s/%s size=%d: %s",
                entity_type,
                entity_id,
                image_type,
                size,
                e,
            )

        return None

    async def get_image_with_fallback(
        self,
        entity_type: str,
        entity_id: int,
        image_type: str = "portrait",
        preferred_size: int = 1024,
        use_cache: bool = True,
    ) -> tuple[bytes | None, int | None]:
        """Get an image with automatic size fallback.

        Tries to get the image in the preferred size, falling back to larger sizes
        in order: 1024 -> 512 -> 256 -> 128 -> 64 -> 32

        Args:
            entity_type: Type of entity ('characters', 'corporations', 'alliances', 'types')
            entity_id: Entity ID
            image_type: Type of image ('portrait', 'logo', 'icon', 'render')
            preferred_size: Preferred image size (default: 1024)
            use_cache: Whether to use disk cache

        Returns:
            Tuple of (image_data, actual_size) or (None, None) if not found

        Example:
            ```python
            # Get character portrait, preferring 128 but accepting larger
            img_data, size = await client.get_image_with_fallback(
                "characters", 96947097, "portrait", 128
            )
            if img_data:
                print(f"Got image at size {size}")
            ```
        """
        # Size fallback order: prefer larger sizes (better quality)
        sizes = [1024, 512, 256, 128, 64, 32]

        # Reorder sizes to try preferred size first, then fall back to larger, then smaller
        preferred_index = (
            sizes.index(preferred_size) if preferred_size in sizes else 3
        )  # default to 128
        sizes_to_try = [
            *sizes[preferred_index::-1],  # larger sizes in descending order
            preferred_size,  # preferred size
            *sizes[preferred_index + 1 :],  # smaller sizes
        ]

        # Remove duplicates while preserving order
        seen = set()
        sizes_to_try = [x for x in sizes_to_try if not (x in seen or seen.add(x))]

        for size in sizes_to_try:
            img_data = await self._get_image(
                entity_type, entity_id, size, image_type, use_cache
            )
            if img_data:
                return img_data, size

        return None, None
