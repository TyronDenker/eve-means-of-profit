"""Dialog to set a custom name and system for a location."""

import logging
import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
)

from services.location_service import LocationService
from ui.signal_bus import get_signal_bus
from ui.styles import AppStyles

logger = logging.getLogger(__name__)


class CustomLocationDialog(QDialog):
    def __init__(
        self,
        location_id: int,
        current_name: str = "",
        parent=None,
        sde_provider=None,
        location_service: LocationService | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Custom Location Name & System")
        self._location_service = location_service
        self._signal_bus = get_signal_bus()
        self._location_id = location_id
        self._sde_provider = sde_provider

        layout = QFormLayout(self)
        layout.addRow(QLabel(f"Location ID: {location_id}"))

        # Custom name field (hidden until clicked for inline-edit UX)
        self.name_edit = QLineEdit()
        custom_loc_data = None
        if self._location_service:
            try:
                custom_loc_data = self._location_service.get_custom_location_data(
                    location_id
                )
            except Exception:
                logger.exception("Failed to read custom location data from cache")
        if custom_loc_data and custom_loc_data.get("name"):
            self.name_edit.setText(str(custom_loc_data.get("name")))
        else:
            self.name_edit.setText(str(current_name))
        self.name_edit.hide()
        # Auto-parse system on the fly as the user edits (no popups while typing)
        self.name_edit.textChanged.connect(
            lambda _text: self._on_auto_parse(show_feedback=False)
        )

        self._name_hint = QLabel("Click to edit custom name & system")
        self._name_hint.setStyleSheet(AppStyles.LABEL_INFO)
        self._name_hint.setCursor(Qt.CursorShape.PointingHandCursor)
        self._name_hint.mousePressEvent = self._on_hint_clicked

        layout.addRow("Custom Name", self._name_hint)
        layout.addRow("", self.name_edit)

        # System override dropdown
        self.system_combo = QComboBox()
        self.system_combo.setEditable(True)
        self.system_combo.setStyleSheet(AppStyles.COMBOBOX)
        self.system_combo.addItem("(Auto-detect)", None)
        self.system_combo.hide()

        # Ensure we have an SDE provider (fallback create one lazily)
        if self._sde_provider is None:
            try:
                from data import SDEProvider
                from data.parsers import SDEJsonlParser
                from utils.config import get_config

                parser = SDEJsonlParser(str(get_config().sde.sde_dir_path))
                self._sde_provider = SDEProvider(parser)
            except Exception:
                self._sde_provider = None

        # Load all solar systems from SDE if available
        if self._sde_provider:
            try:
                all_systems = self._sde_provider.get_all_solar_systems()
                sorted_systems = sorted(all_systems.items(), key=lambda x: x[1])
                for sys_id, sys_name in sorted_systems:
                    self.system_combo.addItem(sys_name, sys_id)
            except Exception:
                pass  # SDE not loaded yet

        # Set current system override if saved
        if custom_loc_data and custom_loc_data.get("system_id") is not None:
            saved_sys_id = custom_loc_data.get("system_id")
            for i in range(self.system_combo.count()):
                if self.system_combo.itemData(i) == saved_sys_id:
                    self.system_combo.setCurrentIndex(i)
                    break

        layout.addRow("System Override", self.system_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Add Clear button
        clear_button = buttons.addButton(
            "Clear", QDialogButtonBox.ButtonRole.ActionRole
        )
        if clear_button is not None:
            clear_button.clicked.connect(self._on_clear)

        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _show_editors(self) -> None:
        self._name_hint.hide()
        self.name_edit.show()
        self.system_combo.show()

    def _on_hint_clicked(self, _event) -> None:
        """Handle click on the hint label to reveal editors."""
        self._show_editors()

    def _on_auto_parse(self, show_feedback: bool = False) -> bool:
        """Try to auto-parse system from the location name.

        Args:
            show_feedback: When True, emit a single info message on failure; when
                False, stay silent (used during typing to avoid popup spam).

        Returns:
            bool: True if a system was detected and selected, else False.
        """
        name = self.name_edit.text().strip()
        if not name or not self._sde_provider:
            return False

        found = False

        # Try to extract system name from common patterns
        # Pattern 1: "System Name - Structure Name"
        # Pattern 2: "Structure Name (System Name)"
        # Pattern 3: Just search for any known system name in the text

        all_systems = self._sde_provider.get_all_solar_systems()

        # Try pattern matching first
        patterns = [
            r"^([^-]+?)\s*[-\u2013]\s*",  # "System - Structure"
            r"\(([^)]+)\)\s*$",  # "Structure (System)"
            r"^([A-Z0-9]+-[A-Z0-9]+)",  # J-space or nullsec system codes
        ]

        for pattern in patterns:
            match = re.search(pattern, name)
            if match:
                potential_system = match.group(1).strip()
                # Check if it matches any system
                for sys_id, sys_name in all_systems.items():
                    if sys_name.lower() == potential_system.lower():
                        # Found it!
                        for i in range(self.system_combo.count()):
                            if self.system_combo.itemData(i) == sys_id:
                                self.system_combo.setCurrentIndex(i)
                                found = True
                                break
                        if found:
                            break
                if found:
                    break

        # Fallback: check if any known system name appears in the text
        name_lower = name.lower()
        for sys_id, sys_name in all_systems.items():
            if sys_name.lower() in name_lower:
                for i in range(self.system_combo.count()):
                    if self.system_combo.itemData(i) == sys_id:
                        self.system_combo.setCurrentIndex(i)
                        found = True
                        break
                if found:
                    break

        if not found and show_feedback:
            self._signal_bus.info_message.emit(
                "Could not auto-detect system from name; you can choose one manually."
            )
        return found

    def _on_clear(self) -> None:
        """Clear the custom location name and system override."""
        self.name_edit.clear()
        self.system_combo.setCurrentIndex(0)  # Reset to auto-detect
        try:
            if self._location_service:
                self._location_service.set_custom_location_data(
                    self._location_id, name=None, system_id=None
                )
            self._signal_bus.custom_location_changed.emit(self._location_id)
            self._signal_bus.info_message.emit(
                f"Cleared custom name for location {self._location_id}"
            )
        except Exception:
            logger.exception("Failed to clear custom location override")
            try:
                self._signal_bus.error_occurred.emit(
                    "Failed to clear custom location override; see logs."
                )
            except Exception:
                pass

    def _on_accept(self) -> None:
        name = self.name_edit.text().strip()

        # One last auto-parse attempt with user-facing feedback if nothing is selected
        self._on_auto_parse(show_feedback=True)

        system_id = self.system_combo.currentData()

        # Store as dict with both name and system_id
        location_data = {}
        if name:
            location_data["name"] = name
        if system_id is not None:
            location_data["system_id"] = system_id

        logger.debug(
            "Saving custom location: location_id=%d, data=%s",
            self._location_id,
            location_data if location_data else None,
        )

        # Save to locations cache via location service
        if self._location_service:
            self._location_service.set_custom_location_data(
                self._location_id,
                name=location_data.get("name"),
                system_id=location_data.get("system_id"),
            )
            verification = self._location_service.get_custom_location_data(
                self._location_id
            )
            logger.debug(
                "Verified saved data: location_id=%d, retrieved=%s",
                self._location_id,
                verification,
            )

        logger.debug(
            "Emitting custom_location_changed signal with location_id=%d",
            self._location_id,
        )
        self._signal_bus.custom_location_changed.emit(self._location_id)
        logger.debug("Signal emitted successfully")
        self.accept()
