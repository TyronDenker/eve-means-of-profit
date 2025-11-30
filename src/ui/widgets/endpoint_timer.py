"""Reusable widget to display a 'Ready' state or a live countdown until expiry.

Public API:
- class EndpointTimer(QWidget)
  - set_expiry(seconds_until_expiry: float | int | None) -> None

This module is self-contained and only depends on PyQt6 and datetime. It
updates the UI once per second and uses UTC-aware datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from PyQt6.QtCore import QTimer, Qt, pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


class EndpointTimer(QWidget):
    """Widget showing time until an endpoint can be refreshed.

    Parameters:
        endpoint_name:
            Display name shown to the left of the timer.
        parent:
            Optional parent widget.
    """

    def __init__(self, endpoint_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.endpoint_name = endpoint_name
        self._expires_at: datetime | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Endpoint name label
        self.name_label = QLabel(f"{endpoint_name}:")
        self.name_label.setMinimumWidth(100)
        layout.addWidget(self.name_label)

        # Timer label
        self.timer_label = QLabel("--:--:--")
        self.timer_label.setMinimumWidth(80)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.timer_label)

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
        if self._expires_at is None:
            self.timer_label.setText("Ready")
            self.timer_label.setStyleSheet("color: green;")
            return

        now = datetime.now(UTC)
        if now >= self._expires_at:
            self.timer_label.setText("Ready")
            self.timer_label.setStyleSheet("color: green;")
            self._expires_at = None
            return

        remaining = self._expires_at - now
        total_seconds = int(remaining.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        self.timer_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        self.timer_label.setStyleSheet("color: orange;")
