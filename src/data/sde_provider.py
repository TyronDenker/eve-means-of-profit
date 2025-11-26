"""SDE Provider for high-level data access and caching."""

import logging
from collections import defaultdict

from data.parsers import SDEJsonlParser
from models.eve import (
    EveCategory,
    EveGroup,
    EveMarketGroup,
    EveType,
)

logger = logging.getLogger(__name__)


class SDEProvider:
    """Provider for SDE data with caching and optimized query capabilities.

    This provider provides:
    - Primary caches: Direct ID lookups (O(1))
    - Index hashmaps: Fast filtered queries (O(1) for common filters)
    - Memory management: Clear caches when needed
    """

    def __init__(self, parser: SDEJsonlParser):
        """Initialize the SDE provider.

        Args:
            parser: SDEJsonlParser instance for loading SDE data.

        """
        self._parser = parser

        # Primary caches - ID-based lookups (dict[id, object])
        self._types_cache: dict[int, EveType] | None = None
        self._categories_cache: dict[int, EveCategory] | None = None
        self._groups_cache: dict[int, EveGroup] | None = None
        self._market_groups_cache: dict[int, EveMarketGroup] | None = None
        self._npc_stations_cache: set[int] | None = None

        # Location name caches
        self._npc_station_names_cache: dict[int, str] | None = None
        self._region_names_cache: dict[int, str] | None = None
        self._constellation_names_cache: dict[int, str] | None = None
        self._solar_system_names_cache: dict[int, str] | None = None

        # Index hashmaps - for fast filtered queries
        # Format: dict[filter_value, list[object_id]]
        # These are always built when their corresponding cache is loaded
        self._types_by_group_index: dict[int, list[int]] = {}
        self._types_by_category_index: dict[int, list[int]] = {}
        self._types_by_market_group_index: dict[int, list[int]] = {}
        self._published_types_ids: set[int] = set()
        self._groups_by_category_index: dict[int, list[int]] = {}

        # Blueprint type IDs cache
        self._blueprint_type_ids_cache: set[int] | None = None

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
        type_ids = self._types_by_group_index.get(group_id, [])
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
        type_ids = self._types_by_category_index.get(category_id, [])
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
        type_ids = self._types_by_market_group_index.get(market_group_id, [])
        return [types_cache[tid] for tid in type_ids]

    def get_published_types(self) -> list[EveType]:
        """Get all published types.

        Uses O(1) hashmap lookup for optimal performance.

        Returns:
            List of published EveType objects

        """
        types_cache = self._load_types()
        return [types_cache[tid] for tid in self._published_types_ids]

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
        group_ids = self._groups_by_category_index.get(category_id, [])
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

    def clear_cache(self) -> None:
        """Clear all cached data to free memory."""
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
        self._region_names_cache = None
        self._constellation_names_cache = None
        self._solar_system_names_cache = None

        # Clear index hashmaps (reset to empty, not None)
        self._types_by_group_index = {}
        self._types_by_category_index = {}
        self._types_by_market_group_index = {}
        self._published_types_ids = set()
        self._groups_by_category_index = {}

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
            "indices_built": len(self._types_by_group_index) > 0,
        }

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
