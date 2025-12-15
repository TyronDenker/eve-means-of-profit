"""Context menu factory for consistent menu actions across all tabs.

Provides reusable menu builders for:
- Copy actions (cells, rows, columns, headers)
- Custom price management
- Custom location name management
- Navigation to related items/locations
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import QInputDialog, QMenu, QWidget

from ui.signal_bus import get_signal_bus
from ui.utils.clipboard import (
    copy_cells_as_text,
    copy_column_headers,
    copy_field_values,
    copy_rows_as_csv,
)

if TYPE_CHECKING:
    from utils.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class ContextMenuFactory:
    """Factory for creating consistent context menus across tabs."""

    def __init__(self, settings_manager: SettingsManager | None = None):
        """Initialize context menu factory.

        Args:
            settings_manager: Settings manager for custom price/location actions
        """
        self._settings = settings_manager

    def build_table_menu(
        self,
        parent: QWidget,
        selected_rows: list[dict[str, Any]],
        columns: list[tuple[str, str]],
        *,
        enable_copy: bool = True,
        enable_custom_price: bool = False,
        enable_custom_location: bool = False,
        type_id_key: str = "type_id",
        location_id_key: str = "location_id",
        custom_actions: list[tuple[str, Callable[[], None]]] | None = None,
    ) -> QMenu:
        """Build a context menu for table views.

        Args:
            parent: Parent widget for the menu
            selected_rows: List of selected row dictionaries
            columns: List of (key, title) column tuples
            enable_copy: Enable copy submenu
            enable_custom_price: Enable custom price actions (requires type_id in rows)
            enable_custom_location: Enable custom location actions (requires location_id)
            type_id_key: Key for type_id in row dict (default: "type_id")
            location_id_key: Key for location_id in row dict
            custom_actions: Additional custom actions as (label, callback) tuples

        Returns:
            QMenu instance ready to display
        """
        menu = QMenu(parent)

        # Copy submenu
        if enable_copy and selected_rows:
            copy_menu = menu.addMenu("Copy")
            if copy_menu:
                # Copy selection as text
                copy_menu.addAction(
                    "Copy Selection (Tab-separated)",
                    lambda: copy_cells_as_text(
                        selected_rows, [col[0] for col in columns]
                    ),
                )

                # Copy as CSV
                copy_menu.addAction(
                    "Copy Selection as CSV",
                    lambda: copy_rows_as_csv(selected_rows, columns),
                )

                copy_menu.addSeparator()

                # Copy column headers
                copy_menu.addAction(
                    "Copy Column Headers", lambda: copy_column_headers(columns)
                )

                # Copy specific fields if common keys exist
                common_keys = self._find_common_keys(selected_rows, columns)
                if common_keys:
                    copy_menu.addSeparator()
                    for key, title in common_keys[:5]:  # Limit to 5 most common
                        copy_menu.addAction(
                            f"Copy {title}",
                            lambda k=key: copy_field_values(selected_rows, k),
                        )

        # Custom price submenu
        if enable_custom_price and selected_rows and self._settings:
            menu.addSeparator()
            price_menu = menu.addMenu("Custom Price")
            if price_menu:
                # Extract unique type IDs
                type_ids = self._extract_unique_ids(selected_rows, type_id_key)

                if len(type_ids) == 1:
                    type_id = type_ids[0]
                    price_menu.addAction(
                        "Set Custom Price...",
                        lambda: self._show_set_price_dialog(parent, type_id),
                    )

                    # Show remove option if custom price exists
                    if self._settings.get_custom_price(type_id):
                        price_menu.addAction(
                            "Remove Custom Price",
                            lambda: self._remove_custom_price(type_id),
                        )
                elif len(type_ids) > 1:
                    price_menu.addAction(
                        f"Set Custom Prices for {len(type_ids)} Items...",
                        lambda: self._show_bulk_price_dialog(parent, type_ids),
                    )

        # Custom location name submenu
        if enable_custom_location and selected_rows and self._settings:
            menu.addSeparator()
            location_menu = menu.addMenu("Custom Location")
            if location_menu:
                # Extract unique location IDs
                location_ids = self._extract_unique_ids(selected_rows, location_id_key)

                if len(location_ids) == 1:
                    location_id = location_ids[0]
                    location_menu.addAction(
                        "Set Custom Location Name...",
                        lambda: self._show_set_location_dialog(parent, location_id),
                    )

                    # Show remove option if custom location exists
                    if self._settings.get_custom_location_name(location_id):
                        location_menu.addAction(
                            "Remove Custom Location Name",
                            lambda: self._remove_custom_location(location_id),
                        )

        # Custom actions
        if custom_actions:
            menu.addSeparator()
            for label, callback in custom_actions:
                menu.addAction(label, callback)

        # Selection info
        if selected_rows:
            menu.addSeparator()
            info_action = menu.addAction(f"Selection: {len(selected_rows)} item(s)")
            if info_action:
                info_action.setEnabled(False)

        return menu

    def _find_common_keys(
        self, rows: list[dict[str, Any]], columns: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """Find column keys that have non-empty values in all selected rows.

        Args:
            rows: List of row dictionaries
            columns: List of (key, title) tuples

        Returns:
            List of (key, title) tuples for columns with values in all rows
        """
        if not rows:
            return []

        common = []
        for key, title in columns:
            if all(row.get(key) for row in rows):
                common.append((key, title))

        return common

    def _extract_unique_ids(self, rows: list[dict[str, Any]], id_key: str) -> list[int]:
        """Extract unique integer IDs from rows.

        Args:
            rows: List of row dictionaries
            id_key: Key to extract IDs from

        Returns:
            List of unique IDs as integers
        """
        ids = set()
        for row in rows:
            val = row.get(id_key)
            if val is not None:
                try:
                    ids.add(int(val))
                except (ValueError, TypeError):
                    pass

        return sorted(ids)

    def _show_set_price_dialog(self, parent: QWidget, type_id: int) -> None:
        """Show dialog to set custom price for a type.

        Args:
            parent: Parent widget
            type_id: EVE type ID
        """
        if not self._settings:
            return

        # Get current custom price if any
        current = self._settings.get_custom_price(type_id)
        current_sell = current.get("sell") if current else None

        price, ok = QInputDialog.getDouble(
            parent,
            "Set Custom Price",
            f"Enter custom sell price for type {type_id}:",
            value=current_sell or 0.0,
            min=0.0,
            decimals=2,
        )

        if ok and price > 0:
            self._settings.set_custom_price(type_id, sell_price=price)
            logger.info("Set custom price for type %d: %.2f", type_id, price)

            # Emit signal if available
            try:
                get_signal_bus().custom_price_changed.emit(type_id)
            except Exception as e:
                logger.debug("Failed to emit custom_price_changed: %s", e)

    def _show_bulk_price_dialog(self, parent: QWidget, type_ids: list[int]) -> None:
        """Show dialog to set same price for multiple types.

        Args:
            parent: Parent widget
            type_ids: List of EVE type IDs
        """
        if not self._settings:
            return

        price, ok = QInputDialog.getDouble(
            parent,
            "Set Custom Prices",
            f"Enter custom sell price for {len(type_ids)} items:",
            value=0.0,
            min=0.0,
            decimals=2,
        )

        if ok and price > 0:
            for type_id in type_ids:
                self._settings.set_custom_price(type_id, sell_price=price)

            logger.info("Set custom price for %d types: %.2f", len(type_ids), price)

            # Emit signals
            try:
                bus = get_signal_bus()
                for type_id in type_ids:
                    bus.custom_price_changed.emit(type_id)
            except Exception as e:
                logger.debug("Failed to emit custom_price_changed: %s", e)

    def _remove_custom_price(self, type_id: int) -> None:
        """Remove custom price for a type.

        Args:
            type_id: EVE type ID
        """
        if not self._settings:
            return

        self._settings.remove_custom_price(type_id)
        logger.info("Removed custom price for type %d", type_id)

        # Emit signal
        try:
            get_signal_bus().custom_price_changed.emit(type_id)
        except Exception as e:
            logger.debug("Failed to emit custom_price_changed: %s", e)

    def _show_set_location_dialog(self, parent: QWidget, location_id: int) -> None:
        """Show dialog to set custom location name.

        Args:
            parent: Parent widget
            location_id: Location ID
        """
        if not self._settings:
            return

        # Get current custom name if any
        current = self._settings.get_custom_location_name(location_id)

        name, ok = QInputDialog.getText(
            parent,
            "Set Custom Location Name",
            f"Enter custom name for location {location_id}:",
            text=current or "",
        )

        if ok and name:
            self._settings.set_custom_location_name(location_id, name)
            logger.info("Set custom location name for %d: %s", location_id, name)

            # Emit signal
            try:
                get_signal_bus().custom_location_changed.emit(location_id)
            except Exception as e:
                logger.debug("Failed to emit custom_location_changed: %s", e)

    def _remove_custom_location(self, location_id: int) -> None:
        """Remove custom location name.

        Args:
            location_id: Location ID
        """
        if not self._settings:
            return

        self._settings.remove_custom_location_name(location_id)
        logger.info("Removed custom location name for %d", location_id)

        # Emit signal
        try:
            get_signal_bus().custom_location_changed.emit(location_id)
        except Exception as e:
            logger.debug("Failed to emit custom_location_changed: %s", e)
