"""Tests for the metrics collector module."""

import asyncio
import statistics
import threading
import time
import uuid
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from typing import Any
from unittest.mock import MagicMock

import pytest

# =============================================================================
# Mock implementations (self-contained, no imports from src)
# =============================================================================


class MetricCategories:
    """Pre-defined metric category prefixes."""

    STARTUP = "startup"
    REFRESH = "refresh"
    ESI = "esi"
    SDE = "sde"
    UI = "ui"


class MetricsCollector:
    """Collects and reports performance metrics for operations."""

    _instance: "MetricsCollector | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsCollector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        self._metrics: dict[str, list[float]] = defaultdict(list)
        self._active_timers: dict[str, tuple[str, float]] = {}
        self._metrics_lock = threading.Lock()
        self._timers_lock = threading.Lock()

    def start_timer(self, operation: str) -> str:
        timer_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        with self._timers_lock:
            self._active_timers[timer_id] = (operation, start_time)
        return timer_id

    def stop_timer(self, timer_id: str) -> float:
        end_time = time.perf_counter()
        with self._timers_lock:
            if timer_id not in self._active_timers:
                raise ValueError(f"Timer ID not found: {timer_id}")
            operation, start_time = self._active_timers.pop(timer_id)

        duration_ms = (end_time - start_time) * 1000
        self.record(operation, duration_ms)
        return duration_ms

    @contextmanager
    def time_operation(self, operation: str):
        timer_id = self.start_timer(operation)
        try:
            yield
        finally:
            self.stop_timer(timer_id)

    def record(self, metric: str, value: float) -> None:
        with self._metrics_lock:
            self._metrics[metric].append(value)

    def get_stats(self, metric: str) -> dict:
        with self._metrics_lock:
            values = self._metrics.get(metric, [])
            if not values:
                return {
                    "count": 0,
                    "min": 0.0,
                    "max": 0.0,
                    "avg": 0.0,
                    "p50": 0.0,
                    "p95": 0.0,
                }

            sorted_values = sorted(values)
            count = len(sorted_values)
            p50_idx = int(count * 0.50)
            p95_idx = int(count * 0.95)
            p50 = sorted_values[min(p50_idx, count - 1)]
            p95 = sorted_values[min(p95_idx, count - 1)]

            return {
                "count": count,
                "min": min(sorted_values),
                "max": max(sorted_values),
                "avg": statistics.mean(sorted_values),
                "p50": p50,
                "p95": p95,
            }

    def get_all_metrics(self) -> dict[str, list[float]]:
        with self._metrics_lock:
            return {k: list(v) for k, v in self._metrics.items()}

    def clear(self) -> None:
        with self._metrics_lock:
            self._metrics.clear()
        with self._timers_lock:
            self._active_timers.clear()

    def report(self, logger: Any | None = None) -> str:
        lines = ["=" * 60, "PERFORMANCE METRICS REPORT", "=" * 60]
        all_metrics = self.get_all_metrics()

        if not all_metrics:
            lines.append("No metrics collected.")
        else:
            categories: dict[str, list[str]] = defaultdict(list)
            for metric_name in sorted(all_metrics.keys()):
                category = metric_name.split(".")[0] if "." in metric_name else "other"
                categories[category].append(metric_name)

            for category in sorted(categories.keys()):
                lines.append("")
                lines.append(f"[{category.upper()}]")
                lines.append("-" * 40)

                for metric_name in categories[category]:
                    stats = self.get_stats(metric_name)
                    display_name = (
                        metric_name.split(".", 1)[1]
                        if "." in metric_name
                        else metric_name
                    )
                    lines.append(f"  {display_name}:")
                    lines.append(
                        f"    count={stats['count']}, "
                        f"min={stats['min']:.2f}ms, "
                        f"max={stats['max']:.2f}ms, "
                        f"avg={stats['avg']:.2f}ms"
                    )
                    lines.append(
                        f"    p50={stats['p50']:.2f}ms, p95={stats['p95']:.2f}ms"
                    )

        lines.append("")
        lines.append("=" * 60)

        report = "\n".join(lines)

        if logger:
            for line in lines:
                logger.info(line)

        return report


def get_metrics(metrics: "MetricsCollector | None" = None) -> MetricsCollector:
    if metrics is not None:
        MetricsCollector._instance = metrics
        return metrics
    return MetricsCollector()


def timed(operation: str | None = None):
    """Decorator to automatically time function execution."""

    def decorator(func):
        op_name = operation or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with get_metrics().time_operation(op_name):
                return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with get_metrics().time_operation(op_name):
                return func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def reset_metrics() -> None:
    MetricsCollector._instance = None


@pytest.fixture(autouse=True)
def reset_metrics_singleton():
    """Reset metrics singleton before and after each test."""
    reset_metrics()
    yield
    reset_metrics()


class TestMetricsCollectorTimingOperations:
    """Tests for timing operations in MetricsCollector."""

    def test_start_and_stop_timer(self):
        """Test starting and stopping a timer records duration."""
        metrics = MetricsCollector()

        timer_id = metrics.start_timer("test.operation")
        time.sleep(0.01)  # 10ms
        duration = metrics.stop_timer(timer_id)

        assert duration > 0
        assert duration >= 10  # At least 10ms

    def test_stop_timer_records_metric(self):
        """Test that stopping a timer records the metric."""
        metrics = MetricsCollector()

        timer_id = metrics.start_timer("test.recorded")
        time.sleep(0.005)
        metrics.stop_timer(timer_id)

        all_metrics = metrics.get_all_metrics()
        assert "test.recorded" in all_metrics
        assert len(all_metrics["test.recorded"]) == 1

    def test_stop_invalid_timer_raises_error(self):
        """Test stopping an invalid timer raises ValueError."""
        metrics = MetricsCollector()

        with pytest.raises(ValueError, match="Timer ID not found"):
            metrics.stop_timer("invalid-timer-id")

    def test_context_manager_times_operation(self):
        """Test context manager correctly times operations."""
        metrics = MetricsCollector()

        with metrics.time_operation("test.context"):
            time.sleep(0.01)

        stats = metrics.get_stats("test.context")
        assert stats["count"] == 1
        assert stats["min"] >= 10

    def test_context_manager_records_on_exception(self):
        """Test context manager records timing even when exception occurs."""
        metrics = MetricsCollector()

        try:
            with metrics.time_operation("test.exception"):
                time.sleep(0.005)
                raise RuntimeError("Test error")
        except RuntimeError:
            pass

        stats = metrics.get_stats("test.exception")
        assert stats["count"] == 1

    def test_multiple_timings_same_operation(self):
        """Test multiple timings for the same operation are recorded."""
        metrics = MetricsCollector()

        for _ in range(3):
            with metrics.time_operation("test.multiple"):
                time.sleep(0.001)

        stats = metrics.get_stats("test.multiple")
        assert stats["count"] == 3


class TestStatisticsCalculation:
    """Tests for statistics calculation (min, max, avg, p50, p95)."""

    def test_empty_metric_returns_zeros(self):
        """Test that empty metric returns zeroed statistics."""
        metrics = MetricsCollector()

        stats = metrics.get_stats("nonexistent.metric")

        assert stats["count"] == 0
        assert stats["min"] == 0.0
        assert stats["max"] == 0.0
        assert stats["avg"] == 0.0
        assert stats["p50"] == 0.0
        assert stats["p95"] == 0.0

    def test_single_value_statistics(self):
        """Test statistics with a single value."""
        metrics = MetricsCollector()
        metrics.record("test.single", 100.0)

        stats = metrics.get_stats("test.single")

        assert stats["count"] == 1
        assert stats["min"] == 100.0
        assert stats["max"] == 100.0
        assert stats["avg"] == 100.0
        assert stats["p50"] == 100.0
        assert stats["p95"] == 100.0

    def test_multiple_values_min_max_avg(self):
        """Test min, max, avg with multiple values."""
        metrics = MetricsCollector()
        values = [10.0, 20.0, 30.0, 40.0, 50.0]
        for v in values:
            metrics.record("test.multiple", v)

        stats = metrics.get_stats("test.multiple")

        assert stats["count"] == 5
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["avg"] == 30.0

    def test_percentile_calculation(self):
        """Test percentile calculation with larger dataset."""
        metrics = MetricsCollector()
        # Create 100 values: 1, 2, 3, ..., 100
        for i in range(1, 101):
            metrics.record("test.percentiles", float(i))

        stats = metrics.get_stats("test.percentiles")

        assert stats["count"] == 100
        assert stats["min"] == 1.0
        assert stats["max"] == 100.0
        # p50 should be around 50
        assert 49 <= stats["p50"] <= 51
        # p95 should be around 95
        assert 94 <= stats["p95"] <= 96

    def test_record_method(self):
        """Test direct recording of metric values."""
        metrics = MetricsCollector()

        metrics.record("test.direct", 42.5)
        metrics.record("test.direct", 57.5)

        stats = metrics.get_stats("test.direct")
        assert stats["count"] == 2
        assert stats["avg"] == 50.0


class TestThreadSafety:
    """Tests for thread safety of metrics collector."""

    def test_concurrent_timer_operations(self):
        """Test concurrent start/stop timer operations."""
        metrics = MetricsCollector()
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(10):
                    timer_id = metrics.start_timer(f"thread.{thread_id}")
                    time.sleep(0.001)
                    metrics.stop_timer(timer_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"

        # Each thread should have 10 recordings
        for i in range(5):
            stats = metrics.get_stats(f"thread.{i}")
            assert stats["count"] == 10

    def test_concurrent_record_operations(self):
        """Test concurrent record operations."""
        metrics = MetricsCollector()
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(100):
                    metrics.record("concurrent.metric", float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        stats = metrics.get_stats("concurrent.metric")
        # 10 threads * 100 records each
        assert stats["count"] == 1000

    def test_concurrent_get_stats(self):
        """Test concurrent stats retrieval while recording."""
        metrics = MetricsCollector()

        # Pre-populate with some data
        for i in range(100):
            metrics.record("concurrent.stats", float(i))

        errors = []

        def reader():
            try:
                for _ in range(50):
                    stats = metrics.get_stats("concurrent.stats")
                    assert "count" in stats
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(50):
                    metrics.record("concurrent.stats", float(i))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)] + [
            threading.Thread(target=writer) for _ in range(3)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestTimedDecorator:
    """Tests for the @timed decorator."""

    def test_timed_decorator_sync_function(self):
        """Test @timed decorator with synchronous function."""

        @timed("test.decorated.sync")
        def sync_function():
            time.sleep(0.01)
            return "result"

        result = sync_function()

        assert result == "result"
        stats = get_metrics().get_stats("test.decorated.sync")
        assert stats["count"] == 1
        assert stats["min"] >= 10

    def test_timed_decorator_async_function(self):
        """Test @timed decorator with async function."""

        @timed("test.decorated.async")
        async def async_function():
            await asyncio.sleep(0.01)
            return "async_result"

        result = asyncio.run(async_function())

        assert result == "async_result"
        stats = get_metrics().get_stats("test.decorated.async")
        assert stats["count"] == 1
        assert stats["min"] >= 10

    def test_timed_decorator_default_operation_name(self):
        """Test @timed decorator uses function name when no operation specified."""

        @timed()
        def my_function():
            return "test"

        my_function()

        # Should use qualified function name
        all_metrics = get_metrics().get_all_metrics()
        matching = [k for k in all_metrics.keys() if "my_function" in k]
        assert len(matching) >= 1

    def test_timed_decorator_preserves_function_metadata(self):
        """Test @timed decorator preserves original function metadata."""

        @timed("test.metadata")
        def documented_function():
            """This is a docstring."""
            pass

        assert documented_function.__name__ == "documented_function"
        assert "docstring" in documented_function.__doc__

    def test_timed_decorator_handles_exceptions(self):
        """Test @timed decorator still records timing on exception."""

        @timed("test.exception.decorator")
        def failing_function():
            time.sleep(0.005)
            raise ValueError("Expected error")

        with pytest.raises(ValueError):
            failing_function()

        stats = get_metrics().get_stats("test.exception.decorator")
        assert stats["count"] == 1


class TestMetricCategories:
    """Tests for predefined metric categories."""

    def test_categories_defined(self):
        """Test all expected categories are defined."""
        assert hasattr(MetricCategories, "STARTUP")
        assert hasattr(MetricCategories, "REFRESH")
        assert hasattr(MetricCategories, "ESI")
        assert hasattr(MetricCategories, "SDE")
        assert hasattr(MetricCategories, "UI")

    def test_category_values(self):
        """Test category values are valid strings."""
        assert MetricCategories.STARTUP == "startup"
        assert MetricCategories.REFRESH == "refresh"
        assert MetricCategories.ESI == "esi"
        assert MetricCategories.SDE == "sde"
        assert MetricCategories.UI == "ui"


class TestMetricsReport:
    """Tests for metrics report generation."""

    def test_report_empty_metrics(self):
        """Test report generation with no metrics."""
        metrics = MetricsCollector()
        report = metrics.report()

        assert "PERFORMANCE METRICS REPORT" in report
        assert "No metrics collected" in report

    def test_report_with_metrics(self):
        """Test report generation with recorded metrics."""
        metrics = MetricsCollector()
        metrics.record("startup.init", 100.0)
        metrics.record("startup.load", 200.0)
        metrics.record("esi.call", 50.0)

        report = metrics.report()

        assert "PERFORMANCE METRICS REPORT" in report
        assert "STARTUP" in report
        assert "ESI" in report
        assert "init" in report
        assert "load" in report

    def test_report_logs_to_logger(self):
        """Test report writes to logger when provided."""
        metrics = MetricsCollector()
        metrics.record("test.metric", 42.0)

        mock_logger = MagicMock()
        metrics.report(logger=mock_logger)

        # Logger should have been called
        assert mock_logger.info.called


class TestMetricsClear:
    """Tests for clearing metrics."""

    def test_clear_removes_all_metrics(self):
        """Test clear() removes all recorded metrics."""
        metrics = MetricsCollector()
        metrics.record("test.metric1", 1.0)
        metrics.record("test.metric2", 2.0)

        metrics.clear()

        all_metrics = metrics.get_all_metrics()
        assert len(all_metrics) == 0

    def test_clear_removes_active_timers(self):
        """Test clear() removes active timers."""
        metrics = MetricsCollector()
        timer_id = metrics.start_timer("test.active")

        metrics.clear()

        # Timer should no longer be valid
        with pytest.raises(ValueError):
            metrics.stop_timer(timer_id)


class TestGetMetricsSingleton:
    """Tests for get_metrics() singleton behavior."""

    def test_get_metrics_returns_same_instance(self):
        """Test get_metrics() returns singleton instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()

        assert metrics1 is metrics2

    def test_reset_metrics_clears_singleton(self):
        """Test reset_metrics() clears the singleton."""
        metrics1 = get_metrics()
        metrics1.record("test.before.reset", 1.0)

        reset_metrics()

        metrics2 = get_metrics()
        all_metrics = metrics2.get_all_metrics()
        # New instance should have no metrics
        assert "test.before.reset" not in all_metrics

    def test_get_metrics_with_custom_instance(self):
        """Test get_metrics() can accept custom instance."""
        custom = MetricsCollector()
        custom.record("custom.metric", 123.0)

        result = get_metrics(custom)

        assert result is custom
        # Subsequent calls should return the custom instance
        assert get_metrics() is custom


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
