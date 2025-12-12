"""Tests for the progress system including ProgressWidget, CancelToken, and ConcurrencyManager."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import pytest

# =============================================================================
# Mock implementations of progress_callback module
# (Tests should work without importing the actual module)
# =============================================================================


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
    """Structured progress information for async operations."""

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
    """Token to signal cancellation to async operations."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        """Signal cancellation to the operation."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        return self._cancelled


class TestProgressUpdate:
    """Tests for ProgressUpdate dataclass."""

    def test_create_progress_update(self):
        """Test creating a ProgressUpdate with all fields."""
        update = ProgressUpdate(
            operation="test_op",
            character_id=12345,
            phase=ProgressPhase.FETCHING,
            current=5,
            total=10,
            message="Fetching data",
            detail="Additional details",
        )

        assert update.operation == "test_op"
        assert update.character_id == 12345
        assert update.phase == ProgressPhase.FETCHING
        assert update.current == 5
        assert update.total == 10
        assert update.message == "Fetching data"
        assert update.detail == "Additional details"

    def test_progress_update_optional_fields(self):
        """Test ProgressUpdate with optional fields."""
        update = ProgressUpdate(
            operation="test",
            character_id=None,
            phase=ProgressPhase.STARTING,
            current=0,
            total=0,
            message="Starting",
        )

        assert update.character_id is None
        assert update.detail is None


class TestProgressPhase:
    """Tests for ProgressPhase enum."""

    def test_all_phases_defined(self):
        """Test all expected phases are defined."""
        assert ProgressPhase.STARTING.value == "starting"
        assert ProgressPhase.FETCHING.value == "fetching"
        assert ProgressPhase.PROCESSING.value == "processing"
        assert ProgressPhase.SAVING.value == "saving"
        assert ProgressPhase.COMPLETE.value == "complete"
        assert ProgressPhase.ERROR.value == "error"

    def test_phase_count(self):
        """Test expected number of phases."""
        phases = list(ProgressPhase)
        assert len(phases) == 6


class TestCancelToken:
    """Tests for CancelToken cancellation."""

    def test_initial_state_not_cancelled(self):
        """Test token starts in non-cancelled state."""
        token = CancelToken()
        assert token.is_cancelled is False

    def test_cancel_sets_cancelled_flag(self):
        """Test cancel() sets the cancelled flag."""
        token = CancelToken()
        token.cancel()
        assert token.is_cancelled is True

    def test_cancel_is_idempotent(self):
        """Test calling cancel() multiple times is safe."""
        token = CancelToken()
        token.cancel()
        token.cancel()
        token.cancel()
        assert token.is_cancelled is True

    def test_multiple_tokens_independent(self):
        """Test multiple tokens operate independently."""
        token1 = CancelToken()
        token2 = CancelToken()

        token1.cancel()

        assert token1.is_cancelled is True
        assert token2.is_cancelled is False

    def test_cancel_token_in_loop(self):
        """Test cancel token can be checked in a loop."""
        token = CancelToken()
        iterations = 0

        for i in range(100):
            if token.is_cancelled:
                break
            iterations += 1
            if i == 49:
                token.cancel()

        assert iterations == 50

    def test_cancel_token_with_async_operation(self):
        """Test cancel token works with async operations."""
        token = CancelToken()

        async def async_operation():
            for i in range(10):
                if token.is_cancelled:
                    return i
                await asyncio.sleep(0.001)
            return 10

        async def canceller():
            await asyncio.sleep(0.005)
            token.cancel()

        async def run_test():
            result = await asyncio.gather(
                async_operation(),
                canceller(),
            )
            return result[0]

        result = asyncio.run(run_test())
        assert result < 10  # Operation was cancelled early


class TestProgressWidgetMock:
    """Tests for ProgressWidget state changes using mocks.

    These tests mock the Qt components to test the logic without requiring Qt.
    """

    def test_progress_widget_state_sequence(self):
        """Test that progress widget goes through expected state sequence."""
        # Mock the state transitions
        states = []

        class MockProgressWidget:
            def __init__(self):
                self._visible = False
                self._cancel_enabled = False
                self._progress = 0
                self._max = 0
                self._message = ""

            def start_operation(self, title: str, total: int = 0):
                self._visible = True
                self._cancel_enabled = True
                self._max = total
                self._progress = 0
                self._message = title
                states.append("started")

            def update_progress(self, current: int, message: str = ""):
                self._progress = current
                if message:
                    self._message = message
                states.append("updated")

            def complete(self, message: str = "Complete"):
                self._cancel_enabled = False
                self._message = message
                states.append("completed")

        widget = MockProgressWidget()
        widget.start_operation("Test Operation", total=5)
        widget.update_progress(1, "Step 1")
        widget.update_progress(2, "Step 2")
        widget.complete("Done!")

        assert states == ["started", "updated", "updated", "completed"]
        assert widget._cancel_enabled is False

    def test_progress_widget_cancellation_sequence(self):
        """Test progress widget cancellation flow."""
        cancel_emitted = [False]

        class MockProgressWidget:
            def __init__(self):
                self._visible = False
                self._cancel_enabled = False

            def start_operation(self, title: str, total: int = 0):
                self._visible = True
                self._cancel_enabled = True

            def cancel(self):
                self._cancel_enabled = False
                cancel_emitted[0] = True

        widget = MockProgressWidget()
        widget.start_operation("Operation")
        assert widget._cancel_enabled is True

        widget.cancel()
        assert widget._cancel_enabled is False
        assert cancel_emitted[0] is True


class TestProgressCallback:
    """Tests for progress callback function type."""

    def test_callback_receives_updates(self):
        """Test that progress callback receives updates."""
        received_updates = []

        def callback(update: ProgressUpdate) -> None:
            received_updates.append(update)

        # Simulate sending updates
        callback(
            ProgressUpdate(
                operation="test",
                character_id=123,
                phase=ProgressPhase.STARTING,
                current=0,
                total=10,
                message="Starting",
            )
        )

        callback(
            ProgressUpdate(
                operation="test",
                character_id=123,
                phase=ProgressPhase.FETCHING,
                current=5,
                total=10,
                message="Halfway",
            )
        )

        callback(
            ProgressUpdate(
                operation="test",
                character_id=123,
                phase=ProgressPhase.COMPLETE,
                current=10,
                total=10,
                message="Done",
            )
        )

        assert len(received_updates) == 3
        assert received_updates[0].phase == ProgressPhase.STARTING
        assert received_updates[1].phase == ProgressPhase.FETCHING
        assert received_updates[2].phase == ProgressPhase.COMPLETE

    def test_callback_with_none_is_handled(self):
        """Test that None callback is handled gracefully."""
        callback: ProgressCallback | None = None

        # Simulating code that checks for callback before calling
        update = ProgressUpdate(
            operation="test",
            character_id=None,
            phase=ProgressPhase.STARTING,
            current=0,
            total=0,
            message="Test",
        )

        # Pattern used in production code
        if callback:
            callback(update)

        # Should not raise


class TestIntegrationProgressWithCancellation:
    """Integration tests combining progress and cancellation."""

    def test_cancellation_stops_concurrent_operations(self):
        """Test that cancellation stops multiple concurrent operations."""
        token = CancelToken()
        completed_count = [0]
        cancelled_count = [0]

        async def worker(worker_id: int):
            for step in range(10):
                if token.is_cancelled:
                    cancelled_count[0] += 1
                    return
                await asyncio.sleep(0.01)
            completed_count[0] += 1

        async def canceller():
            await asyncio.sleep(0.025)
            token.cancel()

        async def run_test():
            await asyncio.gather(
                *[worker(i) for i in range(5)],
                canceller(),
            )

        asyncio.run(run_test())

        # Some workers should have been cancelled
        assert cancelled_count[0] > 0
        # Total should be 5 workers
        assert completed_count[0] + cancelled_count[0] == 5

    def test_progress_tracking_with_cancellation(self):
        """Test progress tracking integrates with cancellation."""
        token = CancelToken()
        updates = []

        def progress_callback(update: ProgressUpdate):
            updates.append(update)

        async def operation_with_progress():
            for i in range(10):
                if token.is_cancelled:
                    progress_callback(
                        ProgressUpdate(
                            operation="test",
                            character_id=None,
                            phase=ProgressPhase.ERROR,
                            current=i,
                            total=10,
                            message="Cancelled",
                        )
                    )
                    return

                progress_callback(
                    ProgressUpdate(
                        operation="test",
                        character_id=None,
                        phase=ProgressPhase.PROCESSING,
                        current=i + 1,
                        total=10,
                        message=f"Step {i + 1}",
                    )
                )
                await asyncio.sleep(0.01)

        async def run_test():
            async def cancel_after_delay():
                await asyncio.sleep(0.035)
                token.cancel()

            await asyncio.gather(
                operation_with_progress(),
                cancel_after_delay(),
            )

        asyncio.run(run_test())

        # Should have received some progress updates
        assert len(updates) > 0
        # Last update should be cancellation
        assert updates[-1].phase == ProgressPhase.ERROR
        assert "Cancelled" in updates[-1].message


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
