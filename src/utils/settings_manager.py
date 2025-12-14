"""Centralized user settings management for EVE Means of Profit.

This module manages user preferences and UI state through a JSON file.

Features:
- Thread-safe singleton pattern
- Atomic file writes (temp file + rename)
- Type-safe Pydantic models
- Per-tab UI settings
- Character manager preferences
- Custom prices
- Automatic defaults on first run

Usage:
    from utils.settings_manager import get_settings_manager

    settings = get_settings_manager()

    # Get UI settings for a specific tab
    ui = settings.get_ui_settings("assets")

    # Update character order
    settings.set_character_order([123, 456, 789])

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

from .config import get_config

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
    col_widths: dict[str, int] = Field(
        default_factory=dict,
        description="Width in pixels for each column keyed by column id/name",
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


class MarketValuePreferences(BaseModel):
    """Preferences for market value calculations."""

    source_station: str = Field(
        default="jita",
        description="Market station for prices: 'jita', 'amarr', 'dodixie', 'rens', 'hek'",
    )
    price_type: str = Field(
        default="sell",
        description="Price type to use: 'buy', 'sell', 'weighted'",
    )
    weighted_buy_ratio: float = Field(
        default=0.3,
        description="Weight for buy price in weighted calculation (0.0-1.0)",
    )


class LoggingPreferences(BaseModel):
    """Preferences for application logging."""

    save_to_file: bool = Field(
        default=True,
        description="Whether to save logs to files",
    )
    retention_count: int = Field(
        default=7,
        description="Number of log files to retain (older files are deleted)",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
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
    # Font and UI sizing preferences
    character_name_font_size: int = Field(
        default=14,
        description="Font size for character names (px)",
    )
    corp_alliance_font_size: int = Field(
        default=11,
        description="Font size for corporation and alliance names (px)",
    )
    networth_font_size: int = Field(
        default=11,
        description="Font size for networth data (px)",
    )
    portrait_size: int = Field(
        default=128,
        description="Character portrait size in pixels (64, 96, 128, 192, 256, 512, 1024)",
    )
    sidebar_visible: bool = Field(
        default=True,
        description="Whether the endpoint timer sidebar is visible",
    )
    show_refresh_on_hover: bool = Field(
        default=True,
        description="When true, hovering over a character portrait shows a refresh button",
    )
    # Character ordering within accounts
    account_character_order: dict[str, list[int]] = Field(
        default_factory=dict,
        description="Character order per account: {account_id: [char_id1, char_id2, ...]}",
    )
    # View state persistence
    show_endpoint_timers: bool = Field(
        default=True,
        description="Whether to show endpoint timers in character cards",
    )
    list_view_enabled: bool = Field(
        default=False,
        description="Whether list view is enabled instead of card view",
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
    market_value: MarketValuePreferences = Field(
        default_factory=MarketValuePreferences,
        description="Market value source and calculation preferences",
    )
    logging: LoggingPreferences = Field(
        default_factory=LoggingPreferences,
        description="Logging preferences for file output and retention",
    )

    # Account management: allows mapping characters to accounts and storing
    # account-wide PLEX vault amounts (in units of PLEX, not ISK).
    accounts: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Accounts data keyed by account_id: {name: str, plex_units: int, "
            "characters: [int, ...]}"
        ),
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
        # External persistence files for custom data (new separated storage)
        # These allow independent versioning and prevent large rewrites of the
        # main settings file when frequently adjusting prices or names.
        self._custom_prices_path = self._settings_path.parent / "custom_prices.json"
        self._write_lock = threading.Lock()
        self._settings = self._load()
        # Load / migrate external custom data stores
        self._load_external_custom_data()
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
            # New: accounts default empty
            accounts={},
        )
        # Save defaults immediately
        self._save(defaults)
        return defaults

    def _save(self, settings: UserSettings | None = None) -> None:
        """Atomically save settings to JSON with Windows-safe replace and retry.

        Writes to a unique temp file in the same directory, fsyncs, then replaces
        the target with os.replace (atomic on Windows) with limited retries to avoid
        PermissionError when other processes momentarily lock the file.

        Args:
            settings: Settings to save. If None, saves current settings.
        """
        if settings is None:
            settings = self._settings

        with self._write_lock:
            # Ensure parent directory exists
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)

            # Prepare pruned payload (exclude external custom stores)
            pruned = settings.model_dump(mode="json")
            pruned["custom_prices"] = {}

            # Unique temp filename to avoid collisions
            import contextlib
            import os
            import time

            temp_name = f"{self._settings_path.name}.tmp-{os.getpid()}-{int(time.time() * 1000)}"
            temp_path = self._settings_path.parent / temp_name

            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(pruned, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                logger.error(
                    "Failed to write temporary settings file %s: %s", temp_path, e
                )
                with contextlib.suppress(Exception):
                    if temp_path.exists():
                        temp_path.unlink()
                raise

            # Attempt atomic replace with retries
            max_attempts = 5
            delay = 0.1
            last_err: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    os.replace(temp_path, self._settings_path)
                    logger.debug("Settings saved to %s", self._settings_path)
                    last_err = None
                    break
                except PermissionError as e:
                    last_err = e
                    logger.warning(
                        "PermissionError replacing settings (attempt %d/%d): %s",
                        attempt,
                        max_attempts,
                        e,
                    )
                    time.sleep(delay)
                    delay = min(delay * 2, 1.0)
                except Exception as e:
                    last_err = e
                    logger.error("Unexpected error replacing settings: %s", e)
                    break

            # Cleanup temp file if still present
            with contextlib.suppress(Exception):
                if temp_path.exists():
                    temp_path.unlink()

            if last_err is not None:
                raise last_err

    def reload(self) -> None:
        """Reload settings from disk, discarding any unsaved changes."""
        with self._write_lock:
            self._settings = self._load()
            # Refresh external stores (do not overwrite current in-memory values)
            self._load_external_custom_data()
            logger.debug("Settings reloaded from disk")

    # -------------------------------------------------------------------------
    # External Stores (Custom Prices / Locations)
    # -------------------------------------------------------------------------

    def _load_external_custom_data(self) -> None:
        """Load or migrate custom price and location data into memory.

        Migration logic:
        - If external files exist, load them and replace in-memory maps.
        - If they do NOT exist but legacy data is present in user_settings.json,
          write out the new external files and clear legacy fields from the
          primary settings file for future runs.
        """
        migrated = False

        # Load custom prices external file if present
        if self._custom_prices_path.exists():
            try:
                with open(self._custom_prices_path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    # Expect root to be mapping type_id -> {buy, sell}
                    self._settings.custom_prices = {
                        str(k): v for k, v in data.items() if isinstance(v, dict)
                    }
            except Exception as e:
                logger.warning(f"Failed to load custom prices file: {e}")
        elif self._settings.custom_prices:
            # Legacy inline data – migrate
            self._persist_custom_prices()
            migrated = True

        # If migration occurred, prune legacy fields from settings file
        if migrated:
            try:
                self._save(self._settings)
                logger.info(
                    "Migrated legacy custom price/location data to external JSON files"
                )
            except Exception:
                logger.exception("Failed to prune legacy custom data after migration")

    def _persist_custom_prices(self) -> None:
        """Persist current in-memory custom prices to external file."""
        try:
            self._custom_prices_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._custom_prices_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._settings.custom_prices, f, indent=2, ensure_ascii=False)
            tmp.replace(self._custom_prices_path)
        except Exception as e:
            logger.error(f"Failed to persist custom prices: {e}")

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

    def get_character_name_font_size(self) -> int:
        """Get the character name font size."""
        return self._settings.character_manager.character_name_font_size

    def set_character_name_font_size(self, size: int) -> None:
        """Set the character name font size."""
        self._settings.character_manager.character_name_font_size = max(
            8, min(24, size)
        )
        self._save()

    def get_corp_alliance_font_size(self) -> int:
        """Get the corporation/alliance font size."""
        return self._settings.character_manager.corp_alliance_font_size

    def set_corp_alliance_font_size(self, size: int) -> None:
        """Set the corporation/alliance font size."""
        self._settings.character_manager.corp_alliance_font_size = max(8, min(18, size))
        self._save()

    def get_networth_font_size(self) -> int:
        """Get the networth data font size."""
        return self._settings.character_manager.networth_font_size

    def set_networth_font_size(self, size: int) -> None:
        """Set the networth data font size."""
        self._settings.character_manager.networth_font_size = max(8, min(16, size))
        self._save()

    def get_portrait_size(self) -> int:
        """Get the character portrait size."""
        return self._settings.character_manager.portrait_size

    def set_portrait_size(self, size: int) -> None:
        """Set the character portrait size."""
        # Allow only specific portrait sizes
        valid_sizes = [64, 96, 128, 192, 256]
        if size not in valid_sizes:
            # Find closest valid size
            size = min(valid_sizes, key=lambda x: abs(x - size))
        self._settings.character_manager.portrait_size = size
        self._save()

    def get_sidebar_visible(self) -> bool:
        """Get whether the endpoint timer sidebar is visible."""
        return self._settings.character_manager.sidebar_visible

    def set_sidebar_visible(self, visible: bool) -> None:
        """Set whether the endpoint timer sidebar is visible."""
        self._settings.character_manager.sidebar_visible = visible
        self._save()

    def get_show_refresh_on_hover(self) -> bool:
        """Get whether hovering over a portrait shows a refresh button."""
        return self._settings.character_manager.show_refresh_on_hover

    def set_show_refresh_on_hover(self, visible: bool) -> None:
        """Set whether hovering over a portrait shows a refresh button."""
        self._settings.character_manager.show_refresh_on_hover = bool(visible)
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
        # Persist ONLY the external store (avoid rewriting whole settings file)
        self._persist_custom_prices()

    def remove_custom_price(self, type_id: int) -> None:
        """Remove custom price for an item type.

        Args:
            type_id: Item type ID to remove custom price for
        """
        key = str(type_id)
        if key in self._settings.custom_prices:
            del self._settings.custom_prices[key]
            self._persist_custom_prices()

    def get_all_custom_prices(self) -> dict[int, dict[str, float | None]]:
        """Get all custom item prices.

        Returns:
            Dictionary mapping type IDs to price dictionaries {buy, sell}
        """
        return {int(k): v for k, v in self._settings.custom_prices.items()}

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

    # -------------------------------------------------------------------------
    # Accounts & PLEX vault management
    # -------------------------------------------------------------------------

    def get_accounts(self) -> dict[int, dict[str, Any]]:
        """Return all accounts with their metadata.

        Returns:
            Mapping of account_id -> {name, plex_units, characters}
        """
        out: dict[int, dict[str, Any]] = {}
        for k, v in self._settings.accounts.items():
            try:
                out[int(k)] = {
                    "name": str(v.get("name") or ""),
                    "plex_units": int(v.get("plex_units") or 0),
                    "characters": [int(x) for x in v.get("characters", [])],
                }
            except Exception:
                continue
        return out

    def get_account_name(self, account_id: int) -> str | None:
        """Get the display name for an account.

        Args:
            account_id: Numeric account identifier

        Returns:
            Account name or None if not set
        """
        acc = self._settings.accounts.get(str(account_id))
        if not acc:
            return None
        name = acc.get("name")
        return str(name) if name else None

    def set_account(self, account_id: int, name: str | None = None) -> None:
        """Create or update an account name.

        Args:
            account_id: Numeric account identifier (user-defined)
            name: Optional display name
        """
        key = str(account_id)
        acc = self._settings.accounts.get(
            key, {"name": "", "plex_units": 0, "characters": []}
        )
        if name is not None:
            acc["name"] = str(name)
        self._settings.accounts[key] = acc
        self._save()

    def set_account_plex_units(self, account_id: int, units: int) -> None:
        """Set PLEX vault amount (in units) for an account."""
        key = str(account_id)
        acc = self._settings.accounts.get(
            key, {"name": "", "plex_units": 0, "characters": []}
        )
        acc["plex_units"] = max(0, int(units))
        self._settings.accounts[key] = acc
        self._save()

    def get_account_plex_units(self, account_id: int) -> int:
        """Get PLEX units stored for an account."""
        acc = self._settings.accounts.get(str(account_id))
        if not acc:
            return 0
        try:
            return int(acc.get("plex_units") or 0)
        except Exception:
            return 0

    def set_account_plex_update_time(self, account_id: int, timestamp: str) -> None:
        """Set the timestamp when PLEX vault was last manually updated (ISO format)."""
        key = str(account_id)
        acc = self._settings.accounts.get(
            key, {"name": "", "plex_units": 0, "characters": []}
        )
        acc["plex_update_time"] = timestamp
        self._settings.accounts[key] = acc
        self._save()

    def get_account_plex_update_time(self, account_id: int) -> str | None:
        """Get the timestamp when PLEX vault was last manually updated (ISO format)."""
        acc = self._settings.accounts.get(str(account_id))
        if not acc:
            return None
        return acc.get("plex_update_time")

    def assign_character_to_account(self, character_id: int, account_id: int) -> bool:
        """Assign a character to an account, enforcing max 3 characters per account.

        Returns True if assignment succeeded, False if limit exceeded.
        """
        key = str(account_id)
        acc = self._settings.accounts.get(
            key, {"name": "", "plex_units": 0, "characters": []}
        )
        chars = [int(x) for x in acc.get("characters", [])]
        if character_id in chars:
            # Already assigned
            return True
        if len(chars) >= 3:
            return False
        chars.append(int(character_id))
        acc["characters"] = chars
        self._settings.accounts[key] = acc
        self._save()
        return True

    def unassign_character_from_account(
        self, character_id: int, account_id: int
    ) -> None:
        """Remove a character from an account."""
        key = str(account_id)
        acc = self._settings.accounts.get(key)
        if not acc:
            return
        acc["characters"] = [
            int(x) for x in acc.get("characters", []) if int(x) != int(character_id)
        ]
        self._settings.accounts[key] = acc
        self._save()

    def delete_account(self, account_id: int) -> None:
        """Delete an account entirely.

        Note: Characters should be unassigned before calling this.
        """
        key = str(account_id)
        if key in self._settings.accounts:
            del self._settings.accounts[key]
            self._save()

    def get_account_for_character(self, character_id: int) -> int | None:
        """Return the account_id this character is assigned to, if any."""
        for k, v in self._settings.accounts.items():
            chars = [int(x) for x in v.get("characters", [])]
            if int(character_id) in chars:
                try:
                    return int(k)
                except Exception:
                    return None
        return None

    def get_primary_character_for_account(self, account_id: int) -> int | None:
        """Return a deterministic 'primary' character for an account.

        Uses the first in list; falls back to smallest ID.
        """
        acc = self._settings.accounts.get(str(account_id))
        if not acc:
            return None
        chars = [int(x) for x in acc.get("characters", [])]
        if not chars:
            return None
        return chars[0]

    # -------------------------------------------------------------------------
    # Market Value Preferences
    # -------------------------------------------------------------------------

    def get_market_source_station(self) -> str:
        """Get the market station for price lookups."""
        return self._settings.market_value.source_station

    def set_market_source_station(self, station: str) -> None:
        """Set the market station for price lookups.

        Args:
            station: One of 'jita', 'amarr', 'dodixie', 'rens', 'hek'
        """
        valid_stations = {"jita", "amarr", "dodixie", "rens", "hek"}
        if station.lower() in valid_stations:
            self._settings.market_value.source_station = station.lower()
            self._save()

    def get_market_price_type(self) -> str:
        """Get the price type for market calculations."""
        return self._settings.market_value.price_type

    def set_market_price_type(self, price_type: str) -> None:
        """Set the price type for market calculations.

        Args:
            price_type: One of 'buy', 'sell', 'weighted'
        """
        valid_types = {"buy", "sell", "weighted"}
        if price_type.lower() in valid_types:
            self._settings.market_value.price_type = price_type.lower()
            self._save()

    def get_market_weighted_buy_ratio(self) -> float:
        """Get the buy weight ratio for weighted price calculations."""
        return self._settings.market_value.weighted_buy_ratio

    def set_market_weighted_buy_ratio(self, ratio: float) -> None:
        """Set the buy weight ratio for weighted price calculations.

        Args:
            ratio: Float between 0.0 and 1.0
        """
        self._settings.market_value.weighted_buy_ratio = max(0.0, min(1.0, ratio))
        self._save()

    # -------------------------------------------------------------------------
    # Logging Preferences
    # -------------------------------------------------------------------------

    def get_logging_save_to_file(self) -> bool:
        """Get whether logs should be saved to files."""
        return self._settings.logging.save_to_file

    def set_logging_save_to_file(self, enabled: bool) -> None:
        """Set whether logs should be saved to files."""
        self._settings.logging.save_to_file = bool(enabled)
        self._save()

    def get_logging_retention_count(self) -> int:
        """Get the number of log files to retain."""
        return self._settings.logging.retention_count

    def set_logging_retention_count(self, count: int) -> None:
        """Set the number of log files to retain."""
        self._settings.logging.retention_count = max(1, min(365, count))
        self._save()

    def get_logging_level(self) -> str:
        """Get the logging level."""
        return self._settings.logging.log_level

    def set_logging_level(self, level: str) -> None:
        """Set the logging level.

        Args:
            level: One of 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        """
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level.upper() in valid_levels:
            self._settings.logging.log_level = level.upper()
            self._save()

    # -------------------------------------------------------------------------
    # View State Persistence
    # -------------------------------------------------------------------------

    def get_show_endpoint_timers(self) -> bool:
        """Get whether endpoint timers are shown in character cards.

        Returns:
            True if timers should be shown, False otherwise
        """
        return self._settings.character_manager.show_endpoint_timers

    def set_show_endpoint_timers(self, visible: bool) -> None:
        """Set whether endpoint timers are shown in character cards.

        Args:
            visible: True to show timers, False to hide them
        """
        self._settings.character_manager.show_endpoint_timers = bool(visible)
        self._save()

    def get_list_view_enabled(self) -> bool:
        """Get whether list view is enabled instead of card view.

        Returns:
            True if list view is enabled, False for card view
        """
        return self._settings.character_manager.list_view_enabled

    def set_list_view_enabled(self, enabled: bool) -> None:
        """Set whether list view is enabled instead of card view.

        Args:
            enabled: True to enable list view, False for card view
        """
        self._settings.character_manager.list_view_enabled = bool(enabled)
        self._save()

    # -------------------------------------------------------------------------
    # Character Ordering within Accounts
    # -------------------------------------------------------------------------

    def get_account_character_order(self, account_id: int) -> list[int]:
        """Get the ordered list of character IDs for an account.

        Args:
            account_id: Account identifier

        Returns:
            Ordered list of character IDs, or empty list if not set
        """
        order = self._settings.character_manager.account_character_order.get(
            str(account_id), []
        )
        return [int(x) for x in order]

    def set_account_character_order(self, account_id: int, order: list[int]) -> None:
        """Set the character order for an account.

        Args:
            account_id: Account identifier
            order: Ordered list of character IDs
        """
        self._settings.character_manager.account_character_order[str(account_id)] = [
            int(x) for x in order
        ]
        self._save()


# Global singleton accessor
_manager_instance: SettingsManager | None = None
_manager_lock = threading.Lock()


def get_settings_manager(
    settings_manager: SettingsManager | None = None,
) -> SettingsManager:
    """Get the global settings manager instance.

    Args:
        settings_manager: Optional settings manager to use instead of singleton.
                          If provided on first call, sets the singleton.
                          Useful for dependency injection.

    Returns:
        Global SettingsManager singleton
    """
    global _manager_instance  # noqa: PLW0603

    if settings_manager is not None:
        with _manager_lock:
            _manager_instance = settings_manager
        return _manager_instance

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
