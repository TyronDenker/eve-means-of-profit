"""Embedded progress bar widget for async operations.

Public API:
- class ProgressWidget(QWidget)
  - start_operation(title: str, total: int = 0) -> None
  - update_progress(current: int, message: str = "") -> None
  - complete() -> None
  - cancel_clicked: pyqtSignal (emitted when cancel is clicked)

This module provides a non-modal progress indicator that can be embedded
in the main window layout, showing progress for background operations
without blocking user interaction.
"""

from __future__ import annotations

from PyQt6.QtCore import QSize, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ui.styles import COLORS


class ProgressWidget(QWidget):
    """Embedded progress bar for async operations.

    A horizontal widget containing a progress bar, status label, and cancel
    button. Designed to be embedded in the main window layout rather than
    shown as a modal dialog.

    Signals:
        cancel_clicked: Emitted when the cancel button is clicked.

    Parameters:
        parent: Optional parent widget.
    """

    cancel_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._on_hide_timer)
        # Start hidden
        self.setVisible(False)

    def sizeHint(self) -> QSize:
        """Return preferred size for status bar integration."""
        return QSize(400, 22)

    def _setup_ui(self) -> None:
        """Set up the widget UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(4)

        # Progress bar - compact for status bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimumWidth(100)
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)  # No text in status bar version
        self._progress_bar.setFixedHeight(14)  # Smaller height for status bar
        self._progress_bar.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._progress_bar)

        # Status label - shorter for status bar
        self._status_label = QLabel()
        self._status_label.setMinimumWidth(80)
        self._status_label.setMaximumWidth(200)
        self._status_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._status_label)

        # Cancel button - smaller for status bar
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setFixedWidth(50)
        self._cancel_button.setFixedHeight(16)
        self._cancel_button.setStyleSheet("""
            QPushButton {
                font-size: 9px;
                padding: 0px 4px;
            }
        """)
        self._cancel_button.clicked.connect(self._on_cancel_clicked)
        layout.addWidget(self._cancel_button)

        # Styling - compact for status bar
        self.setStyleSheet(f"""
            ProgressWidget {{
                background-color: transparent;
                border: none;
                padding: 0px;
            }}
            QProgressBar {{
                border: 1px solid {COLORS.BORDER_LIGHT};
                border-radius: 2px;
                background-color: {COLORS.BG_LIGHT};
                padding: 1px;
            }}
            QProgressBar::chunk {{
                background-color: {COLORS.SUCCESS};
                border-radius: 1px;
            }}
            QLabel {{
                color: {COLORS.TEXT_SECONDARY};
                font-size: 9px;
                padding: 0px 2px;
            }}
            QPushButton {{
                background-color: {COLORS.BORDER_LIGHT};
                border: 1px solid #666;
                border-radius: 2px;
                color: {COLORS.TEXT_SECONDARY};
                padding: 2px 4px;
            }}
            QPushButton:hover {{
                background-color: #666;
            }}
            QPushButton:pressed {{
                background-color: {COLORS.BORDER_MEDIUM};
            }}
        """)

    def start_operation(self, title: str, total: int = 0) -> None:
        """Start showing progress for an operation.

        Parameters:
            title: The operation title to display.
            total: Total number of steps (0 for indeterminate progress).
        """
        self._hide_timer.stop()
        self._cancel_button.setEnabled(True)

        if total > 0:
            self._progress_bar.setMaximum(total)
            self._progress_bar.setValue(0)
        else:
            # Indeterminate progress
            self._progress_bar.setMaximum(0)
            self._progress_bar.setValue(0)

        self._status_label.setText(title)
        self.setVisible(True)

    def update_progress(self, current: int, message: str = "") -> None:
        """Update the progress display.

        Parameters:
            current: Current progress value.
            message: Optional status message to display.
        """
        # Ensure current is an integer
        current = int(current)

        if self._progress_bar.maximum() > 0:
            # Cap the value at maximum to avoid errors
            value = min(current, self._progress_bar.maximum())
            self._progress_bar.setValue(value)

        if message:
            self._status_label.setText(message)

    def set_indeterminate(self, indeterminate: bool = True) -> None:
        """Switch between determinate and indeterminate progress.

        Parameters:
            indeterminate: True for indeterminate (spinning) progress.
        """
        if indeterminate:
            self._progress_bar.setMaximum(0)
        else:
            self._progress_bar.setMaximum(100)

    def complete(self, message: str = "Complete", hide_delay_ms: int = 1500) -> None:
        """Mark operation as complete and hide after delay.

        Parameters:
            message: Completion message to display.
            hide_delay_ms: Milliseconds before hiding the widget.
        """
        self._cancel_button.setEnabled(False)

        # Ensure progress bar shows full
        if self._progress_bar.maximum() > 0:
            self._progress_bar.setValue(self._progress_bar.maximum())

        self._status_label.setText(message)

        # Schedule hide
        self._hide_timer.start(hide_delay_ms)

    def error(self, message: str = "Error", hide_delay_ms: int = 3000) -> None:
        """Mark operation as failed and hide after delay.

        Parameters:
            message: Error message to display.
            hide_delay_ms: Milliseconds before hiding the widget.
        """
        self._cancel_button.setEnabled(False)
        self._status_label.setText(message)
        self._status_label.setStyleSheet(f"color: {COLORS.ERROR};")

        # Schedule hide
        self._hide_timer.start(hide_delay_ms)

    def cancel(self) -> None:
        """Programmatically cancel and hide the progress widget."""
        self._cancel_button.setEnabled(False)
        self._status_label.setText("Cancelled")
        self._hide_timer.start(1000)

    def _on_cancel_clicked(self) -> None:
        """Handle cancel button click."""
        self._cancel_button.setEnabled(False)
        self._status_label.setText("Cancelling...")
        self.cancel_clicked.emit()

    def _on_hide_timer(self) -> None:
        """Handle hide timer timeout."""
        self.setVisible(False)
        # Reset label style in case it was changed for error
        self._status_label.setStyleSheet("")
