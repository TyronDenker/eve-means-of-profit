"""Centralized user settings management for EVE Means of Profit.

This module manages user preferences and UI state through a JSON file.

Features:
- Thread-safe singleton pattern
- Atomic file writes (temp file + rename)
- Type-safe Pydantic models
- Per-tab UI settings
- Character manager preferences
- Custom locations and prices
- Automatic defaults on first run

Usage:
    from utils.settings_manager import get_settings_manager

    settings = get_settings_manager()

    # Get UI settings for a specific tab
    ui = settings.get_ui_settings("assets")

    # Update character order
    settings.set_character_order([123, 456, 789])

    # Get custom location name
    name = settings.get_custom_location(1000001)

    # Get custom price
    price = settings.get_custom_sell_price(34)
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from utils.config import get_config

logger = logging.getLogger(__name__)


class UISettings(BaseModel):
    """Settings for a single UI tab/view.

    These settings control column visibility, order, widths, sorting,
    and filter panel visibility for table-based views.
    """

    filters_visible: bool = Field(
        default=False,
        description="Whether the advanced filter panel is visible",
    )
    visible_columns: list[str] = Field(
        default_factory=list,
        description="List of column IDs that are currently visible",
    )
    column_order: list[str] = Field(
        default_factory=list,
        description="Visual order of columns (left to right)",
    )
    col_widths: list[int] = Field(
        default_factory=list,
        description="Width in pixels for each column (parallel to column_order)",
    )
    movable: bool = Field(
        default=True,
        description="Whether columns can be reordered by dragging",
    )
    sort_section: int = Field(
        default=-1,
        description="Index of the column used for sorting (-1 = no sort)",
    )
    sort_order: int = Field(
        default=0,
        description="Sort order (0 = ascending, 1 = descending)",
    )

    # Filter-related settings (stored as JSON strings in QSettings)
    active_filter: str = Field(
        default="",
        description="JSON-serialized active filter state",
    )
    filter_presets: str = Field(
        default="",
        description="JSON-serialized filter presets",
    )


class CharacterManagerSettings(BaseModel):
    """Settings for the character manager."""

    order: list[int] = Field(
        default_factory=list,
        description="Ordered list of character IDs for display",
    )
    default_character_id: int | None = Field(
        default=None,
        description="Default character ID to select on startup",
    )
    view_mode: str = Field(
        default="card",
        description="View mode: 'card', 'list', or 'compact'",
    )


class UserSettings(BaseModel):
    """Root settings model containing all user preferences."""

    ui: dict[str, UISettings] = Field(
        default_factory=dict,
        description="UI settings per tab (assets, contracts, industry, etc.)",
    )
    character_manager: CharacterManagerSettings = Field(
        default_factory=CharacterManagerSettings,
        description="Character manager preferences",
    )
    custom_prices: dict[str, dict[str, float | None]] = Field(
        default_factory=dict,
        description="Custom prices for items (key = type_id, value = {buy, sell})",
    )
    custom_locations: dict[str, str] = Field(
        default_factory=dict,
        description="Custom user-defined names for locations (key = location_id, value = custom_name)",
    )


class SettingsManager:
    """Singleton settings manager with thread-safe JSON persistence.

    This class manages all user settings through a unified JSON file.
    All operations are thread-safe and writes are atomic.
    """

    _instance: SettingsManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> SettingsManager:
        """Create or return the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        """Initialize the settings manager."""
        # Prevent re-initialization
        if self._initialized:
            return

        self._settings_path = get_config().app.user_settings_file
        self._write_lock = threading.Lock()
        self._settings = self._load()
        self._initialized = True

    def _load(self) -> UserSettings:
        """Load settings from JSON file, create defaults if missing.

        Returns:
            UserSettings instance with loaded or default values
        """
        if not self._settings_path.exists():
            logger.info(
                f"Settings file not found at {self._settings_path}, creating defaults"
            )
            return self._create_defaults()

        try:
            with open(self._settings_path, encoding="utf-8") as f:
                data = json.load(f)
            return UserSettings.model_validate(data)
        except Exception as e:
            logger.warning(
                f"Failed to load settings from {self._settings_path}: {e}. "
                f"Using defaults."
            )
            return self._create_defaults()

    def _create_defaults(self) -> UserSettings:
        """Create default settings structure.

        Returns:
            UserSettings with default values
        """
        defaults = UserSettings(
            ui={
                "assets": UISettings(),
                "contracts": UISettings(),
                "industry": UISettings(),
                "market_orders": UISettings(),
                "wallet_journal": UISettings(),
                "wallet_transactions": UISettings(),
                "slot_usage": UISettings(),
            },
            character_manager=CharacterManagerSettings(),
            custom_prices={},
        )
        # Save defaults immediately
        self._save(defaults)
        return defaults

    def _save(self, settings: UserSettings | None = None) -> None:
        """Atomically save settings to JSON file.

        Uses a temporary file and rename to ensure atomic writes.

        Args:
            settings: Settings to save. If None, saves current settings.
        """
        if settings is None:
            settings = self._settings

        with self._write_lock:
            try:
                # Ensure parent directory exists
                self._settings_path.parent.mkdir(parents=True, exist_ok=True)

                # Write to temporary file first
                temp_path = self._settings_path.with_suffix(".tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(
                        settings.model_dump(mode="json"),
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )

                # Atomic rename
                temp_path.replace(self._settings_path)
                logger.debug(f"Settings saved to {self._settings_path}")

            except Exception as e:
                logger.error(f"Failed to save settings to {self._settings_path}: {e}")
                raise

    def reload(self) -> None:
        """Reload settings from disk, discarding any unsaved changes."""
        with self._write_lock:
            self._settings = self._load()
            logger.debug("Settings reloaded from disk")

    # -------------------------------------------------------------------------
    # UI Settings
    # -------------------------------------------------------------------------

    def get_ui_settings(self, tab_name: str) -> UISettings:
        """Get UI settings for a specific tab.

        Args:
            tab_name: Name of the tab (e.g., "assets", "contracts")

        Returns:
            UISettings for the specified tab (creates default if missing)
        """
        if tab_name not in self._settings.ui:
            self._settings.ui[tab_name] = UISettings()
            self._save()
        return self._settings.ui[tab_name]

    def set_ui_settings(self, tab_name: str, settings: UISettings) -> None:
        """Update UI settings for a specific tab.

        Args:
            tab_name: Name of the tab (e.g., "assets", "contracts")
            settings: New UISettings to store
        """
        self._settings.ui[tab_name] = settings
        self._save()

    def update_ui_settings(self, tab_name: str, **kwargs: Any) -> None:
        """Update specific UI settings fields for a tab.

        Args:
            tab_name: Name of the tab
            **kwargs: Field names and values to update
        """
        ui = self.get_ui_settings(tab_name)
        for key, value in kwargs.items():
            if hasattr(ui, key):
                setattr(ui, key, value)
        self.set_ui_settings(tab_name, ui)

    # -------------------------------------------------------------------------
    # Character Manager Settings
    # -------------------------------------------------------------------------

    def get_character_order(self) -> list[int]:
        """Get the ordered list of character IDs.

        Returns:
            List of character IDs in display order
        """
        return self._settings.character_manager.order.copy()

    def set_character_order(self, order: list[int]) -> None:
        """Update the character display order.

        Args:
            order: New ordered list of character IDs
        """
        self._settings.character_manager.order = [int(x) for x in order]
        self._save()

    def get_default_character(self) -> int | None:
        """Get the default character ID.

        Returns:
            Default character ID or None if not set
        """
        return self._settings.character_manager.default_character_id

    def set_default_character(self, char_id: int | None) -> None:
        """Set the default character ID.

        Args:
            char_id: Character ID to set as default, or None to clear
        """
        self._settings.character_manager.default_character_id = (
            int(char_id) if char_id is not None else None
        )
        self._save()

    def get_view_mode(self) -> str:
        """Get the character manager view mode.

        Returns:
            View mode string ('card', 'list', or 'compact')
        """
        return self._settings.character_manager.view_mode

    def set_view_mode(self, mode: str) -> None:
        """Set the character manager view mode.

        Args:
            mode: View mode ('card', 'list', or 'compact')
        """
        self._settings.character_manager.view_mode = mode
        self._save()

    # -------------------------------------------------------------------------
    # Custom Prices (supports buy and sell prices)
    # -------------------------------------------------------------------------

    def get_custom_price(self, type_id: int) -> dict[str, float | None] | None:
        """Get custom price for an item type.

        Args:
            type_id: Item type ID to look up

        Returns:
            Dictionary with 'buy' and 'sell' keys, or None if not set
        """
        return self._settings.custom_prices.get(str(type_id))

    def get_custom_buy_price(self, type_id: int) -> float | None:
        """Get custom buy price for an item type.

        Args:
            type_id: Item type ID

        Returns:
            Custom buy price or None
        """
        prices = self.get_custom_price(type_id)
        if prices and "buy" in prices:
            return float(prices["buy"]) if prices["buy"] is not None else None
        return None

    def get_custom_sell_price(self, type_id: int) -> float | None:
        """Get custom sell price for an item type.

        Args:
            type_id: Item type ID

        Returns:
            Custom sell price or None
        """
        prices = self.get_custom_price(type_id)
        if prices and "sell" in prices:
            return float(prices["sell"]) if prices["sell"] is not None else None
        return None

    def set_custom_price(
        self, type_id: int, buy: float | None = None, sell: float | None = None
    ) -> None:
        """Set custom price(s) for an item type.

        Args:
            type_id: Item type ID
            buy: Custom buy price (None to keep existing or leave unset)
            sell: Custom sell price (None to keep existing or leave unset)
        """
        key = str(type_id)
        existing = self._settings.custom_prices.get(key, {"buy": None, "sell": None})

        if buy is not None:
            existing["buy"] = float(buy)
        if sell is not None:
            existing["sell"] = float(sell)

        self._settings.custom_prices[key] = existing
        self._save()

    def remove_custom_price(self, type_id: int) -> None:
        """Remove custom price for an item type.

        Args:
            type_id: Item type ID to remove custom price for
        """
        key = str(type_id)
        if key in self._settings.custom_prices:
            del self._settings.custom_prices[key]
            self._save()

    def get_all_custom_prices(self) -> dict[int, dict[str, float | None]]:
        """Get all custom item prices.

        Returns:
            Dictionary mapping type IDs to price dictionaries {buy, sell}
        """
        return {int(k): v for k, v in self._settings.custom_prices.items()}

    # -------------------------------------------------------------------------
    # Custom Location Names
    # -------------------------------------------------------------------------

    def get_custom_location(self, location_id: int) -> str | None:
        """Get custom user-defined name for a location.

        Args:
            location_id: Location ID to look up

        Returns:
            Custom name or None if not set
        """
        return self._settings.custom_locations.get(str(location_id))

    def set_custom_location(self, location_id: int, custom_name: str | None) -> None:
        """Set custom user-defined name for a location.

        Args:
            location_id: Location ID
            custom_name: Custom name to set, or None to remove
        """
        key = str(location_id)
        if custom_name is None:
            if key in self._settings.custom_locations:
                del self._settings.custom_locations[key]
        else:
            self._settings.custom_locations[key] = custom_name
        self._save()

    def remove_custom_location(self, location_id: int) -> None:
        """Remove custom name for a location.

        Args:
            location_id: Location ID to remove custom name for
        """
        key = str(location_id)
        if key in self._settings.custom_locations:
            del self._settings.custom_locations[key]
            self._save()

    def get_all_custom_locations(self) -> dict[int, str]:
        """Get all custom location names.

        Returns:
            Dictionary mapping location IDs to custom names
        """
        return {int(k): v for k, v in self._settings.custom_locations.items()}

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def export_settings(self, path: Path) -> None:
        """Export settings to a JSON file.

        Args:
            path: Destination file path
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                self._settings.model_dump(mode="json"),
                f,
                indent=2,
                ensure_ascii=False,
            )
        logger.info(f"Settings exported to {path}")

    def import_settings(self, path: Path) -> None:
        """Import settings from a JSON file.

        Args:
            path: Source file path
        """
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self._settings = UserSettings.model_validate(data)
        self._save()
        logger.info(f"Settings imported from {path}")


# Global singleton accessor
_manager_instance: SettingsManager | None = None
_manager_lock = threading.Lock()


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance.

    Returns:
        Global SettingsManager singleton
    """
    global _manager_instance  # noqa: PLW0603

    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = SettingsManager()

    # Type checker needs assurance - will always be set at this point
    assert _manager_instance is not None
    return _manager_instance


def reset_settings_manager() -> None:
    """Reset the global settings manager instance.

    Primarily for testing purposes.
    """
    global _manager_instance  # noqa: PLW0603

    with _manager_lock:
        _manager_instance = None

    # Also reset the SettingsManager singleton
    SettingsManager._instance = None  # noqa: SLF001

global_settings = get_settings_manager()
