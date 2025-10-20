"""SDE JSONL data loader for EVE Online static data."""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.models.eve import (
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
from src.utils.jsonl_parser import JSONLParser

logger = logging.getLogger(__name__)


class SDEJsonlLoader:
    """Loader for SDE JSONL files with lazy loading capabilities."""

    def __init__(self, base_path: Path | str | None = None):
        """Initialize the loader with a base path to SDE data.

        Args:
            base_path: Path to the SDE data directory. Defaults to 'data/sde/'
                      relative to the project root.

        """
        if base_path is None:
            # Default to data/sde from project root
            self.base_path = Path(__file__).parent.parent.parent.parent / "data" / "sde"
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
        """Map SDE keys to model field names.

        The SDE uses '_key' and camelCase for most fields.
        Pydantic models use 'id' and snake_case with aliases.

        Args:
            data: Raw dictionary from JSONL

        Returns:
            Dictionary with mapped keys

        """
        # Map _key to id
        if "_key" in data:
            data["id"] = data["_key"]

        return data

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
