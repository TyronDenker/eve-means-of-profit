"""User preferences dialog for application-wide settings."""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles import AppStyles
from utils.settings_manager import SettingsManager, get_settings_manager

logger = logging.getLogger(__name__)


class PreferencesDialog(QDialog):
    """Dialog for editing user preferences.

    Centralizes UI/default filter/column settings, market value sources,
    and logging preferences in a tabbed interface.
    """

    def __init__(
        self,
        settings_manager: SettingsManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize preferences dialog.

        Args:
            settings_manager: Settings manager instance (uses global if None)
            parent: Parent widget
        """
        super().__init__(parent)
        self._settings = settings_manager or get_settings_manager()

        self.setWindowTitle("User Preferences")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self._setup_ui()
        self._load_current_values()

    def _setup_ui(self) -> None:
        """Setup user interface with tabbed layout."""
        layout = QVBoxLayout(self)

        # Create tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Market Value tab
        self.tabs.addTab(self._create_market_value_tab(), "Market Values")

        # Logging tab
        self.tabs.addTab(self._create_logging_tab(), "Logging")

        # Button row
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.apply_button = QPushButton("Apply")
        self.apply_button.setStyleSheet(AppStyles.BUTTON_PRIMARY)
        self.apply_button.clicked.connect(self._on_apply)
        button_layout.addWidget(self.apply_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.setStyleSheet(AppStyles.BUTTON_PRIMARY)
        self.ok_button.clicked.connect(self._on_ok)
        button_layout.addWidget(self.ok_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(AppStyles.BUTTON_SECONDARY)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def _create_market_value_tab(self) -> QWidget:
        """Create market value preferences tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Market Source group
        source_group = QGroupBox("Market Data Source")
        source_group.setStyleSheet(AppStyles.GROUP_BOX)
        source_layout = QFormLayout(source_group)

        # Station selector
        self.station_combo = QComboBox()
        self.station_combo.addItems(["Jita", "Amarr", "Dodixie", "Rens", "Hek"])
        self.station_combo.setStyleSheet(AppStyles.COMBOBOX)
        source_layout.addRow("Trade Hub:", self.station_combo)

        station_help = QLabel(
            "Select which trade hub to use for market price lookups. "
            "Jita typically has the highest volume and best prices."
        )
        station_help.setWordWrap(True)
        station_help.setStyleSheet("color: #888; font-size: 10px;")
        source_layout.addRow("", station_help)

        layout.addWidget(source_group)

        # Price Type group
        price_group = QGroupBox("Price Calculation")
        price_group.setStyleSheet(AppStyles.GROUP_BOX)
        price_layout = QFormLayout(price_group)

        # Price type selector
        self.price_type_combo = QComboBox()
        self.price_type_combo.addItems(["Sell", "Buy", "Weighted"])
        self.price_type_combo.setStyleSheet(AppStyles.COMBOBOX)
        self.price_type_combo.currentTextChanged.connect(self._on_price_type_changed)
        price_layout.addRow("Price Type:", self.price_type_combo)

        price_help = QLabel(
            "• Sell: Use sell order prices (typical for asset valuation)\n"
            "• Buy: Use buy order prices (more conservative)\n"
            "• Weighted: Blend of buy and sell prices"
        )
        price_help.setWordWrap(True)
        price_help.setStyleSheet("color: #888; font-size: 10px;")
        price_layout.addRow("", price_help)

        # Weighted ratio (only visible when Weighted is selected)
        self.weighted_label = QLabel("Buy Weight:")
        self.weighted_spin = QDoubleSpinBox()
        self.weighted_spin.setRange(0.0, 1.0)
        self.weighted_spin.setSingleStep(0.1)
        self.weighted_spin.setDecimals(2)
        self.weighted_spin.setSuffix("")
        self.weighted_spin.setStyleSheet(AppStyles.SPINBOX)
        price_layout.addRow(self.weighted_label, self.weighted_spin)

        weighted_help = QLabel(
            "Weight for buy prices (0.0 = all sell, 1.0 = all buy). "
            "For example, 0.3 means 30% buy price + 70% sell price."
        )
        weighted_help.setWordWrap(True)
        weighted_help.setStyleSheet("color: #888; font-size: 10px;")
        self.weighted_help = weighted_help
        price_layout.addRow("", weighted_help)

        layout.addWidget(price_group)

        layout.addStretch()
        return widget

    def _create_logging_tab(self) -> QWidget:
        """Create logging preferences tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Logging group
        logging_group = QGroupBox("Log File Settings")
        logging_group.setStyleSheet(AppStyles.GROUP_BOX)
        logging_layout = QFormLayout(logging_group)

        # Enable file logging
        self.log_file_checkbox = QCheckBox("Save logs to files")
        self.log_file_checkbox.setStyleSheet(AppStyles.CHECKBOX)
        logging_layout.addRow("File Logging:", self.log_file_checkbox)

        # Retention count
        self.retention_spin = QSpinBox()
        self.retention_spin.setRange(1, 365)
        self.retention_spin.setSuffix(" files")
        self.retention_spin.setStyleSheet(AppStyles.SPINBOX)
        logging_layout.addRow("Retention:", self.retention_spin)

        retention_help = QLabel(
            "Number of log files to keep. Older files are automatically deleted. "
            "Each file represents one application session."
        )
        retention_help.setWordWrap(True)
        retention_help.setStyleSheet("color: #888; font-size: 10px;")
        logging_layout.addRow("", retention_help)

        # Log level
        self.log_level_combo = QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setStyleSheet(AppStyles.COMBOBOX)
        logging_layout.addRow("Log Level:", self.log_level_combo)

        level_help = QLabel(
            "Minimum severity for logged messages:\n"
            "• DEBUG: Detailed diagnostic information\n"
            "• INFO: General informational messages\n"
            "• WARNING: Warning messages (recommended)\n"
            "• ERROR: Error messages only\n"
            "• CRITICAL: Critical errors only"
        )
        level_help.setWordWrap(True)
        level_help.setStyleSheet("color: #888; font-size: 10px;")
        logging_layout.addRow("", level_help)

        layout.addWidget(logging_group)

        layout.addStretch()
        return widget

    def _load_current_values(self) -> None:
        """Load current settings into UI controls."""
        # Market values
        station = self._settings.get_market_source_station()
        station_index = {"jita": 0, "amarr": 1, "dodixie": 2, "rens": 3, "hek": 4}.get(
            station.lower(), 0
        )
        self.station_combo.setCurrentIndex(station_index)

        price_type = self._settings.get_market_price_type()
        type_index = {"sell": 0, "buy": 1, "weighted": 2}.get(price_type.lower(), 0)
        self.price_type_combo.setCurrentIndex(type_index)

        self.weighted_spin.setValue(self._settings.get_market_weighted_buy_ratio())
        self._on_price_type_changed(self.price_type_combo.currentText())

        # Logging
        self.log_file_checkbox.setChecked(self._settings.get_logging_save_to_file())
        self.retention_spin.setValue(self._settings.get_logging_retention_count())
        level = self._settings.get_logging_level()
        level_index = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"].index(level)
        self.log_level_combo.setCurrentIndex(level_index)

    def _on_price_type_changed(self, text: str) -> None:
        """Show/hide weighted ratio controls based on price type."""
        is_weighted = text.lower() == "weighted"
        self.weighted_label.setVisible(is_weighted)
        self.weighted_spin.setVisible(is_weighted)
        self.weighted_help.setVisible(is_weighted)

    def _on_apply(self) -> None:
        """Apply settings without closing dialog."""
        self._save_settings()

    def _on_ok(self) -> None:
        """Apply settings and close dialog."""
        self._save_settings()
        self.accept()

    def _save_settings(self) -> None:
        """Save all settings from UI controls."""
        try:
            # Market values
            station_map = ["jita", "amarr", "dodixie", "rens", "hek"]
            self._settings.set_market_source_station(
                station_map[self.station_combo.currentIndex()]
            )

            type_map = ["sell", "buy", "weighted"]
            self._settings.set_market_price_type(
                type_map[self.price_type_combo.currentIndex()]
            )

            self._settings.set_market_weighted_buy_ratio(self.weighted_spin.value())

            # Logging
            self._settings.set_logging_save_to_file(self.log_file_checkbox.isChecked())
            self._settings.set_logging_retention_count(self.retention_spin.value())
            level_map = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            self._settings.set_logging_level(
                level_map[self.log_level_combo.currentIndex()]
            )

            logger.info("User preferences saved successfully")

        except Exception as e:
            logger.exception("Failed to save preferences: %s", e)
