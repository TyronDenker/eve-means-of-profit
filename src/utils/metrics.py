"""Metrics collection and performance instrumentation for EVE Means of Profit.

This module provides a thread-safe metrics collector for timing and performance
data collection across startup, refresh, ESI calls, and UI operations.
"""

import asyncio
import logging
import statistics
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from functools import wraps
from typing import TypeVar

# Type variable for generic decorator support
F = TypeVar("F", bound=Callable)


# Pre-defined metric categories
class MetricCategories:
    """Pre-defined metric category prefixes."""

    STARTUP = "startup"  # startup.* - startup timing metrics
    REFRESH = "refresh"  # refresh.* - character refresh metrics
    ESI = "esi"  # esi.* - ESI API call metrics
    SDE = "sde"  # sde.* - SDE loading metrics
    UI = "ui"  # ui.* - UI rendering metrics


class MetricsCollector:
    """Collects and reports performance metrics for operations.

    This is a thread-safe singleton that collects timing and performance data
    for various operations throughout the application.

    Usage:
        # Get the singleton instance
        metrics = get_metrics()

        # Time an operation using context manager
        with metrics.time_operation("startup.load_sde"):
            load_sde_data()

        # Manual timer control
        timer_id = metrics.start_timer("esi.get_character")
        # ... do work ...
        duration = metrics.stop_timer(timer_id)

        # Record arbitrary metrics
        metrics.record("refresh.characters_loaded", 5)

        # Get statistics
        stats = metrics.get_stats("startup.load_sde")
        print(f"Average: {stats['avg']}ms")

        # Generate report
        report = metrics.report()
        print(report)
    """

    _instance: "MetricsCollector | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsCollector":
        """Create or return the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize instance variables."""
        self._metrics: dict[str, list[float]] = defaultdict(list)
        self._active_timers: dict[str, tuple[str, float]] = {}
        self._metrics_lock = threading.Lock()
        self._timers_lock = threading.Lock()

    def start_timer(self, operation: str) -> str:
        """Start timing an operation.

        Args:
            operation: Name of the operation being timed (e.g., "startup.load_sde")

        Returns:
            Timer ID that should be passed to stop_timer()
        """
        timer_id = str(uuid.uuid4())
        start_time = time.perf_counter()
        with self._timers_lock:
            self._active_timers[timer_id] = (operation, start_time)
        return timer_id

    def stop_timer(self, timer_id: str) -> float:
        """Stop a timer and record the elapsed time.

        Args:
            timer_id: The timer ID returned from start_timer()

        Returns:
            Duration in milliseconds

        Raises:
            ValueError: If timer_id is not found
        """
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
        """Context manager for timing operations.

        Args:
            operation: Name of the operation being timed

        Yields:
            None

        Example:
            with metrics.time_operation("startup.init_ui"):
                initialize_ui()
        """
        timer_id = self.start_timer(operation)
        try:
            yield
        finally:
            self.stop_timer(timer_id)

    def record(self, metric: str, value: float) -> None:
        """Record a metric value.

        Args:
            metric: Name of the metric
            value: Value to record
        """
        with self._metrics_lock:
            self._metrics[metric].append(value)

    def get_stats(self, metric: str) -> dict:
        """Get statistics for a metric.

        Args:
            metric: Name of the metric

        Returns:
            Dictionary with count, min, max, avg, p50 (median), and p95 percentile
        """
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

            # Calculate percentiles
            p50_idx = int(count * 0.50)
            p95_idx = int(count * 0.95)

            # Handle edge cases for small datasets
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
        """Get all collected metrics.

        Returns:
            Dictionary mapping metric names to lists of recorded values
        """
        with self._metrics_lock:
            # Return a copy to prevent external modification
            return {k: list(v) for k, v in self._metrics.items()}

    def clear(self) -> None:
        """Clear all collected metrics and active timers."""
        with self._metrics_lock:
            self._metrics.clear()
        with self._timers_lock:
            self._active_timers.clear()

    def report(self, logger: logging.Logger | None = None) -> str:
        """Generate a human-readable report of metrics.

        Args:
            logger: Optional logger to write the report to

        Returns:
            Human-readable string report of all metrics
        """
        lines = ["=" * 60, "PERFORMANCE METRICS REPORT", "=" * 60]

        all_metrics = self.get_all_metrics()

        if not all_metrics:
            lines.append("No metrics collected.")
        else:
            # Group metrics by category
            categories: dict[str, list[str]] = defaultdict(list)
            for metric_name in sorted(all_metrics.keys()):
                category = metric_name.split(".")[0] if "." in metric_name else "other"
                categories[category].append(metric_name)

            # Report by category
            for category in sorted(categories.keys()):
                lines.append("")
                lines.append(f"[{category.upper()}]")
                lines.append("-" * 40)

                for metric_name in categories[category]:
                    stats = self.get_stats(metric_name)
                    # Format the metric name without category prefix for cleaner output
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
    """Get the singleton MetricsCollector instance.

    Args:
        metrics: Optional MetricsCollector to use instead of singleton.
                 If provided on first call, sets the singleton.
                 Useful for dependency injection.

    Returns:
        The global MetricsCollector instance
    """
    if metrics is not None:
        MetricsCollector._instance = metrics
        return metrics
    return MetricsCollector()


def timed(operation: str | None = None) -> Callable[[F], F]:
    """Decorator to automatically time function execution.

    Can be used with both sync and async functions.

    Args:
        operation: Optional operation name. If not provided, uses the
                   function's qualified name.

    Returns:
        Decorated function that records execution time

    Example:
        @timed("startup.load_config")
        def load_config():
            ...

        @timed()  # Will use function name as operation
        async def fetch_data():
            ...
    """

    def decorator(func: F) -> F:
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
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


def reset_metrics() -> None:
    """Reset the metrics collector singleton.

    This is primarily useful for testing to ensure a clean state.
    """
    MetricsCollector._instance = None
