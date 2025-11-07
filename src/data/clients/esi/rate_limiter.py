"""
ESI Rate Limiter.

Tracks X-ESI-Error-Limit headers and throttles requests to comply with ESI limits.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


class RateLimiter:
    """
    Tracks and enforces ESI error rate limits.

    ESI uses an error bucket system where errors increment a counter.
    Headers indicate remaining errors and reset time.
    """

    def __init__(self, threshold: int = 10):
        """
        Initialize rate limiter.

        Args:
            threshold: Start throttling when errors remaining falls below this value
        """
        self.threshold = threshold
        self.errors_remaining = 100  # Default ESI limit
        self.reset_time = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """
        Wait if rate limit is being approached or exceeded.

        This method should be called before making a request.
        """
        async with self._lock:
            # If we're at or below threshold, wait for reset
            if self.errors_remaining <= self.threshold:
                wait_time = max(0, self.reset_time - time.time())
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                    # Reset counter after waiting
                    self.errors_remaining = 100

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """
        Update rate limit state from response headers.

        Args:
            headers: HTTP response headers containing X-ESI-Error-Limit-* values
        """
        # Update errors remaining
        if "x-esi-error-limit-remain" in headers:
            self.errors_remaining = int(headers["x-esi-error-limit-remain"])

        # Update reset time (seconds from now)
        if "x-esi-error-limit-reset" in headers:
            reset_seconds = int(headers["x-esi-error-limit-reset"])
            self.reset_time = time.time() + reset_seconds

    def get_metrics(self) -> dict[str, int | float]:
        """
        Get current rate limit metrics.

        Returns:
            Dictionary with errors_remaining, errors_limit, reset_time, and throttling status
        """
        return {
            "errors_remaining": self.errors_remaining,
            "errors_limit": 100,  # ESI standard limit
            "reset_time": max(0, self.reset_time - time.time()),
            "throttling": self.errors_remaining <= self.threshold,
        }
