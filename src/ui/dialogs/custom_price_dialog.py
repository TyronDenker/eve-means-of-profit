"""Dialog to set custom buy/sell prices for an item type."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
)

from ui.signal_bus import get_signal_bus
from ui.styles import AppStyles
from utils.settings_manager import get_settings_manager


class CustomPriceDialog(QDialog):
    def __init__(self, type_id: int, type_name: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Price")
        self._settings = get_settings_manager()
        self._signal_bus = get_signal_bus()
        self._type_id = type_id
        self._type_name = type_name or f"Type {type_id}"
        layout = QFormLayout(self)
        layout.addRow(QLabel(f"Item: {self._type_name} (ID {type_id})"))
        self._hint_label = QLabel("Click to edit custom prices")
        self._hint_label.setStyleSheet(AppStyles.LABEL_INFO)
        self._hint_label.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addRow("Custom Prices", self._hint_label)
        self.buy_spin = QDoubleSpinBox()
        self.buy_spin.setRange(0.0, 1e12)
        self.buy_spin.setDecimals(2)
        self.buy_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        self.sell_spin = QDoubleSpinBox()
        self.sell_spin.setRange(0.0, 1e12)
        self.sell_spin.setDecimals(2)
        self.sell_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        prices = self._settings.get_custom_price(type_id) or {}
        if prices.get("buy") is not None:
            self.buy_spin.setValue(float(prices["buy"]))
        if prices.get("sell") is not None:
            self.sell_spin.setValue(float(prices["sell"]))
        # Hide editors until the user clicks the hint (editable-on-click UX)
        self._editors_shown = False
        self.buy_spin.hide()
        self.sell_spin.hide()
        layout.addRow("Buy Price", self.buy_spin)
        layout.addRow("Sell Price", self.sell_spin)
        self._hint_label.mousePressEvent = self._on_hint_clicked

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        # Add Clear button similar to CustomLocationDialog
        clear_button = buttons.addButton(
            "Clear", QDialogButtonBox.ButtonRole.ActionRole
        )
        if clear_button is not None:
            clear_button.clicked.connect(self._on_clear)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_accept(self) -> None:
        self._settings.set_custom_price(
            self._type_id, buy=self.buy_spin.value(), sell=self.sell_spin.value()
        )
        self._signal_bus.custom_price_changed.emit(self._type_id)
        self.accept()

    def _show_editors(self) -> None:
        if self._editors_shown:
            return
        self._editors_shown = True
        self._hint_label.hide()
        self.buy_spin.show()
        self.sell_spin.show()

    def _on_hint_clicked(self, _event) -> None:
        self._show_editors()

    def _on_clear(self) -> None:
        """Clear custom prices for this type by removing the entry."""
        try:
            self._settings.remove_custom_price(self._type_id)
        except Exception:
            # Fallback: set explicitly to None if removal API fails
            self._settings.set_custom_price(self._type_id, buy=None, sell=None)
        self._signal_bus.custom_price_changed.emit(self._type_id)
        try:
            self._signal_bus.info_message.emit(
                f"Cleared custom price overrides for {self._type_name}"
            )
        except Exception:
            pass
        self.accept()
