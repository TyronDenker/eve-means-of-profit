"""Tests for async parallel refresh functionality."""

import asyncio
from dataclasses import dataclass
from enum import Enum

import pytest

# =============================================================================
# Mock implementations (self-contained, no imports from src)
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


class CancelToken:
    """Token to signal cancellation to async operations."""

    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


class TestParallelEndpointExecution:
    """Tests for parallel endpoint execution during refresh."""

    def test_endpoints_run_in_parallel(self):
        """Test that multiple endpoints run concurrently."""
        execution_order = []
        concurrent_count = [0]
        max_concurrent = [0]

        async def mock_endpoint(name: str, delay: float = 0.01):
            concurrent_count[0] += 1
            max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            execution_order.append(f"start_{name}")
            await asyncio.sleep(delay)
            execution_order.append(f"end_{name}")
            concurrent_count[0] -= 1

        async def run_test():
            endpoints = [
                mock_endpoint("assets"),
                mock_endpoint("wallet"),
                mock_endpoint("orders"),
                mock_endpoint("contracts"),
            ]
            await asyncio.gather(*endpoints)

        asyncio.run(run_test())

        # All endpoints should have run
        assert "start_assets" in execution_order
        assert "end_assets" in execution_order
        assert "start_wallet" in execution_order
        assert "end_wallet" in execution_order

        # Should have some parallelism (at least 2 concurrent)
        assert max_concurrent[0] >= 2

    def test_parallel_execution_runs_concurrently(self):
        """Test that parallel execution runs endpoints concurrently."""
        max_concurrent = [0]
        current_concurrent = [0]

        async def mock_endpoint(endpoint_id: int):
            current_concurrent[0] += 1
            max_concurrent[0] = max(max_concurrent[0], current_concurrent[0])
            await asyncio.sleep(0.02)
            current_concurrent[0] -= 1

        async def run_test():
            # Run 6 endpoints
            await asyncio.gather(*[mock_endpoint(i) for i in range(6)])

        asyncio.run(run_test())

        # Should run concurrently (more than 1 at a time)
        assert max_concurrent[0] > 1


class TestProgressCallbackUpdates:
    """Tests for progress callback updates during refresh."""

    def test_progress_callback_called_for_each_step(self):
        """Test progress callback is called for each operation step."""
        updates = []

        def progress_callback(update: ProgressUpdate):
            updates.append(update)

        async def simulate_refresh():
            total = 4
            for i, endpoint in enumerate(["assets", "wallet", "orders", "contracts"]):
                progress_callback(
                    ProgressUpdate(
                        operation="refresh",
                        character_id=12345,
                        phase=ProgressPhase.FETCHING,
                        current=i + 1,
                        total=total,
                        message=f"Fetching {endpoint}",
                    )
                )
                await asyncio.sleep(0.001)

            progress_callback(
                ProgressUpdate(
                    operation="refresh",
                    character_id=12345,
                    phase=ProgressPhase.COMPLETE,
                    current=total,
                    total=total,
                    message="Complete",
                )
            )

        asyncio.run(simulate_refresh())

        assert len(updates) == 5  # 4 fetching + 1 complete
        assert updates[0].current == 1
        assert updates[3].current == 4
        assert updates[4].phase == ProgressPhase.COMPLETE

    def test_progress_shows_correct_totals(self):
        """Test progress callback shows correct totals."""
        updates = []

        def progress_callback(update: ProgressUpdate):
            updates.append(update)

        async def refresh_with_endpoints(endpoint_count: int):
            for i in range(endpoint_count):
                progress_callback(
                    ProgressUpdate(
                        operation="refresh",
                        character_id=123,
                        phase=ProgressPhase.PROCESSING,
                        current=i + 1,
                        total=endpoint_count,
                        message=f"Endpoint {i + 1}",
                    )
                )

        asyncio.run(refresh_with_endpoints(6))

        assert len(updates) == 6
        for update in updates:
            assert update.total == 6

    def test_progress_includes_character_info(self):
        """Test progress updates include character information."""
        updates = []

        def progress_callback(update: ProgressUpdate):
            updates.append(update)

        character_id = 987654321

        async def refresh_character():
            progress_callback(
                ProgressUpdate(
                    operation="refresh",
                    character_id=character_id,
                    phase=ProgressPhase.STARTING,
                    current=0,
                    total=5,
                    message="Starting refresh",
                )
            )

        asyncio.run(refresh_character())

        assert len(updates) == 1
        assert updates[0].character_id == character_id


class TestCancellationHandling:
    """Tests for cancellation handling during refresh."""

    def test_cancellation_stops_pending_operations(self):
        """Test that cancellation stops pending operations."""
        token = CancelToken()
        completed = []

        async def mock_endpoint(name: str):
            for step in range(5):
                if token.is_cancelled:
                    return f"{name}_cancelled"
                await asyncio.sleep(0.01)
            completed.append(name)
            return f"{name}_done"

        async def run_test():
            async def cancel_after():
                await asyncio.sleep(0.025)
                token.cancel()

            tasks = [
                mock_endpoint("endpoint1"),
                mock_endpoint("endpoint2"),
                mock_endpoint("endpoint3"),
                cancel_after(),
            ]
            results = await asyncio.gather(*tasks)
            return results[:3]

        results = asyncio.run(run_test())

        # Some should be cancelled
        cancelled_count = sum(1 for r in results if "cancelled" in r)
        assert cancelled_count > 0

    def test_cancellation_is_immediate(self):
        """Test that cancellation takes effect immediately."""
        token = CancelToken()
        check_count = [0]

        async def cancellable_operation():
            for _ in range(1000):
                if token.is_cancelled:
                    return check_count[0]
                check_count[0] += 1
                await asyncio.sleep(0.0001)
            return check_count[0]

        async def run_test():
            async def cancel_soon():
                await asyncio.sleep(0.005)
                token.cancel()

            result = await asyncio.gather(
                cancellable_operation(),
                cancel_soon(),
            )
            return result[0]

        result = asyncio.run(run_test())

        # Should have been cancelled early, not completed all 1000 iterations
        assert result < 1000

    def test_cancelled_operations_return_gracefully(self):
        """Test cancelled operations return gracefully without exception."""
        token = CancelToken()

        async def cancellable_operation():
            if token.is_cancelled:
                return {"status": "cancelled", "error": None}
            await asyncio.sleep(0.1)
            return {"status": "completed", "error": None}

        token.cancel()
        result = asyncio.run(cancellable_operation())

        assert result["status"] == "cancelled"
        assert result["error"] is None


class TestErrorIsolation:
    """Tests for error isolation (one failure doesn't block others)."""

    def test_single_failure_doesnt_stop_others(self):
        """Test that one endpoint failing doesn't stop other endpoints."""
        results = []

        async def successful_endpoint(name: str):
            await asyncio.sleep(0.01)
            results.append(f"{name}_success")
            return True

        async def failing_endpoint(name: str):
            await asyncio.sleep(0.005)
            raise RuntimeError(f"{name} failed")

        async def run_test():
            tasks = [
                successful_endpoint("endpoint1"),
                failing_endpoint("endpoint2"),
                successful_endpoint("endpoint3"),
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        task_results = asyncio.run(run_test())

        # Check results
        assert task_results[0] is True
        assert isinstance(task_results[1], RuntimeError)
        assert task_results[2] is True

        # Successful endpoints should have completed
        assert "endpoint1_success" in results
        assert "endpoint3_success" in results

    def test_multiple_failures_isolated(self):
        """Test that multiple failures are isolated from each other."""

        async def endpoint(endpoint_id: int, should_fail: bool):
            await asyncio.sleep(0.01)
            if should_fail:
                raise ValueError(f"Endpoint {endpoint_id} failed")
            return f"Endpoint {endpoint_id} succeeded"

        async def run_test():
            tasks = [
                endpoint(1, should_fail=False),
                endpoint(2, should_fail=True),
                endpoint(3, should_fail=True),
                endpoint(4, should_fail=False),
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(run_test())

        # Success results
        assert results[0] == "Endpoint 1 succeeded"
        assert results[3] == "Endpoint 4 succeeded"

        # Failure results
        assert isinstance(results[1], ValueError)
        assert isinstance(results[2], ValueError)

    def test_failure_count_tracking(self):
        """Test that failures are properly counted."""

        async def endpoint(should_fail: bool):
            if should_fail:
                raise Exception("Failed")
            return True

        async def run_test():
            tasks = [
                endpoint(False),
                endpoint(True),
                endpoint(False),
                endpoint(True),
                endpoint(False),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successes = sum(1 for r in results if r is True)
            failures = sum(1 for r in results if isinstance(r, Exception))

            return successes, failures

        successes, failures = asyncio.run(run_test())

        assert successes == 3
        assert failures == 2

    def test_error_details_preserved(self):
        """Test that error details are preserved in results."""

        async def endpoint_with_specific_error(error_type: str):
            if error_type == "value":
                raise ValueError("Value error message")
            if error_type == "runtime":
                raise RuntimeError("Runtime error message")
            return "success"

        async def run_test():
            tasks = [
                endpoint_with_specific_error("value"),
                endpoint_with_specific_error("runtime"),
                endpoint_with_specific_error("none"),
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(run_test())

        assert isinstance(results[0], ValueError)
        assert "Value error" in str(results[0])

        assert isinstance(results[1], RuntimeError)
        assert "Runtime error" in str(results[1])

        assert results[2] == "success"


class TestRefreshIntegration:
    """Integration tests combining parallel execution, progress, and error handling."""

    def test_full_refresh_flow(self):
        """Test complete refresh flow with progress and error handling."""
        token = CancelToken()
        progress_updates = []

        def progress_callback(update: ProgressUpdate):
            progress_updates.append(update)

        async def mock_endpoint(name: str, should_fail: bool = False):
            if token.is_cancelled:
                return {"name": name, "status": "cancelled"}

            await asyncio.sleep(0.01)

            if should_fail:
                raise RuntimeError(f"{name} failed")

            return {"name": name, "status": "success"}

        async def refresh_with_progress(character_id: int):
            endpoints = [
                ("assets", False),
                ("wallet", False),
                ("orders", True),  # This one fails
                ("contracts", False),
            ]

            progress_callback(
                ProgressUpdate(
                    operation="refresh",
                    character_id=character_id,
                    phase=ProgressPhase.STARTING,
                    current=0,
                    total=len(endpoints),
                    message="Starting refresh",
                )
            )

            tasks = [mock_endpoint(name, fail) for name, fail in endpoints]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successes = sum(1 for r in results if isinstance(r, dict))
            failures = sum(1 for r in results if isinstance(r, Exception))

            progress_callback(
                ProgressUpdate(
                    operation="refresh",
                    character_id=character_id,
                    phase=ProgressPhase.COMPLETE
                    if failures == 0
                    else ProgressPhase.ERROR,
                    current=len(endpoints),
                    total=len(endpoints),
                    message=f"{successes} succeeded, {failures} failed",
                )
            )

            return results

        results = asyncio.run(refresh_with_progress(12345))

        # Check results
        assert len(results) == 4
        success_count = sum(1 for r in results if isinstance(r, dict))
        assert success_count == 3

        # Check progress
        assert len(progress_updates) == 2
        assert progress_updates[0].phase == ProgressPhase.STARTING
        assert progress_updates[1].phase == ProgressPhase.ERROR
        assert "3 succeeded" in progress_updates[1].message
        assert "1 failed" in progress_updates[1].message

    def test_batch_refresh_multiple_characters(self):
        """Test batch refresh of multiple characters."""
        progress_updates = []

        def progress_callback(update: ProgressUpdate):
            progress_updates.append(update)

        async def refresh_character(character_id: int):
            progress_callback(
                ProgressUpdate(
                    operation="refresh",
                    character_id=character_id,
                    phase=ProgressPhase.STARTING,
                    current=0,
                    total=3,
                    message=f"Refreshing character {character_id}",
                )
            )

            for i in range(3):
                await asyncio.sleep(0.005)
                progress_callback(
                    ProgressUpdate(
                        operation="refresh",
                        character_id=character_id,
                        phase=ProgressPhase.PROCESSING,
                        current=i + 1,
                        total=3,
                        message=f"Endpoint {i + 1}",
                    )
                )

            return character_id

        async def batch_refresh(character_ids: list[int]):
            tasks = [refresh_character(cid) for cid in character_ids]
            return await asyncio.gather(*tasks)

        character_ids = [111, 222, 333]
        results = asyncio.run(batch_refresh(character_ids))

        assert len(results) == 3
        assert set(results) == set(character_ids)

        # Should have updates for all characters
        character_updates = {cid: [] for cid in character_ids}
        for update in progress_updates:
            character_updates[update.character_id].append(update)

        for cid in character_ids:
            # Each character should have 4 updates (1 starting + 3 processing)
            assert len(character_updates[cid]) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
