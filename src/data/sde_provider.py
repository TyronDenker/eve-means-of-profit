"""SDE Provider for high-level data access and caching."""

import asyncio
import logging
import os
import pickle
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from data.parsers import SDEJsonlParser
from models.eve import (
    EveCategory,
    EveGroup,
    EveMarketGroup,
    EveType,
)
from utils.config import get_config
from utils.progress_callback import ProgressCallback, ProgressPhase, ProgressUpdate

logger = logging.getLogger(__name__)


class SDEMetadata(TypedDict):
    """Metadata about when and how caches were built."""

    computed_at: str
    total_types: int
    total_groups: int
    total_categories: int
    total_market_groups: int
    total_npc_stations: int
    total_blueprint_types: int


# Minimum expected sizes for integrity validation
MIN_EXPECTED_CACHE_SIZES: dict[str, int] = {
    "types_cache": 1000,  # EVE has tens of thousands of types
    "groups_cache": 100,  # EVE has hundreds of groups
    "categories_cache": 10,  # EVE has dozens of categories
    "market_groups_cache": 100,  # EVE has hundreds of market groups
    "npc_stations_cache": 100,  # There are many NPC stations
}


class SDEProvider:
    """Provider for SDE data with caching and optimized query capabilities.

    This provider provides:
    - Primary caches: Direct ID lookups (O(1))
    - Index hashmaps: Fast filtered queries (O(1) for common filters)
    - Memory management: Clear caches when needed
    """

    def __init__(
        self,
        parser: SDEJsonlParser,
        *,
        background_build: bool = True,
        persist_path: str | Path | None = None,
        progress_callback: ProgressCallback | None = None,
    ):
        """Initialize the SDE provider.

        Args:
            parser: SDEJsonlParser instance for loading SDE data.
            background_build: Whether to build caches/indices in a background thread.
            persist_path: Optional path to persist/load prebuilt caches/indices.
            progress_callback: Optional callback for progress updates during builds.
        """
        self._parser = parser
        self._progress_callback = progress_callback

        # Primary caches - ID-based lookups (dict[id, object])
        self._types_cache: dict[int, EveType] | None = None
        self._categories_cache: dict[int, EveCategory] | None = None
        self._groups_cache: dict[int, EveGroup] | None = None
        self._market_groups_cache: dict[int, EveMarketGroup] | None = None
        self._npc_stations_cache: set[int] | None = None

        # Location name caches
        self._npc_station_names_cache: dict[int, str] | None = None
        self._npc_station_system_ids_cache: dict[int, int] | None = None
        self._region_names_cache: dict[int, str] | None = None
        self._constellation_names_cache: dict[int, str] | None = None
        self._solar_system_names_cache: dict[int, str] | None = None
        self._solar_system_constellation_ids_cache: dict[int, int] | None = None
        self._constellation_region_ids_cache: dict[int, int] | None = None

        # Index hashmaps - for fast filtered queries
        # Format: dict[filter_value, list[object_id]]
        # These are always built when their corresponding cache is loaded
        self._types_by_group_index: dict[int, list[int]] | None = None
        self._types_by_category_index: dict[int, list[int]] | None = None
        self._types_by_market_group_index: dict[int, list[int]] | None = None
        self._published_types_ids: set[int] | None = None
        self._groups_by_category_index: dict[int, list[int]] | None = None

        # Blueprint type IDs cache
        self._blueprint_type_ids_cache: set[int] | None = None

        # SDE metadata
        self._sde_metadata: SDEMetadata | None = None

        # Persistence / background build
        self._persist_path: Path = Path(
            persist_path or (get_config().app.user_data_dir / "sde_indices.pkl")
        )
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.debug(
                "Could not create persist directory for SDE indices", exc_info=True
            )

        self._background_ready = threading.Event()
        # Attempt to load persisted caches; if not available, build in background.
        if self._load_persisted_indices():
            self._background_ready.set()
        elif background_build:
            thread = threading.Thread(
                target=self._build_and_persist_background,
                name="sde-background-build",
                daemon=True,
            )
            thread.start()
        else:
            # Synchronous fallback
            self._build_all_indices_sync()
            self._persist_indices()
            self._background_ready.set()

    def get_type_by_id(self, type_id: int) -> EveType | None:
        """Get a type by its ID.

        Args:
            type_id: The type ID to look up

        Returns:
            EveType object or None if not found

        """
        return self._load_types().get(type_id)

    def get_group_by_id(self, group_id: int) -> EveGroup | None:
        """Get a group by its ID.

        Args:
            group_id: The group ID to look up

        Returns:
            EveGroup object or None if not found

        """
        return self._load_groups().get(group_id)

    def get_category_by_id(self, category_id: int) -> EveCategory | None:
        """Get a category by its ID.

        Args:
            category_id: The category ID to look up

        Returns:
            EveCategory object or None if not found

        """
        return self._load_categories().get(category_id)

    def get_market_group_by_id(self, market_group_id: int) -> EveMarketGroup | None:
        """Get a market group by its ID.

        Args:
            market_group_id: The market group ID to look up

        Returns:
            EveMarketGroup object or None if not found

        """
        return self._load_market_groups().get(market_group_id)

    def get_types_by_group(self, group_id: int) -> list[EveType]:
        """Get all types belonging to a specific group.

        Uses O(1) hashmap lookup for optimal performance.

        Args:
            group_id: The group ID to filter by

        Returns:
            List of EveType objects in the group

        """
        types_cache = self._load_types()
        # _load_types ensures indices are built
        index = self._types_by_group_index or {}
        type_ids = index.get(group_id, [])
        return [types_cache[tid] for tid in type_ids]

    def get_types_by_category(self, category_id: int) -> list[EveType]:
        """Get all types belonging to a specific category.

        Uses O(1) hashmap lookup for optimal performance.

        Args:
            category_id: The category ID to filter by

        Returns:
            List of EveType objects in the category

        """
        types_cache = self._load_types()
        # _load_types ensures indices are built
        index = self._types_by_category_index or {}
        type_ids = index.get(category_id, [])
        return [types_cache[tid] for tid in type_ids]

    def get_types_by_market_group(self, market_group_id: int) -> list[EveType]:
        """Get all types in a specific market group.

        Uses O(1) hashmap lookup for optimal performance.

        Args:
            market_group_id: The market group ID to filter by

        Returns:
            List of EveType objects in the market group

        """
        types_cache = self._load_types()
        # _load_types ensures indices are built
        index = self._types_by_market_group_index or {}
        type_ids = index.get(market_group_id, [])
        return [types_cache[tid] for tid in type_ids]

    def get_published_types(self) -> list[EveType]:
        """Get all published types.

        Uses O(1) hashmap lookup for optimal performance.

        Returns:
            List of published EveType objects

        """
        types_cache = self._load_types()
        # _load_types ensures indices are built
        published_ids = self._published_types_ids or set()
        return [types_cache[tid] for tid in published_ids]

    def get_all_types(self) -> list[EveType]:
        """Get all types.

        Returns:
            List of all EveType objects

        """
        return list(self._load_types().values())

    def get_all_categories(self) -> list[EveCategory]:
        """Get all categories.

        Returns:
            List of all EveCategory objects

        """
        return list(self._load_categories().values())

    def get_all_groups(self) -> list[EveGroup]:
        """Get all groups.

        Returns:
            List of all EveGroup objects

        """
        return list(self._load_groups().values())

    def get_groups_by_category(self, category_id: int) -> list[EveGroup]:
        """Get all groups belonging to a specific category.

        Uses O(1) hashmap lookup for optimal performance.

        Args:
            category_id: The category ID to filter by

        Returns:
            List of EveGroup objects in the category

        """
        groups_cache = self._load_groups()
        # _load_groups ensures indices are built
        index = self._groups_by_category_index or {}
        group_ids = index.get(category_id, [])
        return [groups_cache[gid] for gid in group_ids]

    def is_npc_station(self, station_id: int) -> bool:
        """Check if a station ID is an NPC station.

        Args:
            station_id: Station ID to check

        Returns:
            True if the station is an NPC station
        """
        return station_id in self._load_npc_stations()

    def get_npc_stations(self) -> set[int]:
        """Get all NPC station IDs.

        Returns:
            Set of all NPC station IDs
        """
        return self._load_npc_stations().copy()

    def is_blueprint(self, type_id: int) -> bool:
        """Check if a type ID is a blueprint.

        Args:
            type_id: Type ID to check

        Returns:
            True if the type is a blueprint
        """
        return type_id in self._load_blueprint_type_ids()

    def get_blueprint_type_ids(self) -> set[int]:
        """Get all blueprint type IDs.

        Returns:
            Set of all blueprint type IDs
        """
        return self._load_blueprint_type_ids().copy()

    def get_npc_station_name(self, station_id: int) -> str | None:
        """Get NPC station name by ID.

        Args:
            station_id: Station ID to look up

        Returns:
            Station name or None if not found
        """
        return self._load_npc_station_names().get(station_id)

    def get_npc_station_system_id(self, station_id: int) -> int | None:
        """Get NPC station's solar system ID by station ID.

        Args:
            station_id: Station ID to look up

        Returns:
            Solar system ID or None if not found
        """
        # Load station system mapping
        station_systems = self._load_npc_station_system_ids()
        return station_systems.get(station_id)

    def get_region_name(self, region_id: int) -> str | None:
        """Get region name by ID.

        Args:
            region_id: Region ID to look up

        Returns:
            Region name or None if not found
        """
        return self._load_region_names().get(region_id)

    def get_constellation_name(self, constellation_id: int) -> str | None:
        """Get constellation name by ID.

        Args:
            constellation_id: Constellation ID to look up

        Returns:
            Constellation name or None if not found
        """
        return self._load_constellation_names().get(constellation_id)

    def get_solar_system_name(self, system_id: int) -> str | None:
        """Get solar system name by ID.

        Args:
            system_id: Solar system ID to look up

        Returns:
            Solar system name or None if not found
        """
        return self._load_solar_system_names().get(system_id)

    def get_solar_system_constellation_id(self, system_id: int) -> int | None:
        """Get constellation ID for a solar system.

        Args:
            system_id: Solar system ID to look up

        Returns:
            Constellation ID or None if not found
        """
        return self._load_solar_system_constellation_ids().get(system_id)

    def get_constellation_region_id(self, constellation_id: int) -> int | None:
        """Get region ID for a constellation.

        Args:
            constellation_id: Constellation ID to look up

        Returns:
            Region ID or None if not found
        """
        return self._load_constellation_region_ids().get(constellation_id)

    def get_all_solar_systems(self) -> dict[int, str]:
        """Get all solar systems.

        Returns:
            Dictionary mapping solar system ID to name
        """
        return self._load_solar_system_names()

    def clear_cache(self) -> None:
        """Clear all cached data to free memory.

        All caches are set to None for consistency with fresh state.
        """
        logger.info("Clearing SDE cache...")

        # Clear primary caches
        self._types_cache = None
        self._categories_cache = None
        self._groups_cache = None
        self._market_groups_cache = None
        self._npc_stations_cache = None
        self._blueprint_type_ids_cache = None

        # Clear location name caches
        self._npc_station_names_cache = None
        self._npc_station_system_ids_cache = None
        self._region_names_cache = None
        self._constellation_names_cache = None
        self._solar_system_names_cache = None
        self._solar_system_constellation_ids_cache = None
        self._constellation_region_ids_cache = None

        # Clear index hashmaps (set to None for consistency)
        self._types_by_group_index = None
        self._types_by_category_index = None
        self._types_by_market_group_index = None
        self._published_types_ids = None
        self._groups_by_category_index = None

        # Clear metadata
        self._sde_metadata = None

        logger.info("Cache cleared")

    @property
    def is_loaded(self) -> bool:
        """Check if any data has been loaded.

        Returns:
            True if any cache is populated

        """
        return any(
            [
                self._types_cache is not None,
                self._categories_cache is not None,
                self._groups_cache is not None,
                self._market_groups_cache is not None,
                self._npc_stations_cache is not None,
                self._blueprint_type_ids_cache is not None,
            ]
        )

    def get_cache_stats(self) -> dict[str, int | bool]:
        """Get statistics about cached data.

        Returns:
            Dictionary with cache sizes and index status

        """
        return {
            "types": len(self._types_cache) if self._types_cache else 0,
            "categories": len(self._categories_cache) if self._categories_cache else 0,
            "groups": len(self._groups_cache) if self._groups_cache else 0,
            "market_groups": (
                len(self._market_groups_cache) if self._market_groups_cache else 0
            ),
            "npc_stations": (
                len(self._npc_stations_cache) if self._npc_stations_cache else 0
            ),
            "blueprint_types": (
                len(self._blueprint_type_ids_cache)
                if self._blueprint_type_ids_cache
                else 0
            ),
            "indices_built": (
                self._types_by_group_index is not None
                and len(self._types_by_group_index) > 0
            ),
        }

    def get_sde_metadata(self) -> SDEMetadata | None:
        """Get metadata about the SDE cache.

        Returns:
            SDEMetadata dictionary or None if not computed yet
        """
        return self._sde_metadata

    # ------------------------------------------------------------------
    # Persistence / background helpers
    # ------------------------------------------------------------------
    def wait_until_ready(self, timeout: float | None = None) -> bool:
        """Block until background build/persisted load completes.

        Returns True if ready before timeout, False otherwise.
        """

        return self._background_ready.wait(timeout=timeout)

    def _build_and_persist_background(self) -> None:
        try:
            self._emit_progress(
                ProgressPhase.STARTING, 0, 100, "Building SDE indices..."
            )
            self._build_all_indices_sync()
            self._emit_progress(ProgressPhase.SAVING, 90, 100, "Persisting indices...")
            self._persist_indices()
            self._emit_progress(ProgressPhase.COMPLETE, 100, 100, "SDE ready")
        except Exception:
            logger.exception("Background SDE build failed")
            self._emit_progress(ProgressPhase.ERROR, 0, 100, "SDE build failed")
        finally:
            self._background_ready.set()

    def _check_sde_changed(self, old_metadata: SDEMetadata | None) -> bool:
        """Check if SDE source files have changed since cache was built.

        Uses a simple heuristic: if max mtime of any .jsonl file is newer than
        the cache computed_at timestamp, rebuild everything. This is simpler and
        more robust than per-file tracking for a data set that changes rarely.

        Args:
            old_metadata: Previously stored SDE metadata with computed_at timestamp

        Returns:
            True if SDE files appear to have changed, False otherwise.
        """
        if old_metadata is None:
            # No previous metadata - rebuild
            return True

        base = getattr(self._parser, "file_path", None)
        if not base:
            return False

        base_path = Path(base)
        if not base_path.exists():
            return False

        try:
            # Parse the cached timestamp
            cached_time = datetime.fromisoformat(old_metadata["computed_at"])

            # Check if any .jsonl file is newer than cache
            for path in base_path.glob("*.jsonl"):
                try:
                    file_mtime = path.stat().st_mtime
                    file_time = datetime.fromtimestamp(file_mtime, tz=UTC)
                    if file_time > cached_time:
                        logger.debug(
                            f"SDE file changed: {path.name} mtime {file_time} > cache time {cached_time}"
                        )
                        return True
                except OSError:
                    continue
        except Exception:
            logger.debug(
                "Error checking SDE changes; assuming no change", exc_info=True
            )
            return False

        return False

    def _compute_sde_metadata(self) -> SDEMetadata:
        """Compute metadata about the current SDE cache state.

        Returns:
            SDEMetadata with counts and timestamp.
        """
        return SDEMetadata(
            computed_at=datetime.now(UTC).isoformat(),
            total_types=len(self._types_cache) if self._types_cache else 0,
            total_groups=len(self._groups_cache) if self._groups_cache else 0,
            total_categories=(
                len(self._categories_cache) if self._categories_cache else 0
            ),
            total_market_groups=(
                len(self._market_groups_cache) if self._market_groups_cache else 0
            ),
            total_npc_stations=(
                len(self._npc_stations_cache) if self._npc_stations_cache else 0
            ),
            total_blueprint_types=(
                len(self._blueprint_type_ids_cache)
                if self._blueprint_type_ids_cache
                else 0
            ),
        )

    def _persist_indices(self) -> None:
        if not self._types_cache:
            return

        # Compute metadata (includes computed_at timestamp)
        self._sde_metadata = self._compute_sde_metadata()

        payload = {
            # SDE metadata - includes computed_at for change detection
            "sde_metadata": self._sde_metadata,
            # Caches
            "types_cache": self._types_cache,
            "categories_cache": self._categories_cache,
            "groups_cache": self._groups_cache,
            "market_groups_cache": self._market_groups_cache,
            "npc_stations_cache": self._npc_stations_cache,
            "npc_station_names_cache": self._npc_station_names_cache,
            "npc_station_system_ids_cache": self._npc_station_system_ids_cache,
            "region_names_cache": self._region_names_cache,
            "constellation_names_cache": self._constellation_names_cache,
            "solar_system_names_cache": self._solar_system_names_cache,
            "solar_system_constellation_ids_cache": self._solar_system_constellation_ids_cache,
            "constellation_region_ids_cache": self._constellation_region_ids_cache,
            "types_by_group_index": self._types_by_group_index,
            "types_by_category_index": self._types_by_category_index,
            "types_by_market_group_index": self._types_by_market_group_index,
            "published_types_ids": self._published_types_ids,
            "groups_by_category_index": self._groups_by_category_index,
            "blueprint_type_ids_cache": self._blueprint_type_ids_cache,
        }

        try:
            tmp_path = self._persist_path.with_suffix(".tmp")
            with open(tmp_path, "wb") as f:
                pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, self._persist_path)
            logger.debug("Persisted SDE caches to %s", self._persist_path)
        except Exception:
            logger.debug("Failed to persist SDE caches", exc_info=True)

    def _validate_cache_integrity(self, payload: dict) -> bool:
        """Validate that loaded cache data meets integrity requirements.

        Args:
            payload: The loaded pickle payload

        Returns:
            True if all integrity checks pass, False otherwise.
        """
        # Check all expected cache keys are present
        expected_keys = [
            "types_cache",
            "categories_cache",
            "groups_cache",
            "market_groups_cache",
            "npc_stations_cache",
        ]

        for key in expected_keys:
            if key not in payload or payload[key] is None:
                logger.debug(f"Cache integrity check failed: missing key '{key}'")
                return False

        # Check minimum expected sizes for critical caches (warning only)
        # Small datasets (like test data) are allowed but logged
        for cache_key, min_size in MIN_EXPECTED_CACHE_SIZES.items():
            cache = payload.get(cache_key)
            if cache is not None and len(cache) < min_size:
                logger.debug(
                    f"Cache integrity note: '{cache_key}' has {len(cache)} items, "
                    f"typical SDE has at least {min_size}. This may be test data."
                )
                # Don't fail - small datasets are valid (e.g., tests)

        # Validate index consistency with their source caches
        types_cache = payload.get("types_cache")
        types_by_group = payload.get("types_by_group_index", {})
        if types_cache and types_by_group:
            # Sample check: ensure indexed type IDs exist in types cache
            for type_ids in list(types_by_group.values())[:10]:
                for tid in type_ids[:5]:
                    if tid not in types_cache:
                        logger.debug(
                            f"Cache integrity check: type_id {tid} in index but not in cache"
                        )
                        return False

        return True

    def _load_persisted_indices(self) -> bool:
        if not self._persist_path.exists():
            return False
        try:
            with open(self._persist_path, "rb") as f:
                payload = pickle.load(f)

            # Check if SDE source files have changed since cache was built
            sde_metadata = payload.get("sde_metadata")
            if self._check_sde_changed(sde_metadata):
                logger.info("SDE source files have changed; rebuilding all caches")
                return False

            # Validate integrity before loading
            if not self._validate_cache_integrity(payload):
                logger.warning("Cache integrity validation failed; rebuilding")
                return False

            # Load all caches from payload
            self._types_cache = payload.get("types_cache")
            self._categories_cache = payload.get("categories_cache")
            self._groups_cache = payload.get("groups_cache")
            self._market_groups_cache = payload.get("market_groups_cache")
            self._npc_stations_cache = payload.get("npc_stations_cache")
            self._npc_station_names_cache = payload.get("npc_station_names_cache")
            self._npc_station_system_ids_cache = payload.get(
                "npc_station_system_ids_cache"
            )
            self._region_names_cache = payload.get("region_names_cache")
            self._solar_system_constellation_ids_cache = payload.get(
                "solar_system_constellation_ids_cache"
            )
            self._constellation_region_ids_cache = payload.get(
                "constellation_region_ids_cache"
            )
            self._constellation_names_cache = payload.get("constellation_names_cache")
            self._solar_system_names_cache = payload.get("solar_system_names_cache")
            self._types_by_group_index = payload.get("types_by_group_index")
            self._types_by_category_index = payload.get("types_by_category_index")
            self._types_by_market_group_index = payload.get(
                "types_by_market_group_index"
            )
            self._published_types_ids = payload.get("published_types_ids")
            self._groups_by_category_index = payload.get("groups_by_category_index")
            self._blueprint_type_ids_cache = payload.get("blueprint_type_ids_cache")
            self._sde_metadata = sde_metadata

            logger.info(
                "Loaded SDE caches from persisted file (%s)", self._persist_path
            )
            return True
        except Exception:
            logger.debug(
                "Failed to load persisted SDE caches; will rebuild", exc_info=True
            )
            return False

    def _build_all_indices_sync(self) -> None:
        # Force load everything to build indices once
        self._load_types()
        self._load_categories()
        self._load_groups()
        self._load_market_groups()
        self._load_npc_stations()
        self._load_npc_station_names()
        self._load_npc_station_system_ids()
        self._load_region_names()
        self._load_solar_system_constellation_ids()
        self._load_constellation_region_ids()
        self._load_constellation_names()
        self._load_solar_system_names()
        self._load_blueprint_type_ids()

    def _load_blueprint_type_ids(self) -> set[int]:
        """Load and cache blueprint type IDs.

        Returns:
            Set of type IDs that are blueprints
        """
        if self._blueprint_type_ids_cache is None:
            logger.info("Loading blueprint type IDs from SDE...")
            self._blueprint_type_ids_cache = self._parser.load_blueprint_type_ids()
            logger.info(f"Loaded {len(self._blueprint_type_ids_cache)} blueprint types")
        return self._blueprint_type_ids_cache

    def _load_npc_station_names(self) -> dict[int, str]:
        """Load and cache NPC station names.

        Returns:
            Dictionary mapping station ID to name
        """
        if self._npc_station_names_cache is None:
            logger.info("Loading NPC station names from SDE...")
            self._npc_station_names_cache = self._parser.load_npc_station_names()
            logger.info(
                f"Loaded {len(self._npc_station_names_cache)} NPC station names"
            )
        return self._npc_station_names_cache

    def _load_npc_station_system_ids(self) -> dict[int, int]:
        """Load and cache NPC station to system ID mapping.

        Returns:
            Dictionary mapping station ID to solar system ID
        """
        if self._npc_station_system_ids_cache is None:
            logger.info("Loading NPC station system IDs from SDE...")
            self._npc_station_system_ids_cache = (
                self._parser.load_npc_station_system_ids()
            )
            logger.info(
                f"Loaded {len(self._npc_station_system_ids_cache)} station-system mappings"
            )
        return self._npc_station_system_ids_cache

    def _load_region_names(self) -> dict[int, str]:
        """Load and cache region names.

        Returns:
            Dictionary mapping region ID to name
        """
        if self._region_names_cache is None:
            logger.info("Loading region names from SDE...")
            self._region_names_cache = self._parser.load_region_names()
            logger.info(f"Loaded {len(self._region_names_cache)} region names")
        return self._region_names_cache

    def _load_constellation_names(self) -> dict[int, str]:
        """Load and cache constellation names.

        Returns:
            Dictionary mapping constellation ID to name
        """
        if self._constellation_names_cache is None:
            logger.info("Loading constellation names from SDE...")
            self._constellation_names_cache = self._parser.load_constellation_names()
            logger.info(
                f"Loaded {len(self._constellation_names_cache)} constellation names"
            )
        return self._constellation_names_cache

    def _load_solar_system_names(self) -> dict[int, str]:
        """Load and cache solar system names.

        Returns:
            Dictionary mapping solar system ID to name
        """
        if self._solar_system_names_cache is None:
            logger.info("Loading solar system names from SDE...")
            self._solar_system_names_cache = self._parser.load_solar_system_names()
            logger.info(
                f"Loaded {len(self._solar_system_names_cache)} solar system names"
            )
        return self._solar_system_names_cache

    def _load_solar_system_constellation_ids(self) -> dict[int, int]:
        """Load and cache solar system to constellation ID mapping.

        Returns:
            Dictionary mapping solar system ID to constellation ID
        """
        if self._solar_system_constellation_ids_cache is None:
            logger.info("Loading solar system constellation IDs from SDE...")
            self._solar_system_constellation_ids_cache = (
                self._parser.load_solar_system_constellation_ids()
            )
            logger.info(
                f"Loaded {len(self._solar_system_constellation_ids_cache)} system-constellation mappings"
            )
        return self._solar_system_constellation_ids_cache

    def _load_constellation_region_ids(self) -> dict[int, int]:
        """Load and cache constellation to region ID mapping.

        Returns:
            Dictionary mapping constellation ID to region ID
        """
        if self._constellation_region_ids_cache is None:
            logger.info("Loading constellation region IDs from SDE...")
            self._constellation_region_ids_cache = (
                self._parser.load_constellation_region_ids()
            )
            logger.info(
                f"Loaded {len(self._constellation_region_ids_cache)} constellation-region mappings"
            )
        return self._constellation_region_ids_cache

    def _load_types(self) -> dict[int, EveType]:
        """Load and cache all types."""
        if self._types_cache is None:
            logger.info("Loading types from SDE...")
            self._types_cache = {t.type_id: t for t in self._parser.load_types()}
            logger.info(f"Loaded {len(self._types_cache)} types")
            self._build_type_indices()
        return self._types_cache

    def _build_type_indices(self) -> None:
        """Build hashmap indices for fast type lookups.

        This builds O(1) lookup tables for common queries.
        Ensures groups are loaded before building category index.
        Must only be called after _types_cache is populated.
        """
        assert self._types_cache is not None, (
            "Types cache must be loaded before building indices"
        )

        logger.debug("Building type indices...")

        # Ensure groups are loaded for category index
        self._load_groups()
        assert self._groups_cache is not None

        # Clear and rebuild indices
        groups_index: dict[int, list[int]] = defaultdict(list)
        categories_index: dict[int, list[int]] = defaultdict(list)
        market_groups_index: dict[int, list[int]] = defaultdict(list)
        published_ids: set[int] = set()

        # Build all indices in single pass
        for type_id, type_obj in self._types_cache.items():
            # Group index
            if type_obj.group_id is not None:
                groups_index[type_obj.group_id].append(type_id)

                # Category index (requires group lookup)
                group = self._groups_cache.get(type_obj.group_id)
                if group:
                    categories_index[group.category_id].append(type_id)

            # Market group index
            if type_obj.market_group_id is not None:
                market_groups_index[type_obj.market_group_id].append(type_id)

            # Published index
            if type_obj.published:
                published_ids.add(type_id)

        # Assign built indices
        self._types_by_group_index = dict(groups_index)
        self._types_by_category_index = dict(categories_index)
        self._types_by_market_group_index = dict(market_groups_index)
        self._published_types_ids = published_ids

        logger.debug("Type indices built successfully")

    def _load_categories(self) -> dict[int, EveCategory]:
        """Load and cache all categories."""
        if self._categories_cache is None:
            logger.info("Loading categories from SDE...")
            self._categories_cache = {
                c.category_id: c for c in self._parser.load_categories()
            }
            logger.info(f"Loaded {len(self._categories_cache)} categories")
        return self._categories_cache

    def _load_groups(self) -> dict[int, EveGroup]:
        """Load and cache all groups."""
        if self._groups_cache is None:
            logger.info("Loading groups from SDE...")
            self._groups_cache = {g.group_id: g for g in self._parser.load_groups()}
            logger.info(f"Loaded {len(self._groups_cache)} groups")
            self._build_group_indices()
        return self._groups_cache

    def _build_group_indices(self) -> None:
        """Build hashmap indices for fast group lookups.

        Must only be called after _groups_cache is populated.
        """
        assert self._groups_cache is not None, (
            "Groups cache must be loaded before building indices"
        )

        logger.debug("Building group indices...")

        # Clear and rebuild index
        categories_index: dict[int, list[int]] = defaultdict(list)

        for group_id, group in self._groups_cache.items():
            categories_index[group.category_id].append(group_id)

        # Assign built index
        self._groups_by_category_index = dict(categories_index)

        logger.debug("Group indices built successfully")

    def _load_market_groups(self) -> dict[int, EveMarketGroup]:
        """Load and cache all market groups."""
        if self._market_groups_cache is None:
            logger.info("Loading market groups from SDE...")
            self._market_groups_cache = {
                mg.marketgroup_id: mg for mg in self._parser.load_market_groups()
            }
            logger.info(f"Loaded {len(self._market_groups_cache)} market groups")
        return self._market_groups_cache

    def _load_npc_stations(self) -> set[int]:
        """Load and cache all NPC station IDs.

        Returns:
            Set of NPC station IDs from npcStations.jsonl
        """
        if self._npc_stations_cache is None:
            logger.info("Loading NPC stations from SDE...")
            self._npc_stations_cache = self._parser.load_npc_station_ids()
            logger.info(f"Loaded {len(self._npc_stations_cache)} NPC stations")
        return self._npc_stations_cache

    def _emit_progress(
        self,
        phase: ProgressPhase,
        current: int,
        total: int,
        message: str,
        detail: str | None = None,
    ) -> None:
        """Emit progress update if callback is configured.

        Args:
            phase: Current phase of operation.
            current: Current progress value.
            total: Total progress value.
            message: Status message.
            detail: Optional detail message.
        """
        if self._progress_callback:
            update = ProgressUpdate(
                operation="sde_build",
                character_id=None,
                phase=phase,
                current=current,
                total=total,
                message=message,
                detail=detail,
            )
            self._progress_callback(update)

    async def initialize_async(self) -> None:
        """Initialize SDE provider asynchronously.

        This method runs blocking I/O operations in a thread pool to avoid
        blocking the async event loop during startup.
        """
        self._emit_progress(ProgressPhase.STARTING, 0, 100, "Initializing SDE...")

        # Run blocking operations in thread pool
        loop = asyncio.get_event_loop()

        # Check if persisted indices exist
        if self._persist_path.exists():
            self._emit_progress(
                ProgressPhase.FETCHING, 10, 100, "Loading cached indices..."
            )
            loaded = await loop.run_in_executor(None, self._load_persisted_indices)
            if loaded:
                self._emit_progress(
                    ProgressPhase.COMPLETE, 100, 100, "SDE loaded from cache"
                )
                self._background_ready.set()
                return

        # Build indices in thread pool
        self._emit_progress(ProgressPhase.PROCESSING, 30, 100, "Building indices...")
        await loop.run_in_executor(None, self._build_all_indices_sync)

        self._emit_progress(ProgressPhase.SAVING, 90, 100, "Persisting indices...")
        await loop.run_in_executor(None, self._persist_indices)

        self._emit_progress(ProgressPhase.COMPLETE, 100, 100, "SDE initialized")
        self._background_ready.set()
