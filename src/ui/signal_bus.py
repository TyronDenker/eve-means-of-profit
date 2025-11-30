"""Central signal bus for UI events using PyQt6 signals.

Provides a singleton event bus for decoupled communication between UI components.
"""

from PyQt6.QtCore import QObject, pyqtSignal


class SignalBus(QObject):
    """Central event bus for application-wide signals."""

    # Character signals
    character_added = pyqtSignal(dict)  # Emits character_info dict
    character_removed = pyqtSignal(int)  # Emits character_id
    character_updated = pyqtSignal(dict)  # Emits character_info dict
    character_selected = pyqtSignal(int)  # Emits character_id

    # Authentication signals
    auth_started = pyqtSignal()
    auth_completed = pyqtSignal(dict)  # Emits character_info dict
    auth_failed = pyqtSignal(str)  # Emits error message
    auth_cancelled = pyqtSignal()

    # General signals
    error_occurred = pyqtSignal(str)  # Emits error message
    status_message = pyqtSignal(str)  # Emits status message
    info_message = pyqtSignal(str)  # Emits info message


# Global singleton instance
_signal_bus = None


def get_signal_bus() -> SignalBus:
    """Get the global signal bus instance.

    Returns:
        Global SignalBus singleton
    """
    global _signal_bus  # noqa: PLW0603
    if _signal_bus is None:
        _signal_bus = SignalBus()
    return _signal_bus
