"""Tests for ESI cache backend."""

import time

import pytest

from data.clients.esi.cache import CacheBackend


class TestCacheBackend:
    """Test CacheBackend functionality."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a temporary cache backend."""
        return CacheBackend(cache_dir=tmp_path / "test_cache")

    def test_init(self, tmp_path):
        """Test cache initialization."""
        cache = CacheBackend(cache_dir=tmp_path / "test_cache")
        assert cache.cache_dir.exists()

    def test_cache_key_generation(self, cache):
        """Test cache key generation."""
        key1 = cache._make_key("GET", "/markets/prices")
        key2 = cache._make_key("GET", "/markets/prices")
        key3 = cache._make_key("GET", "/markets/orders")

        # Same request should generate same key
        assert key1 == key2
        # Different request should generate different key
        assert key1 != key3

    def test_cache_key_with_params(self, cache):
        """Test cache key with parameters."""
        key1 = cache._make_key("GET", "/markets/prices", {"region_id": 10000002})
        key2 = cache._make_key("GET", "/markets/prices", {"region_id": 10000002})
        key3 = cache._make_key("GET", "/markets/prices", {"region_id": 10000001})

        assert key1 == key2
        assert key1 != key3

    def test_set_and_get(self, cache):
        """Test storing and retrieving from cache."""
        data = {"test": "data"}
        headers = {
            "etag": "abc123",
            "expires": "Mon, 01 Jan 2099 00:00:00 GMT",
        }

        cache.set("GET", "/test", data, headers)
        cached = cache.get("GET", "/test")

        assert cached is not None
        assert cached["data"] == data
        assert cached["etag"] == "abc123"

    def test_cache_expiry(self, cache):
        """Test cache expiry."""
        data = {"test": "data"}
        headers = {
            "cache-control": "max-age=1",  # 1 second
        }

        cache.set("GET", "/test", data, headers)

        # Should be cached
        cached = cache.get("GET", "/test")
        assert cached is not None

        # Wait for expiry
        time.sleep(1.1)

        # Should be expired
        cached = cache.get("GET", "/test")
        assert cached is None

    def test_get_etag(self, cache):
        """Test retrieving ETag."""
        headers = {
            "etag": "test-etag",
            "expires": "Mon, 01 Jan 2099 00:00:00 GMT",
        }

        cache.set("GET", "/test", {"data": "value"}, headers)
        etag = cache.get_etag("GET", "/test")

        assert etag == "test-etag"

    def test_clear(self, cache):
        """Test clearing cache."""
        cache.set(
            "GET", "/test1", {"data": 1}, {"expires": "Mon, 01 Jan 2099 00:00:00 GMT"}
        )
        cache.set(
            "GET", "/test2", {"data": 2}, {"expires": "Mon, 01 Jan 2099 00:00:00 GMT"}
        )

        cache.clear()

        assert cache.get("GET", "/test1") is None
        assert cache.get("GET", "/test2") is None
