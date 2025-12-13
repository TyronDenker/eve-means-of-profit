"""Reusable widget to display a 'Ready' state or a live countdown until expiry.

Public API:
- class EndpointTimer(QWidget)
  - set_expiry(seconds_until_expiry: float | int | None) -> None

This module is self-contained and only depends on PyQt6 and datetime. It
updates the UI once per second and uses UTC-aware datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.styles import COLORS


class EndpointTimer(QWidget):
    """Widget showing time until an endpoint can be refreshed.

    Parameters:
        endpoint_name:
            Display name shown to the left of the timer.
        parent:
            Optional parent widget.
    """

    def __init__(
        self, endpoint_name: str, parent: QWidget | None = None, compact: bool = False
    ) -> None:
        super().__init__(parent)
        self.endpoint_name = endpoint_name
        self._expires_at: datetime | None = None
        self._compact = compact

        layout = QHBoxLayout(self)
        # Minimal margins in compact mode for tighter layout
        layout.setContentsMargins(
            0 if compact else 4,
            0 if compact else 4,
            0 if compact else 4,
            0 if compact else 4,
        )
        layout.setSpacing(0)

        # Endpoint name label (only show in non-compact mode)
        self.name_label = QLabel(f"{endpoint_name}:")
        if compact:
            self.name_label.setVisible(False)
            self.name_label.setMinimumWidth(0)
            self.name_label.setMaximumWidth(0)
        else:
            self.name_label.setMinimumWidth(100)
            layout.addWidget(self.name_label)

        # Timer label - sized appropriately for compact vs normal mode
        self.timer_label = QLabel("✓")
        if compact:
            # Compact mode: tighter constraints, left-aligned
            self.timer_label.setMinimumWidth(28)
            self.timer_label.setMaximumWidth(36)
            self.timer_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self.timer_label.setStyleSheet(f"color: {COLORS.SUCCESS}; font-size: 10px;")
        else:
            self.timer_label.setMinimumWidth(80)
            self.timer_label.setMaximumWidth(100)
            self.timer_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.timer_label)

        if not compact:
            layout.addStretch()

        # Update timer every second
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_display)
        self._update_timer.start(1000)

    # --- Public API --------------------------------------------------------
    def set_expiry(self, seconds_until_expiry: float | int | None) -> None:
        """Set the expiry time, relative to now.

        Parameters
        ----------
        seconds_until_expiry:
            Seconds until expiry; if None or not positive, becomes ready state.
        """
        if seconds_until_expiry is not None and float(seconds_until_expiry) > 0:
            self._expires_at = datetime.now(UTC) + timedelta(
                seconds=float(seconds_until_expiry)
            )
        else:
            self._expires_at = None
        self._update_display()

    # --- Internals ---------------------------------------------------------
    @pyqtSlot()
    def _update_display(self) -> None:
        """Update the timer display label and color."""
        # Adjust font size based on compact mode
        font_size = "10px" if self._compact else "12px"

        if self._expires_at is None:
            self.timer_label.setText("✓")
            self.timer_label.setStyleSheet(
                f"color: {COLORS.SUCCESS}; font-weight: bold; font-size: {font_size};"
            )
            return

        now = datetime.now(UTC)
        if now >= self._expires_at:
            self.timer_label.setText("✓")
            self.timer_label.setStyleSheet(
                f"color: {COLORS.SUCCESS}; font-weight: bold; font-size: {font_size};"
            )
            self._expires_at = None
            return

        remaining = self._expires_at - now
        total_seconds = int(remaining.total_seconds())
        days, remainder = divmod(total_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Use compact format: show only most significant unit
        if days > 0:
            self.timer_label.setText(f"{days}d")
        elif hours > 0:
            self.timer_label.setText(f"{hours}h")
        elif minutes > 0:
            self.timer_label.setText(f"{minutes}m")
        else:
            self.timer_label.setText(f"{seconds}s")
        self.timer_label.setStyleSheet(
            f"color: {COLORS.WARNING}; font-size: {font_size};"
        )
