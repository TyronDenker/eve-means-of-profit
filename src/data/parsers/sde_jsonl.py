"""SDE JSONL data parser for EVE Online static data."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

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
from utils.config import Config
from utils.jsonl_parser import JSONLParser

logger = logging.getLogger(__name__)

# Mapping of SDE camelCase field names to snake_case model field names
FIELD_NAME_MAP = {
    # Special SDE key
    "_key": "id",
    # Type fields
    "groupID": "group_id",
    "basePrice": "base_price",
    "factionID": "faction_id",
    "graphicID": "graphic_id",
    "iconID": "icon_id",
    "marketGroupID": "market_group_id",
    "metaGroupID": "meta_group_id",
    "portionSize": "portion_size",
    "raceID": "race_id",
    "soundID": "sound_id",
    "variationParentTypeID": "variation_parent_type_id",
    # Blueprint fields
    "blueprintTypeID": "blueprint_type_id",
    "maxProductionLimit": "max_production_limit",
    # Activity fields (used in materials, products, skills)
    "typeID": "type_id",
    "quantity": "quantity",
    "probability": "probability",
    "level": "level",
    "time": "time",
    # Activity names (already snake_case in SDE, but included for completeness)
    "copying": "copying",
    "manufacturing": "manufacturing",
    "invention": "invention",
    "reaction": "reaction",
    "research_material": "research_material",
    "research_time": "research_time",
    "materials": "materials",
    "products": "products",
    "skills": "skills",
    # Category fields
    "categoryID": "category_id",
    # Group fields
    "anchorable": "anchorable",
    "anchored": "anchored",
    "fittableNonSingleton": "fittable_non_singleton",
    "useBasePrice": "use_base_price",
    # Dogma fields
    "attributeID": "attribute_id",
    "defaultValue": "default_value",
    "displayName": "display_name",
    "highIsGood": "high_is_good",
    "stackable": "stackable",
    "unitID": "unit_id",
    "effectID": "effect_id",
    "effectCategory": "effect_category",
    "electronicChance": "electronic_chance",
    "isAssistance": "is_assistance",
    "isOffensive": "is_offensive",
    "isWarpSafe": "is_warp_safe",
    "dischargeAttributeID": "discharge_attribute_id",
    "durationAttributeID": "duration_attribute_id",
    "rangeAttributeID": "range_attribute_id",
    "falloffAttributeID": "falloff_attribute_id",
    "trackingSpeedAttributeID": "tracking_speed_attribute_id",
    "fittingUsageChanceAttributeID": "fitting_usage_chance_attribute_id",
    "displayNameID": "display_name_id",
    # Material fields
    "materialTypeID": "material_type_id",
}


class SDEJsonlParser:
    """Parser for SDE JSONL files with lazy loading capabilities."""

    def __init__(self, base_path: Path | str | None = None):
        """Initialize the parser with a base path to SDE data.

        Args:
            base_path: Path to the SDE data directory. If None, uses Config().paths.sde_path
                      which works correctly with PyInstaller and environment variables.

        """
        if base_path is None:
            # Use config path (PyInstaller compatible)
            self.base_path = Config().paths.sde_path
        else:
            self.base_path = Path(base_path)

        if not self.base_path.exists():
            logger.warning(f"SDE base path does not exist: {self.base_path}")

    def _load_jsonl(self, filename: str) -> Iterator[dict[str, Any]]:
        """Load a JSONL file and return an iterator of dictionaries.

        Args:
            filename: Name of the JSONL file to load

        Yields:
            Parsed JSON objects from the file

        Raises:
            FileNotFoundError: If the file doesn't exist

        """
        file_path = self.base_path / filename
        parser = JSONLParser(file_path)
        yield from parser.parse()

    def _map_keys(self, data: dict[str, Any]) -> dict[str, Any]:
        """Map SDE keys to model field names recursively.

        Handles:
        - Converting SDE keys to our domain keys using FIELD_NAME_MAP
        - Recursively processing nested dicts and lists

        Args:
            data: Raw dictionary from JSONL

        Returns:
            Dictionary with snake_case keys (recursively applied)

        """
        out: dict[str, Any] = {}

        for k, v in data.items():
            # Map key using the field name mapping, fall back to original if not found
            mapped_key: str = FIELD_NAME_MAP.get(k, k)

            # Recursively process nested structures
            if isinstance(v, dict):
                out[mapped_key] = self._map_keys(v)  # type: ignore[list-item]
            elif isinstance(v, list):
                out[mapped_key] = [
                    self._map_keys(item) if isinstance(item, dict) else item  # type: ignore[list-item]
                    for item in v  # type: ignore[list-item]
                ]
            else:
                out[mapped_key] = v

        return out

    def load_types(self) -> Iterator[EveType]:
        """Load all EVE types from types.jsonl.

        Yields:
            EveType objects

        """
        try:
            for data in self._load_jsonl("types.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveType(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse type {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Types file not found: {e}")
            raise

    def load_blueprints(self) -> Iterator[EveBlueprint]:
        """Load all EVE blueprints from blueprints.jsonl.

        Yields:
            EveBlueprint objects

        """
        try:
            for data in self._load_jsonl("blueprints.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveBlueprint(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse blueprint {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Blueprints file not found: {e}")
            raise

    def load_categories(self) -> Iterator[EveCategory]:
        """Load all EVE categories from categories.jsonl.

        Yields:
            EveCategory objects

        """
        try:
            for data in self._load_jsonl("categories.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveCategory(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse category {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Categories file not found: {e}")
            raise

    def load_groups(self) -> Iterator[EveGroup]:
        """Load all EVE groups from groups.jsonl.

        Yields:
            EveGroup objects

        """
        try:
            for data in self._load_jsonl("groups.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveGroup(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse group {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Groups file not found: {e}")
            raise

    def load_market_groups(self) -> Iterator[EveMarketGroup]:
        """Load all EVE market groups from marketGroups.jsonl.

        Yields:
            EveMarketGroup objects

        """
        try:
            for data in self._load_jsonl("marketGroups.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveMarketGroup(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse market group {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Market groups file not found: {e}")
            raise

    def load_type_materials(self) -> Iterator[EveTypeMaterial]:
        """Load all EVE type materials from typeMaterials.jsonl.

        Yields:
            EveTypeMaterial objects

        """
        try:
            for data in self._load_jsonl("typeMaterials.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveTypeMaterial(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse type material {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Type materials file not found: {e}")
            raise

    def load_dogma_attributes(self) -> Iterator[EveDogmaAttribute]:
        """Load all dogma attributes from dogmaAttributes.jsonl.

        Yields:
            EveDogmaAttribute objects

        """
        try:
            for data in self._load_jsonl("dogmaAttributes.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveDogmaAttribute(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse dogma attr {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Dogma attributes file not found: {e}")
            raise

    def load_dogma_effects(self) -> Iterator[EveDogmaEffect]:
        """Load all dogma effects from dogmaEffects.jsonl.

        Yields:
            EveDogmaEffect objects

        """
        try:
            for data in self._load_jsonl("dogmaEffects.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveDogmaEffect(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse dogma effect {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Dogma effects file not found: {e}")
            raise

    def load_dogma_units(self) -> Iterator[EveDogmaUnit]:
        """Load all dogma units from dogmaUnits.jsonl.

        Yields:
            EveDogmaUnit objects

        """
        try:
            for data in self._load_jsonl("dogmaUnits.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveDogmaUnit(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse dogma unit {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Dogma units file not found: {e}")
            raise

    def load_dogma_attribute_categories(self) -> Iterator[EveDogmaAttributeCategory]:
        """Load all dogma attribute categories from dogmaAttributeCategories.jsonl.

        Yields:
            EveDogmaAttributeCategory objects

        """
        try:
            for data in self._load_jsonl("dogmaAttributeCategories.jsonl"):
                data = self._map_keys(data)
                try:
                    yield EveDogmaAttributeCategory(**data)
                except Exception as e:
                    item_id = data.get("id", "unknown")
                    logger.error(f"Failed to parse dogma attr cat {item_id}: {e}")
                    continue
        except FileNotFoundError as e:
            logger.error(f"Dogma attribute categories file not found: {e}")
            raise
