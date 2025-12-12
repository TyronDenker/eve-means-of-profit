"""Dialog for viewing and managing all custom prices and locations."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.location_service import LocationService
from ui.signal_bus import get_signal_bus
from ui.styles import COLORS, AppStyles
from utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


class CustomOverridesDialog(QDialog):
    """Dialog showing all custom prices and locations with ESI/SDE-resolved info."""

    def __init__(
        self,
        parent=None,
        sde_provider=None,
        esi_client=None,
        location_service: LocationService | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Custom Overrides - Prices & Locations")
        self.resize(900, 600)

        self._settings = get_settings_manager()
        self._signal_bus = get_signal_bus()
        self._sde_provider = sde_provider
        self._esi_client = esi_client
        self._location_service = location_service

        # Lazy-load SDE if not provided
        if self._sde_provider is None:
            try:
                from data import SDEProvider  # noqa: PLC0415
                from data.parsers import SDEJsonlParser  # noqa: PLC0415
                from utils.config import get_config  # noqa: PLC0415

                parser = SDEJsonlParser(str(get_config().sde.sde_dir_path))
                self._sde_provider = SDEProvider(parser)
            except Exception:
                logger.warning("Could not load SDE provider")

        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        hint = QPushButton(
            "Inline edits: double-click a row to edit, or use the buttons below."
        )
        hint.setEnabled(False)
        hint.setStyleSheet(
            f"QPushButton {{ text-align: left; color: {COLORS.TEXT_SECONDARY}; border: none; background: transparent; }}"
        )
        layout.addWidget(hint)

        # Custom Prices section
        prices_group = QGroupBox("Custom Prices")
        prices_group.setStyleSheet(AppStyles.GROUP_BOX)
        prices_layout = QVBoxLayout(prices_group)

        self.prices_table = QTableWidget()
        self.prices_table.setStyleSheet(AppStyles.TABLE + AppStyles.SCROLLBAR)
        self.prices_table.setColumnCount(4)
        self.prices_table.setHorizontalHeaderLabels(
            ["Type ID", "Type Name", "Buy Price", "Sell Price"]
        )
        ph = self.prices_table.horizontalHeader()
        if ph is not None:
            try:
                ph.setStretchLastSection(True)
                ph.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            except Exception:
                pass
        self.prices_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.prices_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.prices_table.doubleClicked.connect(lambda _: self._edit_selected_price())
        prices_layout.addWidget(self.prices_table)

        # Prices actions
        prices_buttons = QVBoxLayout()
        self.remove_price_btn = QPushButton("Remove Selected")
        self.remove_price_btn.clicked.connect(self._remove_selected_price)
        prices_buttons.addWidget(self.remove_price_btn)
        self.edit_price_btn = QPushButton("Edit Selected…")
        self.edit_price_btn.clicked.connect(self._edit_selected_price)
        prices_buttons.addWidget(self.edit_price_btn)
        prices_buttons.addStretch()
        prices_layout.addLayout(prices_buttons)

        layout.addWidget(prices_group)

        # Custom Locations section
        locations_group = QGroupBox("Custom Locations")
        locations_group.setStyleSheet(AppStyles.GROUP_BOX)
        locations_layout = QVBoxLayout(locations_group)

        self.locations_table = QTableWidget()
        self.locations_table.setStyleSheet(AppStyles.TABLE + AppStyles.SCROLLBAR)
        self.locations_table.setColumnCount(4)
        self.locations_table.setHorizontalHeaderLabels(
            ["Location ID", "Custom Name", "System Override", "System Name"]
        )
        lh = self.locations_table.horizontalHeader()
        if lh is not None:
            try:
                lh.setStretchLastSection(True)
                lh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            except Exception:
                pass
        self.locations_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.locations_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.locations_table.doubleClicked.connect(
            lambda _: self._edit_selected_location()
        )
        locations_layout.addWidget(self.locations_table)

        # Locations actions
        locations_buttons = QVBoxLayout()
        self.remove_location_btn = QPushButton("Remove Selected")
        self.remove_location_btn.clicked.connect(self._remove_selected_location)
        locations_buttons.addWidget(self.remove_location_btn)
        self.edit_location_btn = QPushButton("Edit Selected…")
        self.edit_location_btn.clicked.connect(self._edit_selected_location)
        locations_buttons.addWidget(self.edit_location_btn)
        locations_buttons.addStretch()
        locations_layout.addLayout(locations_buttons)

        layout.addWidget(locations_group)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)
        layout.addWidget(button_box)

    def _load_data(self) -> None:
        """Load custom prices and locations from settings."""
        self._load_prices()
        self._load_locations()

    def _load_prices(self) -> None:
        """Load custom prices into the table."""
        custom_prices = self._settings.get_all_custom_prices()

        self.prices_table.setRowCount(0)
        if not custom_prices:
            return

        self.prices_table.setRowCount(len(custom_prices))

        for row_idx, (type_id, price_data) in enumerate(sorted(custom_prices.items())):
            # Type ID
            type_id_item = QTableWidgetItem(str(type_id))
            type_id_item.setData(Qt.ItemDataRole.UserRole, type_id)
            self.prices_table.setItem(row_idx, 0, type_id_item)

            # Type Name (resolve via SDE)
            type_name = "Unknown"
            if self._sde_provider:
                try:
                    eve_type = self._sde_provider.get_type_by_id(int(type_id))
                    if eve_type and getattr(eve_type, "name", None):
                        type_name = str(eve_type.name)
                except Exception:
                    pass
            self.prices_table.setItem(row_idx, 1, QTableWidgetItem(type_name))

            # Buy Price
            buy_price = price_data.get("buy", "")
            buy_str = f"{buy_price:,.2f}" if buy_price else ""
            self.prices_table.setItem(row_idx, 2, QTableWidgetItem(buy_str))

            # Sell Price
            sell_price = price_data.get("sell", "")
            sell_str = f"{sell_price:,.2f}" if sell_price else ""
            self.prices_table.setItem(row_idx, 3, QTableWidgetItem(sell_str))

    def _load_locations(self) -> None:
        """Load custom locations into the table."""
        custom_locations = {}
        if self._location_service:
            try:
                custom_locations = self._location_service.get_all_custom_locations()
            except Exception:
                logger.exception("Failed to load custom locations from cache")

        self.locations_table.setRowCount(0)
        if not custom_locations:
            return

        self.locations_table.setRowCount(len(custom_locations))

        for row_idx, (location_id, location_data) in enumerate(
            sorted(custom_locations.items())
        ):
            # Location ID
            loc_id_item = QTableWidgetItem(str(location_id))
            loc_id_item.setData(Qt.ItemDataRole.UserRole, location_id)
            self.locations_table.setItem(row_idx, 0, loc_id_item)

            # Custom Name
            custom_name = location_data.get("name", "")
            cleaned_name = str(custom_name).strip()
            self.locations_table.setItem(row_idx, 1, QTableWidgetItem(cleaned_name))

            # System Override ID
            system_id = location_data.get("system_id", "")
            system_id_str = str(system_id) if system_id else ""
            self.locations_table.setItem(row_idx, 2, QTableWidgetItem(system_id_str))

            # System Name (resolve via SDE)
            system_name = ""
            if system_id and self._sde_provider:
                try:
                    resolved_name = self._sde_provider.get_solar_system_name(
                        int(system_id)
                    )
                    if resolved_name:
                        system_name = resolved_name
                except Exception:
                    pass
            self.locations_table.setItem(row_idx, 3, QTableWidgetItem(system_name))

    def _remove_selected_price(self) -> None:
        """Remove the selected custom price."""
        sel_model = self.prices_table.selectionModel()
        if not sel_model:
            return
        selected_rows = sel_model.selectedRows()
        if not selected_rows:
            return

        for index in selected_rows:
            type_id_item = self.prices_table.item(index.row(), 0)
            if type_id_item:
                type_id = type_id_item.data(Qt.ItemDataRole.UserRole)
                try:
                    # Remove from settings
                    self._settings.remove_custom_price(int(type_id))
                    # Emit signal to update other views
                    self._signal_bus.custom_price_changed.emit(int(type_id))
                    logger.info(f"Removed custom price for type_id {type_id}")
                except Exception as e:
                    logger.error(f"Failed to remove custom price: {e}")

        # Reload the table
        self._load_prices()

    def _edit_selected_price(self) -> None:
        """Edit the selected custom price (buy/sell)."""
        sel_model = self.prices_table.selectionModel()
        if not sel_model:
            return
        selected_rows = sel_model.selectedRows()
        if not selected_rows:
            return

        # Use first selected row for editing
        index = selected_rows[0]
        type_id_item = self.prices_table.item(index.row(), 0)
        type_name_item = self.prices_table.item(index.row(), 1)
        if not type_id_item:
            return
        type_id = type_id_item.data(Qt.ItemDataRole.UserRole)
        type_name = type_name_item.text() if type_name_item else ""

        try:
            from ui.dialogs.custom_price_dialog import (
                CustomPriceDialog,
            )

            dlg = CustomPriceDialog(int(type_id), type_name=type_name, parent=self)
            if dlg.exec():
                # Dialog handles saving and signal emission; just reload table
                self._load_prices()
        except Exception as e:
            logger.error(f"Failed to edit custom price: {e}")

    def _remove_selected_location(self) -> None:
        """Remove the selected custom location."""
        sel_model = self.locations_table.selectionModel()
        if not sel_model:
            return
        selected_rows = sel_model.selectedRows()
        if not selected_rows:
            return

        for index in selected_rows:
            loc_id_item = self.locations_table.item(index.row(), 0)
            if loc_id_item:
                location_id = loc_id_item.data(Qt.ItemDataRole.UserRole)
                try:
                    if self._location_service:
                        self._location_service.set_custom_location_data(
                            int(location_id), name=None, system_id=None
                        )
                    # Emit signal to update other views
                    self._signal_bus.custom_location_changed.emit(int(location_id))
                    logger.info(
                        f"Removed custom location for location_id {location_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to remove custom location: {e}")

        # Reload the table
        self._load_locations()

    def _edit_selected_location(self) -> None:
        """Edit the selected custom location (name/system override)."""
        sel_model = self.locations_table.selectionModel()
        if not sel_model:
            return
        selected_rows = sel_model.selectedRows()
        if not selected_rows:
            return

        # Use first selected row for editing
        index = selected_rows[0]
        loc_id_item = self.locations_table.item(index.row(), 0)
        curr_name_item = self.locations_table.item(index.row(), 1)
        if not loc_id_item:
            return
        location_id = loc_id_item.data(Qt.ItemDataRole.UserRole)
        current_name = curr_name_item.text() if curr_name_item else ""

        try:
            from ui.dialogs.custom_location_dialog import (
                CustomLocationDialog,
            )

            dlg = CustomLocationDialog(
                int(location_id),
                current_name,
                parent=self,
                sde_provider=self._sde_provider,
                location_service=self._location_service,
            )
            if dlg.exec():
                # Dialog handles saving and signal emission; reload table
                self._load_locations()
        except Exception as e:
            logger.error(f"Failed to edit custom location: {e}")
