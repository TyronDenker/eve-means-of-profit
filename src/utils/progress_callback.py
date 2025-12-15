"""Progress callback infrastructure for async operations.

This module provides:
- ProgressPhase enum for tracking operation stages
- ProgressUpdate dataclass for structured progress information
- CancelToken for signaling cancellation to async operations
- ProgressCallback type alias for progress handler functions

Usage:
    from src.utils.progress_callback import (
        CancelToken,
        ProgressCallback,
        ProgressPhase,
        ProgressUpdate,
    )

    def my_progress_handler(update: ProgressUpdate) -> None:
        print(f"{update.operation}: {update.current}/{update.total} - {update.message}")

    token = CancelToken()
    # Pass my_progress_handler and token to async operations
    # Call token.cancel() to request cancellation
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class ProgressPhase(Enum):
    """Phases of an async operation for progress tracking."""

    STARTING = "starting"
    FETCHING = "fetching"
    PROCESSING = "processing"
    SAVING = "saving"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ProgressUpdate:
    """Structured progress information for async operations.

    Attributes:
        operation: Name of the operation being performed.
        character_id: ID of the character involved, or None if not character-specific.
        phase: Current phase of the operation.
        current: Current progress value (e.g., items processed).
        total: Total expected items (0 if indeterminate).
        message: Human-readable status message.
        detail: Optional additional detail string.
    """

    operation: str
    character_id: int | None
    phase: ProgressPhase
    current: int
    total: int
    message: str
    detail: str | None = None


# Type alias for progress callback functions
ProgressCallback = Callable[[ProgressUpdate], None]


class CancelToken:
    """Token to signal cancellation to async operations.

    Create a CancelToken and pass it to async operations. The operation
    should periodically check is_cancelled and exit gracefully if True.

    Example:
        token = CancelToken()

        async def my_operation(token: CancelToken):
            for item in items:
                if token.is_cancelled:
                    return  # Exit gracefully
                await process(item)

        # To cancel from another context:
        token.cancel()
    """

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        """Signal cancellation to the operation."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled

    def reset(self) -> None:
        """Reset the cancellation state for reuse."""
        self._cancelled = False
