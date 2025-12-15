"""SDE JSONL data parser for EVE Online static data."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from models.eve import (
    EveCategory,
    EveGroup,
    EveMarketGroup,
    EveType,
)
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
    # Market group fields
    "hasTypes": "has_types",
    "parentGroupID": "parent_group_id",
    # Material fields
    "materialTypeID": "material_type_id",
}


class SDEJsonlParser:
    """Parser for SDE JSONL files with lazy loading capabilities."""

    def __init__(self, data_path: Path | str):
        """Initialize the parser with the SDE data path.

        Args:
            data_path: Path to the SDE data directory
        """
        self.file_path: Path = Path(data_path)

        if not self.file_path.exists():
            logger.info(
                f"SDE base path does not exist yet: {self.file_path} "
                "(will be created during SDE download)"
            )

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

    def load_blueprint_type_ids(self) -> set[int]:
        """Load all blueprint type IDs from blueprints.jsonl.

        Returns:
            Set of type IDs that are blueprints

        """
        blueprint_ids = set()
        try:
            for data in self._load_jsonl("blueprints.jsonl"):
                # blueprintTypeID is the type_id of the blueprint item
                blueprint_type_id = data.get("blueprintTypeID")
                if blueprint_type_id:
                    blueprint_ids.add(blueprint_type_id)
        except FileNotFoundError:
            logger.warning("blueprints.jsonl not found")
        except Exception:
            logger.exception("Failed to load blueprint type IDs")
        return blueprint_ids

    def load_npc_station_ids(self) -> set[int]:
        """Load all NPC station IDs from npcStations.jsonl.

        Returns:
            Set of NPC station IDs

        """
        station_ids = set()
        try:
            for data in self._load_jsonl("npcStations.jsonl"):
                # _key field contains the station ID
                station_id = data.get("_key")
                if station_id is not None:
                    station_ids.add(int(station_id))
        except FileNotFoundError as e:
            logger.warning(f"NPC stations file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load NPC stations: {e}")

        return station_ids

    def load_npc_station_names(self) -> dict[int, str]:
        """Load NPC station IDs and names from npcStations.jsonl.

        Returns:
            Dictionary mapping station ID to station name

        """
        stations = {}
        try:
            for data in self._load_jsonl("npcStations.jsonl"):
                station_id = data.get("_key")
                name_data = data.get("name")

                if station_id is not None and name_data:
                    # name is a dict with translations, prefer English
                    name = (
                        name_data.get("en")
                        if isinstance(name_data, dict)
                        else str(name_data)
                    )
                    if name:
                        stations[int(station_id)] = name
        except FileNotFoundError as e:
            logger.warning(f"NPC stations file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load NPC station names: {e}")

        return stations

    def load_npc_station_system_ids(self) -> dict[int, int]:
        """Load NPC station to solar system ID mapping from npcStations.jsonl.

        Returns:
            Dictionary mapping station ID to solar system ID

        """
        station_systems = {}
        try:
            for data in self._load_jsonl("npcStations.jsonl"):
                station_id = data.get("_key")
                system_id = data.get("solarSystemID")

                if station_id is not None and system_id is not None:
                    station_systems[int(station_id)] = int(system_id)
        except FileNotFoundError as e:
            logger.warning(f"NPC stations file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load NPC station system IDs: {e}")

        return station_systems

    def load_region_names(self) -> dict[int, str]:
        """Load region IDs and names from mapRegions.jsonl.

        Returns:
            Dictionary mapping region ID to region name

        """
        regions = {}
        try:
            for data in self._load_jsonl("mapRegions.jsonl"):
                region_id = data.get("_key")
                name_data = data.get("name")

                if region_id is not None and name_data:
                    # name is a dict with translations, prefer English
                    name = (
                        name_data.get("en")
                        if isinstance(name_data, dict)
                        else str(name_data)
                    )
                    if name:
                        regions[int(region_id)] = name
        except FileNotFoundError as e:
            logger.warning(f"Region map file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load region names: {e}")

        return regions

    def load_constellation_names(self) -> dict[int, str]:
        """Load constellation IDs and names from mapConstellations.jsonl.

        Returns:
            Dictionary mapping constellation ID to constellation name

        """
        constellations = {}
        try:
            for data in self._load_jsonl("mapConstellations.jsonl"):
                constellation_id = data.get("_key")
                name_data = data.get("name")

                if constellation_id is not None and name_data:
                    # name is a dict with translations, prefer English
                    name = (
                        name_data.get("en")
                        if isinstance(name_data, dict)
                        else str(name_data)
                    )
                    if name:
                        constellations[int(constellation_id)] = name
        except FileNotFoundError as e:
            logger.warning(f"Constellation map file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load constellation names: {e}")

        return constellations

    def load_solar_system_names(self) -> dict[int, str]:
        """Load solar system IDs and names from mapSolarSystems.jsonl.

        Returns:
            Dictionary mapping solar system ID to system name

        """
        systems = {}
        try:
            for data in self._load_jsonl("mapSolarSystems.jsonl"):
                system_id = data.get("_key")
                name_data = data.get("name")

                if system_id is not None and name_data:
                    # name is a dict with translations, prefer English
                    name = (
                        name_data.get("en")
                        if isinstance(name_data, dict)
                        else str(name_data)
                    )
                    if name:
                        systems[int(system_id)] = name
        except FileNotFoundError as e:
            logger.warning(f"Solar system map file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load solar system names: {e}")

        return systems

    def load_solar_system_constellation_ids(self) -> dict[int, int]:
        """Load solar system to constellation ID mapping from mapSolarSystems.jsonl.

        Returns:
            Dictionary mapping solar system ID to constellation ID

        """
        system_constellations = {}
        try:
            for data in self._load_jsonl("mapSolarSystems.jsonl"):
                system_id = data.get("_key")
                constellation_id = data.get("constellationID")

                if system_id is not None and constellation_id is not None:
                    system_constellations[int(system_id)] = int(constellation_id)
        except FileNotFoundError as e:
            logger.warning(f"Solar system map file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load solar system constellation IDs: {e}")

        return system_constellations

    def load_constellation_region_ids(self) -> dict[int, int]:
        """Load constellation to region ID mapping from mapConstellations.jsonl.

        Returns:
            Dictionary mapping constellation ID to region ID

        """
        constellation_regions = {}
        try:
            for data in self._load_jsonl("mapConstellations.jsonl"):
                constellation_id = data.get("_key")
                region_id = data.get("regionID")

                if constellation_id is not None and region_id is not None:
                    constellation_regions[int(constellation_id)] = int(region_id)
        except FileNotFoundError as e:
            logger.warning(f"Constellation map file not found: {e}")
        except Exception as e:
            logger.error(f"Failed to load constellation region IDs: {e}")

        return constellation_regions

    def _load_jsonl(self, filename: str) -> Iterator[dict[str, Any]]:
        """Load a JSONL file and return an iterator of dictionaries.

        Args:
            filename: Name of the JSONL file to load

        Yields:
            Parsed JSON objects from the file

        Raises:
            FileNotFoundError: If the file doesn't exist

        """
        file_path = self.file_path / filename
        if not file_path.exists():
            logger.debug("Skipping missing SDE file: %s", file_path)
            return
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

            # If this field is a translated object (e.g. name: {"en": "...", "de": "..."})
            # prefer the English ('en') value when available. This fixes Pydantic errors where
            # models expect a string but the SDE provides a dict of translations.
            if isinstance(v, dict) and mapped_key in (
                "name",
                "description",
                "display_name",
            ):
                # Prefer English
                en_val = v.get("en")
                if isinstance(en_val, str):
                    out[mapped_key] = en_val
                else:
                    # Fallback to the first string value found
                    picked: Any = None
                    for val in v.values():
                        if isinstance(val, str):
                            picked = val
                            break
                    out[mapped_key] = picked

            # Recursively process nested structures
            elif isinstance(v, dict):
                out[mapped_key] = self._map_keys(v)  # type: ignore[list-item]
            elif isinstance(v, list):
                out[mapped_key] = [
                    self._map_keys(item) if isinstance(item, dict) else item  # type: ignore[list-item]
                    for item in v  # type: ignore[list-item]
                ]
            else:
                out[mapped_key] = v

        return out
