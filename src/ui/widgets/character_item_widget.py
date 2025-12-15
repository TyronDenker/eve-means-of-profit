"""Reusable widget that renders a character portrait and optional corp/alliance logos.

Public API:
- class CharacterItemWidget(QWidget)
  - set_portrait(img_data: bytes | bytearray | memoryview | None) -> None
  - set_corp_logo(img_data: bytes | bytearray | memoryview | None) -> None
  - set_alliance_logo(img_data: bytes | bytearray | memoryview | None) -> None

This module is self-contained and only depends on PyQt6. It guards against
invalid image data and preserves the styling and sizes from the original
inline implementation.
"""

from __future__ import annotations

import logging
import re

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ui.styles import COLORS
from utils.settings_manager import get_settings_manager

from .endpoint_timer import EndpointTimer

logger = logging.getLogger(__name__)


class CharacterItemWidget(QWidget):
    """Widget for a single character list item.

    Renders a 128x128 portrait and, if available on the ``character`` object,
    64x64 corporation and alliance logos with their respective names.

    The widget exposes setters to update the images from raw bytes and is
    resilient to invalid data (it will safely ignore bad images and keep
    placeholders).

    Parameters:
        character:
            An object with attributes like ``character_name``, ``character_id``,
            ``corporation_name``, ``alliance_name`` (missing ones are handled).
        parent:
            Optional parent widget.

    Signals:
        refresh_requested: Emitted when the refresh button is clicked (character_id)
    """

    refresh_requested = pyqtSignal(int)  # character_id

    def __init__(self, character: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.character = character
        self.character_id = getattr(character, "character_id", 0)
        self._settings = get_settings_manager()
        self._view_mode: str = "card"  # or "list"
        self._networth_visible: bool = True
        self._timers_visible: bool = True  # Track endpoint timer visibility
        self._networth_container: QWidget | None = None
        self._networth_snapshot: object | None = None  # Store for list view access
        self._endpoint_timers: dict[str, float | None] = {}  # Store cache expiry times

        # Main horizontal layout: left (info above portrait), right (networth grid)
        main_layout = QHBoxLayout(self)
        # Default margins chosen to match the original styling. We keep a
        # reference and the default tuple so we can tweak margins when the
        # right-side networth panel is hidden to keep left/right spacing
        # visually balanced.
        main_layout.setContentsMargins(2, 2, 2, 2)
        self._main_layout = main_layout
        self._default_main_layout_margins = (2, 2, 2, 2)
        main_layout.setSpacing(2)
        # Keep a reference to the main layout and its default margins so
        # we can tweak spacing when the networth column is hidden to avoid
        # excessive empty space on the right. Stored as (left, top, right, bottom).
        try:
            self._main_layout = main_layout
            self._main_layout_default_margins = main_layout.getContentsMargins()
        except Exception:
            # Defensive: if layout API differs, fall back to None so callers
            # can check existence before using.
            self._main_layout = None
            self._main_layout_default_margins = None

        # --- LEFT SIDE: Info above Portrait ---
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        portrait_size = self._settings.get_portrait_size()
        name_font_size = self._settings.get_character_name_font_size()
        corp_font_size = self._settings.get_corp_alliance_font_size()

        # Portrait and icons
        logo_size = max(24, portrait_size // 4)
        portrait_container = QWidget()
        portrait_container.setFixedSize(portrait_size, portrait_size)
        portrait_container.setStyleSheet("background: transparent;")
        portrait_layout_inner = QHBoxLayout(portrait_container)
        portrait_layout_inner.setContentsMargins(0, 0, 0, 0)
        portrait_layout_inner.setSpacing(0)
        self.portrait_label = QLabel(portrait_container)
        self.portrait_label.setFixedSize(portrait_size, portrait_size)
        self.portrait_label.setScaledContents(True)
        self.portrait_label.setStyleSheet(
            f"border: 2px solid {COLORS.BORDER_LIGHT}; background: {COLORS.BG_DARK};"
        )
        self._set_placeholder_portrait()
        portrait_layout_inner.addWidget(
            self.portrait_label, alignment=Qt.AlignmentFlag.AlignCenter
        )

        # Corp logo (bottom-left). Positioning is calculated relative to the
        # portrait label so that the inset from the portrait border is equal on
        # both left and right sides. We compute the border inset from the
        # portrait label stylesheet (fallback to 0) rather than using hard
        # coded magic numbers in multiple places.
        self.corp_logo_label = QLabel(portrait_container)
        self.corp_logo_label.setFixedSize(logo_size, logo_size)
        self.corp_logo_label.setScaledContents(True)
        self.corp_logo_label.setStyleSheet(
            f"border: 1px solid {COLORS.BORDER_LIGHT}; background: {COLORS.BG_DARK};"
        )
        self.corp_logo_label.hide()

        # Alliance logo (bottom-right)
        self.alliance_logo_label = QLabel(portrait_container)
        self.alliance_logo_label.setFixedSize(logo_size, logo_size)
        self.alliance_logo_label.setScaledContents(True)
        self.alliance_logo_label.setStyleSheet(
            "border: 1px solid #555; background: #111;"
        )
        self.alliance_logo_label.hide()

        # Refresh button overlay (circular)
        self.refresh_button = QPushButton("↻", portrait_container)
        self.refresh_button.setFixedSize(64, 64)
        self.refresh_button.setStyleSheet("""
            QPushButton {
            background-color: rgba(13, 115, 119, 200);
            color: white;
            border: none;
            border-radius: 32px;  /* Half of width/height for circle */
            font-size: 38px;
            font-weight: bold;
            min-width: 64px;
            min-height: 64px;
            max-width: 64px;
            max-height: 64px;
            }
            QPushButton:hover {
            background-color: rgba(20, 161, 168, 220);
            }
            QPushButton:pressed {
            background-color: rgba(10, 90, 93, 200);
            }
        """)
        self.refresh_button.setToolTip("Refresh this character")
        self.refresh_button.move(portrait_size // 2 - 32, portrait_size // 2 - 32)
        self.refresh_button.hide()
        self.refresh_button.clicked.connect(
            lambda: self.refresh_requested.emit(self.character_id)
        )
        portrait_container.installEventFilter(self)

        # Position the logos using the portrait label's border inset so both
        # left and right inner margins are equal. Use a small helper to parse
        # the border width from the stylesheet (robust with a sensible fallback).
        try:

            def _border_px_from_stylesheet(widget: QLabel) -> int:
                ss = widget.styleSheet() or ""
                m = re.search(r"border:\s*(\d+)px", ss)
                if m:
                    try:
                        return int(m.group(1))
                    except Exception:
                        return 0
                return 0

            inset = _border_px_from_stylesheet(self.portrait_label)
            # Place logos inset from the portrait edges to keep symmetry.
            # The alliance logo needs an extra pixel adjustment to account for
            # its own border, ensuring the visual gap is identical on both sides.
            self.corp_logo_label.move(inset, portrait_size - logo_size - inset)
            self.alliance_logo_label.move(
                portrait_size - logo_size - inset - 1, portrait_size - logo_size - inset
            )
        except Exception:
            # Fallback to previous behavior if parsing fails.
            self.corp_logo_label.move(0, portrait_size - logo_size)
            self.alliance_logo_label.move(
                portrait_size - logo_size, portrait_size - logo_size
            )
        # Info section (name, corp, alliance) - stacked vertically above portrait
        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        # Character name
        name_value = getattr(
            character, "character_name", str(getattr(character, "character_id", ""))
        )
        self.name_label = QLabel(name_value)
        self.name_label.setStyleSheet(
            f"font-weight: bold; font-size: {name_font_size}px; color: #fff;"
        )
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.name_label.setWordWrap(False)
        # Keep a reasonably small minimum to avoid forcing a huge left column
        self.name_label.setMinimumWidth(90)
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        self.name_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_layout.addWidget(self.name_label)

        # Corporation name
        corp_name_val = getattr(character, "corporation_name", None)
        if corp_name_val:
            self.corp_name = QLabel(str(corp_name_val))
            self.corp_name.setStyleSheet(
                f"color: {COLORS.TEXT_SECONDARY}; font-size: {corp_font_size}px;"
            )
            self.corp_name.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.corp_name.setWordWrap(False)
            self.corp_name.setMinimumWidth(60)
            self.corp_name.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            info_layout.addWidget(self.corp_name)

        # Alliance name
        alliance_name_val = getattr(character, "alliance_name", None)
        if alliance_name_val:
            self.alliance_name = QLabel(str(alliance_name_val))
            self.alliance_name.setStyleSheet(
                f"color: {COLORS.TEXT_SECONDARY}; font-size: {corp_font_size}px;"
            )
            self.alliance_name.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.alliance_name.setWordWrap(False)
            self.alliance_name.setMinimumWidth(60)
            self.alliance_name.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            info_layout.addWidget(self.alliance_name)

        info_layout.addStretch()
        left_layout.addLayout(info_layout)
        left_layout.addWidget(portrait_container, alignment=Qt.AlignmentFlag.AlignTop)
        main_layout.addLayout(left_layout, stretch=0)

        # --- RIGHT SIDE: Networth grid ---
        self._right_container = QWidget()
        # Allow the right-side to expand horizontally and size appropriately
        # vertically. Previously Maximum capped vertical size which could hide
        # timers and networth when toggling visibility.
        self._right_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        right_layout = QVBoxLayout(self._right_container)
        right_layout.setContentsMargins(0, 4, 0, 0)
        right_layout.setSpacing(0)

        # Networth container (grid with label/value/timer columns)
        self._networth_container = QWidget()
        # Allow the networth container to size itself horizontally and not be
        # artificially clipped. Vertical growth should be constrained by items.
        self._networth_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self._networth_grid = QGridLayout(self._networth_container)
        self._networth_grid.setContentsMargins(0, 0, 0, 0)
        self._networth_grid.setHorizontalSpacing(2)  # Tighter spacing between columns
        self._networth_grid.setVerticalSpacing(0)  # Tighter vertical spacing
        # Columns: label (minimal), value (minimal), timer (conditional)
        # Keep all columns with 0 stretch so they don't expand
        self._networth_grid.setColumnStretch(0, 0)
        self._networth_grid.setColumnStretch(1, 0)
        self._networth_grid.setColumnStretch(2, 0)
        # Timer column width will be set dynamically based on visibility
        # Don't reserve space when hidden to avoid wasted horizontal space

        # Top-align a spacer so the networth grid sits at the bottom of the
        # right side (matching the card UI where the portrait is above).
        right_layout.addStretch()
        right_layout.addWidget(self._networth_container)
        main_layout.addWidget(self._right_container, stretch=1)

        # Size policy: Maximum width to prevent expansion, Minimum height to grow with content
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        self._update_width_constraints()

    def _update_width_constraints(self) -> None:
        """Update widget width constraints based on portrait size and networth visibility."""
        portrait_size = self._settings.get_portrait_size()

        # Width varies based on networth visibility
        rc = getattr(self, "_right_container", None)
        if self._networth_visible and self._view_mode == "card":
            # Calculate minimum width based on actual content
            # Portrait + small buffer for name column + networth grid
            base_width = portrait_size + 120  # Reduced from 140 for tighter layout

            # Add extra width only if timers are visible (smaller timer column)
            if self._timers_visible:
                base_width += 40  # Reduced from 50 for compact timer column

            self.setMinimumWidth(base_width)
            # Allow some expansion but not unlimited
            self.setMaximumWidth(base_width + 80)

            if rc is not None:
                # Tighter constraints for right container
                min_rc_width = (
                    110 if not self._timers_visible else 130
                )  # Reduced widths
                rc.setMinimumWidth(min_rc_width)
                rc.setMaximumWidth(min_rc_width + 40)
        else:
            # More compact when networth is hidden
            self.setMinimumWidth(0)
            self.setMaximumWidth(portrait_size + 100)
            if rc is not None:
                rc.setMinimumWidth(0)
                rc.setMaximumWidth(0)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802  # type: ignore[override]
        """Handle events for child widgets (hover on portrait)."""
        # Show refresh button on hover over portrait container
        try:
            show_hover = self._settings.get_show_refresh_on_hover()
        except Exception:
            logger.debug("Failed to get show_refresh_on_hover setting", exc_info=True)
            show_hover = True
        if hasattr(self, "refresh_button") and show_hover:
            if event.type() == QEvent.Type.Enter:
                self.refresh_button.show()
            elif event.type() == QEvent.Type.Leave:
                self.refresh_button.hide()
        return super().eventFilter(obj, event)

    # --- Placeholders -----------------------------------------------------
    def _set_placeholder_portrait(self) -> None:
        portrait_size = self._settings.get_portrait_size()
        pixmap = QPixmap(portrait_size, portrait_size)
        pixmap.fill(Qt.GlobalColor.darkGray)
        self.portrait_label.setPixmap(pixmap)

    def _set_placeholder_logo(self, label: QLabel) -> None:
        pixmap = QPixmap(label.width(), label.height())
        pixmap.fill(Qt.GlobalColor.darkGray)
        label.setPixmap(pixmap)

    # --- Public API: image setters ----------------------------------------
    def set_portrait(self, img_data: bytes | bytearray | memoryview | None) -> None:
        """Set the character portrait image from raw bytes.

        Silently ignores invalid data and keeps the current/placeholder image.
        """
        pixmap = self._pixmap_from_data(img_data)
        if pixmap is not None:
            self.portrait_label.setPixmap(pixmap)

    def set_corp_logo(self, img_data: bytes | bytearray | memoryview | None) -> None:
        """Set the corporation logo image from raw bytes, if applicable."""
        pixmap = self._pixmap_from_data(img_data)
        if pixmap is not None:
            self.corp_logo_label.setPixmap(pixmap)
            self.corp_logo_label.show()

    def set_alliance_logo(
        self, img_data: bytes | bytearray | memoryview | None
    ) -> None:
        """Set the alliance logo image from raw bytes, if applicable."""
        pixmap = self._pixmap_from_data(img_data)
        if pixmap is not None:
            self.alliance_logo_label.setPixmap(pixmap)
            self.alliance_logo_label.show()

    def set_networth(self, snapshot: object | None) -> None:
        """Render latest networth numbers in a readable grid layout.

        Expects an object with fields like wallet_balance, total_asset_value,
        market_escrow, market_sell_value, contract_collateral, contract_value,
        industry_job_value, plex_vault.
        """
        try:
            self._networth_snapshot = snapshot
            if snapshot is None:
                if self._networth_container is not None:
                    self._networth_container.setVisible(False)
                rc = getattr(self, "_right_container", None)
                if rc is not None:
                    rc.setVisible(False)
                self._update_width_constraints()
                return
            # Clear previous networth grid and (possible timer widgets)
            while self._networth_grid.count():
                item = self._networth_grid.takeAt(0)
                if item is None:
                    continue
                w = item.widget() if hasattr(item, "widget") else None
                if w:
                    w.deleteLater()
            networth_font_size = self._settings.get_networth_font_size()
            # Use compact labels to save horizontal space
            data_items = [
                ("Wallet", self._format_isk(getattr(snapshot, "wallet_balance", 0))),
                ("Assets", self._format_isk(getattr(snapshot, "total_asset_value", 0))),
                ("Sell", self._format_isk(getattr(snapshot, "market_sell_value", 0))),
                ("Escrow", self._format_isk(getattr(snapshot, "market_escrow", 0))),
                ("Contr.", self._format_isk(getattr(snapshot, "contract_value", 0))),
                (
                    "Collat.",
                    self._format_isk(getattr(snapshot, "contract_collateral", 0)),
                ),
                (
                    "Indust.",
                    self._format_isk(getattr(snapshot, "industry_job_value", 0)),
                ),
                ("Skills", "—"),  # Placeholder for skills endpoint timer
            ]
            for row, (label_text, value_text) in enumerate(data_items):
                label = QLabel(label_text)
                label.setStyleSheet(
                    f"color: {COLORS.TEXT_MUTED}; font-size: {networth_font_size}px;"
                )
                label.setAlignment(Qt.AlignmentFlag.AlignLeft)
                label.setContentsMargins(0, 0, 0, 0)  # Remove all margins
                label.setMinimumWidth(0)
                label.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
                )
                value = QLabel(value_text)
                value.setStyleSheet(
                    f"color: {COLORS.TEXT_SECONDARY}; font-size: {networth_font_size}px; font-weight: bold;"
                )
                # Left-align the values so they sit directly after the label
                # and don't float to the right edge of the container.
                value.setAlignment(Qt.AlignmentFlag.AlignLeft)
                # Keep value minimal so it follows the label tightly; do not
                # allow expansion which would push the timer away.
                value.setSizePolicy(
                    QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
                )
                # Minimal margins - just 1px left to separate from label
                value.setContentsMargins(1, 0, 0, 0)
                value.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                self._networth_grid.addWidget(
                    label, row, 0, alignment=Qt.AlignmentFlag.AlignLeft
                )
                self._networth_grid.addWidget(
                    value, row, 1, alignment=Qt.AlignmentFlag.AlignLeft
                )
            # Add endpoint timers into the grid (column 2) - always show when timers visible
            if self._timers_visible:
                for row, (label_text, _) in enumerate(data_items):
                    endpoint_key = self._get_endpoint_key_for_item(label_text)
                    # Always create timer widget, set expiry if available
                    timer_widget = EndpointTimer("", self, compact=True)
                    if endpoint_key and endpoint_key in self._endpoint_timers:
                        timer_seconds = self._endpoint_timers[endpoint_key]
                        timer_widget.set_expiry(timer_seconds)
                    else:
                        # Show ready state when no timer data available
                        timer_widget.set_expiry(None)
                    # Tight timer column - smaller fixed width, compact display
                    timer_widget.setFixedHeight(14)
                    timer_widget.setFixedWidth(36)
                    timer_widget.setSizePolicy(
                        QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
                    )
                    # Remove internal margins for tight layout
                    try:
                        inner_layout = timer_widget.layout()
                        if inner_layout is not None:
                            inner_layout.setContentsMargins(0, 0, 0, 0)
                    except Exception:
                        pass
                    timer_widget.show()
                    self._networth_grid.addWidget(
                        timer_widget, row, 2, alignment=Qt.AlignmentFlag.AlignLeft
                    )
            # Ensure networth container visibility is updated
            if self._networth_container is not None:
                self._networth_container.setVisible(self._networth_visible)
            rc = getattr(self, "_right_container", None)
            if rc is not None:
                rc.setVisible(self._networth_visible)
            # Force layout recalculation so the value labels align after the
            # grid is populated and all widgets are created or removed.
            # Calling adjust/update ensures the new column stretches and sizes
            # take effect immediately.
            if self._networth_container is not None:
                self._networth_container.updateGeometry()
                self._networth_container.adjustSize()
            if rc is not None:
                rc.updateGeometry()
                rc.adjustSize()
            self.updateGeometry()
            self._update_width_constraints()

            # Force a repaint to ensure visibility changes take effect immediately
            if self._networth_container is not None:
                self._networth_container.update()
            if rc is not None:
                rc.update()
            self.update()
        except Exception:
            logger.debug("Failed to set networth display", exc_info=True)

    # --- Helpers -----------------------------------------------------------
    @staticmethod
    def _pixmap_from_data(
        img_data: bytes | bytearray | memoryview | None,
    ) -> QPixmap | None:
        """Create a QPixmap from raw bytes-like data.

        Returns None if ``img_data`` is None, is not bytes-like, or fails to
        decode into an image.
        """
        if img_data is None:
            return None
        try:
            if not isinstance(img_data, (bytes, bytearray, memoryview)):
                return None
            data = bytes(img_data)
            pixmap = QPixmap()
            if pixmap.loadFromData(data) and not pixmap.isNull():
                return pixmap
        except Exception:
            # Swallow errors to avoid UI crashes on corrupt data
            logger.debug("Failed to create pixmap from image data", exc_info=True)
            return None
        return None

    def _get_endpoint_key_for_item(self, label_text: str) -> str | None:
        """Map networth label to endpoint cache key."""
        mapping = {
            "Wallet": "wallet",
            "Assets": "assets",
            "Sell": "market_orders",
            "Escrow": "market_orders",
            "Contr.": "contracts",
            "Collat.": "contracts",
            "Indust.": "industry_jobs",
            "Skills": "skills",
        }
        return mapping.get(label_text)

    def set_endpoint_timers(self, timers: dict[str, float | None]) -> None:
        """Set endpoint cache expiry times.

        Args:
            timers: Dictionary mapping endpoint names to seconds until expiry
                   (e.g., {"assets": 300.5, "wallet": None})
        """
        self._endpoint_timers = timers.copy() if timers else {}
        # Refresh networth display if it exists to show updated timers
        if self._networth_snapshot is not None:
            self.set_networth(self._networth_snapshot)

    # --- Public API: refresh and visibility -------------------------------
    def refresh_sizes(self) -> None:
        """Refresh widget sizes based on current settings.

        Call this after settings change to update portrait, fonts, etc.
        """
        try:
            portrait_size = self._settings.get_portrait_size()
            logo_size = max(24, portrait_size // 4)

            # Update portrait and container
            self.portrait_label.setFixedSize(portrait_size, portrait_size)
            parent = self.portrait_label.parentWidget()
            if parent is not None:
                parent.setFixedSize(portrait_size, portrait_size)

            # Update logos
            self.corp_logo_label.setFixedSize(logo_size, logo_size)
            self.alliance_logo_label.setFixedSize(logo_size, logo_size)
            # Recompute inset from portrait border so logos remain symmetrically
            # placed when sizes change.
            try:
                ss = self.portrait_label.styleSheet() or ""
                m = re.search(r"border:\s*(\d+)px", ss)
                inset = int(m.group(1)) if m else 0
            except Exception:
                inset = 0
            # The alliance logo needs an extra pixel adjustment to account for
            # its own border, ensuring the visual gap is identical on both sides.
            self.corp_logo_label.move(inset, portrait_size - logo_size - inset)
            self.alliance_logo_label.move(
                portrait_size - logo_size - inset - 1, portrait_size - logo_size - inset
            )

            # Update font sizes
            name_font_size = self._settings.get_character_name_font_size()
            self.name_label.setStyleSheet(
                f"font-weight: bold; font-size: {name_font_size}px; color: #fff;"
            )

            corp_font_size = self._settings.get_corp_alliance_font_size()
            if hasattr(self, "corp_name"):
                self.corp_name.setStyleSheet(
                    f"color: #bbb; font-size: {corp_font_size}px;"
                )
            if hasattr(self, "alliance_name"):
                self.alliance_name.setStyleSheet(
                    f"color: #bbb; font-size: {corp_font_size}px;"
                )

            # Update width constraints
            self._update_width_constraints()

            # Reload placeholders if needed
            if (
                self.portrait_label.pixmap() is None
                or self.portrait_label.pixmap().isNull()
            ):
                self._set_placeholder_portrait()
            # Ensure sizes/layouts refresh to reflect new font/portrait settings
            rc = getattr(self, "_right_container", None)
            if rc is not None:
                rc.updateGeometry()
                rc.adjustSize()
            self.updateGeometry()
        except Exception:
            logger.debug("Failed to refresh widget sizes", exc_info=True)

    def set_networth_visible(self, visible: bool) -> None:
        """Show or hide the networth section within this item."""
        try:
            self._networth_visible = bool(visible)
            if self._networth_container is not None:
                self._networth_container.setVisible(self._networth_visible)
            rc = getattr(self, "_right_container", None)
            if rc is not None:
                rc.setVisible(self._networth_visible)
                # Ensure min width when visible so values/timers are not clipped
                if self._networth_visible:
                    rc.setMinimumWidth(120)
                else:
                    rc.setMinimumWidth(0)
            # When the networth/right column is hidden we want to keep
            # roughly the same visual margin on the right as on the left.
            # Adjust the main layout margins (increase right margin) when
            # hiding networth and restore defaults when showing it again.
            try:
                if hasattr(self, "_main_layout") and self._main_layout is not None:
                    if not self._networth_visible:
                        left_m, top_m, right_m, bottom_m = (
                            self._default_main_layout_margins
                        )
                        # Use a slightly larger right margin to visually
                        # balance the card when the right-side panel is gone.
                        self._main_layout.setContentsMargins(
                            left_m, top_m, max(right_m, 8), bottom_m
                        )
                    else:
                        self._main_layout.setContentsMargins(
                            *self._default_main_layout_margins
                        )
            except Exception:
                logger.debug("Failed to adjust main layout margins", exc_info=True)
                # Adjust main layout right margin to improve spacing when the
                # networth column is hidden. This avoids a narrow but visually
                # noticeable gap on the right side of the card by increasing
                # the right margin slightly (e.g., from 4 -> 8). When networth
                # is shown, restore the original margins.
                try:
                    ml = getattr(self, "_main_layout", None)
                    default = getattr(self, "_main_layout_default_margins", None)
                    if ml is not None:
                        if not self._networth_visible:
                            # increase right margin to give a bit more breathing room
                            left_, top_, right_, bottom_ = ml.getContentsMargins()
                            # Only change if it's smaller than desired to avoid stomping
                            if right_ < 8:
                                ml.setContentsMargins(left_, top_, 8, bottom_)
                        else:
                            # restore default margins if we have them
                            if default:
                                try:
                                    ml.setContentsMargins(*default)
                                except Exception:
                                    # Fall back to a safe margin set
                                    ml.setContentsMargins(4, 4, 4, 4)
                except Exception:
                    # Non-critical; don't let margin tweaks break visibility toggle
                    pass
            # If networth is hidden, shrink card width
            if not self._networth_visible:
                portrait_size = self._settings.get_portrait_size()
                self.setMinimumWidth(portrait_size + 2)
                self.setMaximumWidth(portrait_size + 80)
            # Force geometry updates so layout reflows reliably
            if rc is not None:
                rc.updateGeometry()
                rc.adjustSize()
            self.updateGeometry()
            # If we have a snapshot, re-render to ensure timers/labels are
            # laid out correctly when toggling visibility.
            if self._networth_visible and self._networth_snapshot is not None:
                self.set_networth(self._networth_snapshot)
            self._update_width_constraints()
        except Exception:
            logger.debug("Failed to set networth visibility", exc_info=True)

    def set_timers_visible(self, visible: bool) -> None:
        """Show or hide endpoint timers in the networth grid.

        Args:
            visible: Whether endpoint timers should be visible
        """
        try:
            was_visible = self._timers_visible
            self._timers_visible = bool(visible)

            # If visibility changed and we have networth data, re-render to properly layout
            if (
                was_visible != self._timers_visible
                and self._networth_snapshot is not None
            ):
                self.set_networth(self._networth_snapshot)
            else:
                # Just update timer visibility without full re-render
                for row in range(self._networth_grid.rowCount()):
                    timer_item = self._networth_grid.itemAtPosition(row, 2)
                    if timer_item is not None:
                        timer_widget = timer_item.widget()
                        if timer_widget is not None:
                            timer_widget.setVisible(visible)

            # Update layout constraints to adjust card width
            self._update_width_constraints()
            self.updateGeometry()

            # Force parent to recalculate layout
            parent = self.parentWidget()
            if parent is not None:
                parent.updateGeometry()

        except Exception:
            logger.debug("Failed to set timers visibility", exc_info=True)

    def _format_isk(self, v: float | int | None) -> str:
        try:
            x = float(v or 0.0)
            if x >= 1_000_000_000:
                return f"{x / 1_000_000_000:.2f}b"
            if x >= 1_000_000:
                return f"{x / 1_000_000:.2f}m"
            if x >= 1_000:
                return f"{x / 1_000:.2f}k"
            return f"{x:.0f}"
        except (TypeError, ValueError):
            logger.debug("Failed to format ISK value: %s", v, exc_info=True)
            return "0"

    def set_view_mode(self, mode: str) -> None:
        """Switch between 'card' and 'list' view modes.

        - card: full portrait and networth grid (if enabled)
        - list: compact row with small portrait, name, corp/alliance; networth hidden
        """
        try:
            m = mode.lower().strip()
            if m not in {"card", "list"}:
                return
            if self._view_mode == m:
                return
            self._view_mode = m

            # Hide logos and networth in list mode
            is_list = m == "list"
            self.corp_logo_label.setVisible(not is_list)
            # Only show alliance logo if character has an alliance and in card mode
            has_alliance = bool(getattr(self.character, "alliance_id", None))
            self.alliance_logo_label.setVisible(not is_list and has_alliance)
            self.set_networth_visible(False if is_list else self._networth_visible)

            # Refresh sizes based on new view mode
            self.refresh_sizes()
        except Exception:
            logger.debug("Failed to set view mode to %s", mode, exc_info=True)
