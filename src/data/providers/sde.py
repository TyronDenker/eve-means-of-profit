"""SDE Provider for high-level data access and caching."""

import logging
from collections import defaultdict

from data.parsers.sde_jsonl import SDEJsonlParser
from models.eve import (
    EveBlueprint,
    EveCategory,
    EveDogmaAttribute,
    EveDogmaAttributeCategory,
    EveDogmaEffect,
    EveDogmaUnit,
    EveGroup,
    EveMarketGroup,
    EveType,
    EveTypeMaterial,
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
        self._blueprints_cache: dict[int, EveBlueprint] | None = None
        self._categories_cache: dict[int, EveCategory] | None = None
        self._groups_cache: dict[int, EveGroup] | None = None
        self._market_groups_cache: dict[int, EveMarketGroup] | None = None
        self._type_materials_cache: dict[int, EveTypeMaterial] | None = None
        self._dogma_attributes_cache: dict[int, EveDogmaAttribute] | None = None
        self._dogma_effects_cache: dict[int, EveDogmaEffect] | None = None
        self._dogma_units_cache: dict[int, EveDogmaUnit] | None = None
        self._dogma_attr_categories_cache: (
            dict[int, EveDogmaAttributeCategory] | None
        ) = None

        # Index hashmaps - for fast filtered queries
        # Format: dict[filter_value, list[object_id]]
        # These are always built when their corresponding cache is loaded
        self._types_by_group_index: dict[int, list[int]] = {}
        self._types_by_category_index: dict[int, list[int]] = {}
        self._types_by_market_group_index: dict[int, list[int]] = {}
        self._published_types_ids: set[int] = set()
        self._groups_by_category_index: dict[int, list[int]] = {}

    def _load_types(self) -> dict[int, EveType]:
        """Load and cache all types."""
        if self._types_cache is None:
            logger.info("Loading types from SDE...")
            self._types_cache = {t.id: t for t in self._parser.load_types()}
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

    def _load_blueprints(self) -> dict[int, EveBlueprint]:
        """Load and cache all blueprints."""
        if self._blueprints_cache is None:
            logger.info("Loading blueprints from SDE...")
            self._blueprints_cache = {
                bp.id: bp for bp in self._parser.load_blueprints()
            }
            logger.info(f"Loaded {len(self._blueprints_cache)} blueprints")
        return self._blueprints_cache

    def _load_categories(self) -> dict[int, EveCategory]:
        """Load and cache all categories."""
        if self._categories_cache is None:
            logger.info("Loading categories from SDE...")
            self._categories_cache = {c.id: c for c in self._parser.load_categories()}
            logger.info(f"Loaded {len(self._categories_cache)} categories")
        return self._categories_cache

    def _load_groups(self) -> dict[int, EveGroup]:
        """Load and cache all groups."""
        if self._groups_cache is None:
            logger.info("Loading groups from SDE...")
            self._groups_cache = {g.id: g for g in self._parser.load_groups()}
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
                mg.id: mg for mg in self._parser.load_market_groups()
            }
            logger.info(f"Loaded {len(self._market_groups_cache)} market groups")
        return self._market_groups_cache

    def _load_type_materials(self) -> dict[int, EveTypeMaterial]:
        """Load and cache all type materials."""
        if self._type_materials_cache is None:
            logger.info("Loading type materials from SDE...")
            self._type_materials_cache = {
                tm.id: tm for tm in self._parser.load_type_materials()
            }
            logger.info(f"Loaded {len(self._type_materials_cache)} type materials")
        return self._type_materials_cache

    def _load_dogma_attributes(self) -> dict[int, EveDogmaAttribute]:
        """Load and cache all dogma attributes."""
        if self._dogma_attributes_cache is None:
            logger.info("Loading dogma attributes from SDE...")
            self._dogma_attributes_cache = {
                da.id: da for da in self._parser.load_dogma_attributes()
            }
            logger.info(f"Loaded {len(self._dogma_attributes_cache)} dogma attrs")
        return self._dogma_attributes_cache

    def _load_dogma_effects(self) -> dict[int, EveDogmaEffect]:
        """Load and cache all dogma effects."""
        if self._dogma_effects_cache is None:
            logger.info("Loading dogma effects from SDE...")
            self._dogma_effects_cache = {
                de.id: de for de in self._parser.load_dogma_effects()
            }
            logger.info(f"Loaded {len(self._dogma_effects_cache)} dogma effects")
        return self._dogma_effects_cache

    def _load_dogma_units(self) -> dict[int, EveDogmaUnit]:
        """Load and cache all dogma units."""
        if self._dogma_units_cache is None:
            logger.info("Loading dogma units from SDE...")
            self._dogma_units_cache = {
                du.id: du for du in self._parser.load_dogma_units()
            }
            logger.info(f"Loaded {len(self._dogma_units_cache)} dogma units")
        return self._dogma_units_cache

    def _load_dogma_attribute_categories(
        self,
    ) -> dict[int, EveDogmaAttributeCategory]:
        """Load and cache all dogma attribute categories."""
        if self._dogma_attr_categories_cache is None:
            logger.info("Loading dogma attribute categories from SDE...")
            self._dogma_attr_categories_cache = {
                dac.id: dac for dac in self._parser.load_dogma_attribute_categories()
            }
            logger.info(
                f"Loaded {len(self._dogma_attr_categories_cache)} dogma attr categories"
            )
        return self._dogma_attr_categories_cache

    # Public query methods

    def get_type_by_id(self, type_id: int) -> EveType | None:
        """Get a type by its ID.

        Args:
            type_id: The type ID to look up

        Returns:
            EveType object or None if not found

        """
        return self._load_types().get(type_id)

    def get_blueprint_by_id(self, blueprint_id: int) -> EveBlueprint | None:
        """Get a blueprint by its ID.

        Args:
            blueprint_id: The blueprint ID to look up

        Returns:
            EveBlueprint object or None if not found

        """
        return self._load_blueprints().get(blueprint_id)

    def get_category_by_id(self, category_id: int) -> EveCategory | None:
        """Get a category by its ID.

        Args:
            category_id: The category ID to look up

        Returns:
            EveCategory object or None if not found

        """
        return self._load_categories().get(category_id)

    def get_group_by_id(self, group_id: int) -> EveGroup | None:
        """Get a group by its ID.

        Args:
            group_id: The group ID to look up

        Returns:
            EveGroup object or None if not found

        """
        return self._load_groups().get(group_id)

    def get_market_group_by_id(self, market_group_id: int) -> EveMarketGroup | None:
        """Get a market group by its ID.

        Args:
            market_group_id: The market group ID to look up

        Returns:
            EveMarketGroup object or None if not found

        """
        return self._load_market_groups().get(market_group_id)

    def get_type_material_by_id(self, type_id: int) -> EveTypeMaterial | None:
        """Get type materials by type ID.

        Args:
            type_id: The type ID to look up

        Returns:
            EveTypeMaterial object or None if not found

        """
        return self._load_type_materials().get(type_id)

    def get_dogma_attribute_by_id(self, attribute_id: int) -> EveDogmaAttribute | None:
        """Get a dogma attribute by its ID.

        Args:
            attribute_id: The dogma attribute ID to look up

        Returns:
            EveDogmaAttribute object or None if not found

        """
        return self._load_dogma_attributes().get(attribute_id)

    def get_dogma_effect_by_id(self, effect_id: int) -> EveDogmaEffect | None:
        """Get a dogma effect by its ID.

        Args:
            effect_id: The dogma effect ID to look up

        Returns:
            EveDogmaEffect object or None if not found

        """
        return self._load_dogma_effects().get(effect_id)

    def get_dogma_unit_by_id(self, unit_id: int) -> EveDogmaUnit | None:
        """Get a dogma unit by its ID.

        Args:
            unit_id: The dogma unit ID to look up

        Returns:
            EveDogmaUnit object or None if not found

        """
        return self._load_dogma_units().get(unit_id)

    def get_dogma_attribute_category_by_id(
        self, category_id: int
    ) -> EveDogmaAttributeCategory | None:
        """Get a dogma attribute category by its ID.

        Args:
            category_id: The dogma attribute category ID to look up

        Returns:
            EveDogmaAttributeCategory object or None if not found

        """
        return self._load_dogma_attribute_categories().get(category_id)

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

    def get_all_blueprints(self) -> list[EveBlueprint]:
        """Get all blueprints.

        Returns:
            List of all EveBlueprint objects

        """
        return list(self._load_blueprints().values())

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

    def clear_cache(self) -> None:
        """Clear all cached data to free memory."""
        logger.info("Clearing SDE cache...")

        # Clear primary caches
        self._types_cache = None
        self._blueprints_cache = None
        self._categories_cache = None
        self._groups_cache = None
        self._market_groups_cache = None
        self._type_materials_cache = None
        self._dogma_attributes_cache = None
        self._dogma_effects_cache = None
        self._dogma_units_cache = None
        self._dogma_attr_categories_cache = None

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
                self._blueprints_cache is not None,
                self._categories_cache is not None,
                self._groups_cache is not None,
                self._market_groups_cache is not None,
                self._type_materials_cache is not None,
                self._dogma_attributes_cache is not None,
                self._dogma_effects_cache is not None,
                self._dogma_units_cache is not None,
                self._dogma_attr_categories_cache is not None,
            ]
        )

    def get_cache_stats(self) -> dict[str, int | bool]:
        """Get statistics about cached data.

        Returns:
            Dictionary with cache sizes and index status

        """
        return {
            "types": len(self._types_cache) if self._types_cache else 0,
            "blueprints": len(self._blueprints_cache) if self._blueprints_cache else 0,
            "categories": len(self._categories_cache) if self._categories_cache else 0,
            "groups": len(self._groups_cache) if self._groups_cache else 0,
            "market_groups": (
                len(self._market_groups_cache) if self._market_groups_cache else 0
            ),
            "type_materials": (
                len(self._type_materials_cache) if self._type_materials_cache else 0
            ),
            "dogma_attributes": (
                len(self._dogma_attributes_cache) if self._dogma_attributes_cache else 0
            ),
            "dogma_effects": (
                len(self._dogma_effects_cache) if self._dogma_effects_cache else 0
            ),
            "dogma_units": (
                len(self._dogma_units_cache) if self._dogma_units_cache else 0
            ),
            "dogma_attr_categories": (
                len(self._dogma_attr_categories_cache)
                if self._dogma_attr_categories_cache
                else 0
            ),
            "indices_built": len(self._types_by_group_index) > 0,
        }
