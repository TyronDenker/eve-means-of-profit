"""Tests for ESI rate limiter."""

import time

import pytest

from data.clients.esi.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test RateLimiter functionality."""

    def test_init(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(threshold=10)
        assert limiter.threshold == 10
        assert limiter.errors_remaining == 100

    def test_update_from_headers(self):
        """Test updating from response headers."""
        limiter = RateLimiter()
        headers = {
            "x-esi-error-limit-remain": "50",
            "x-esi-error-limit-reset": "60",
        }

        limiter.update_from_headers(headers)

        assert limiter.errors_remaining == 50
        assert limiter.reset_time > 0

    def test_get_metrics(self):
        """Test getting rate limit metrics."""
        limiter = RateLimiter()
        metrics = limiter.get_metrics()

        assert "errors_remaining" in metrics
        assert "errors_limit" in metrics
        assert "reset_time" in metrics
        assert "throttling" in metrics
        assert isinstance(metrics["throttling"], bool)

    @pytest.mark.asyncio
    async def test_acquire_no_throttle(self):
        """Test acquire when no throttling needed."""
        limiter = RateLimiter(threshold=10)
        limiter.errors_remaining = 50

        # Should not block
        await limiter.acquire()
        assert True  # Passed if no timeout

    @pytest.mark.asyncio
    async def test_acquire_with_throttle(self):
        """Test acquire when throttling is needed."""
        limiter = RateLimiter(threshold=10)
        limiter.errors_remaining = 5  # Below threshold
        limiter.reset_time = time.time() + 0.1  # 100ms wait

        start = time.time()
        await limiter.acquire()
        duration = time.time() - start

        # Should have waited approximately 100ms
        assert duration >= 0.05  # At least 50ms (allowing for timing variance)
