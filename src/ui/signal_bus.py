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
    characters_loaded = pyqtSignal(
        list
    )  # Emits list of CharacterInfo - broadcast to all tabs

    # Structure/location signals
    structures_resolving = pyqtSignal(int, int)  # Emits (current, total) for progress
    structures_resolved = pyqtSignal(int)  # Emits count of structures resolved

    # Authentication signals
    auth_started = pyqtSignal()
    auth_completed = pyqtSignal(dict)  # Emits character_info dict
    auth_failed = pyqtSignal(str)  # Emits error message
    auth_cancelled = pyqtSignal()

    # General signals
    error_occurred = pyqtSignal(str)  # Emits error message
    status_message = pyqtSignal(str)  # Emits status message
    info_message = pyqtSignal(str)  # Emits info message

    # Custom data signals
    custom_price_changed = pyqtSignal(int)  # Emits type_id when custom price is updated
    # Use object to avoid Qt 32-bit int truncation for 13+ digit structure IDs
    # Large EVE structure IDs exceed 32-bit range; emitting as int causes corruption.
    # Emitting as object preserves the full Python int.
    custom_location_changed = pyqtSignal(
        object
    )  # Emits location_id when custom name is updated

    # Endpoint timer updates
    endpoint_timers_updated = pyqtSignal(int, dict)  # (character_id, timers dict)

    # Account management signals
    account_changed = (
        pyqtSignal()
    )  # Emitted when account structure changes (create/delete/assign)
    character_assigned = pyqtSignal(int, object)  # (character_id, account_id or None)

    # Global progress signals for app-wide operations
    progress_start = pyqtSignal(str, int)  # (title, total)
    progress_update = pyqtSignal(int, str)  # (current, message)
    progress_complete = pyqtSignal(str)  # (message)
    progress_error = pyqtSignal(str)  # (message)
    progress_cancel_requested = pyqtSignal()  # User clicked cancel


# Global singleton instance
_signal_bus = None


def get_signal_bus(signal_bus: SignalBus | None = None) -> SignalBus:
    """Get the global signal bus instance.

    Args:
        signal_bus: Optional signal bus to use instead of singleton.
                    If provided on first call, sets the singleton.
                    Useful for dependency injection.

    Returns:
        Global SignalBus singleton
    """
    global _signal_bus  # noqa: PLW0603
    if signal_bus is not None:
        _signal_bus = signal_bus
        return _signal_bus
    if _signal_bus is None:
        _signal_bus = SignalBus()
    return _signal_bus


def reset_signal_bus() -> None:
    """Reset the global signal bus.

    Primarily for testing.
    """
    global _signal_bus  # noqa: PLW0603
    _signal_bus = None
