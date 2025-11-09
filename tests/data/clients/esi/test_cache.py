"""Tests for ESI cache backend."""

import time

import pytest

from data.clients.esi.cache import CacheBackend


class TestCacheBackend:
    """Test CacheBackend functionality."""

    @pytest.fixture
    def cache(self, tmp_path):
        """Create a temporary cache backend."""
        cache_dir = tmp_path / "test_cache"
        return CacheBackend(cache_dir=cache_dir)

    def test_init(self, tmp_path):
        """Test cache initialization."""
        cache_dir = tmp_path / "test_cache"
        cache = CacheBackend(cache_dir=cache_dir)
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

    def test_expiry_with_invalid_expires_header(self, cache):
        """
        GIVEN cache backend with invalid expires header
        WHEN storing data with malformed expires value
        THEN fallback to 5-minute default TTL
        """
        # Given: Data with invalid expires header
        data = {"test": "data"}
        headers = {
            "etag": "test-etag",
            "expires": "invalid-date-format",  # This will fail to parse
        }

        # When: Storing data with invalid expires header
        cache.set("GET", "/test", data, headers)
        cached = cache.get("GET", "/test")

        # Then: Data should be cached with default TTL (5 minutes)
        assert cached is not None
        assert cached["data"] == data
        # Verify it uses default expiry (~5 minutes = 300 seconds)
        assert cached["expires_at"] > time.time() + 290
        assert cached["expires_at"] < time.time() + 310

    def test_expiry_with_none_expires_header(self, cache):
        """
        GIVEN cache backend with None expires header
        WHEN storing data with None as expires value (TypeError case)
        THEN fallback to 5-minute default TTL
        """
        # Given: Data with None expires header (triggers TypeError)
        data = {"test": "data"}
        headers = {
            "etag": "test-etag",
            "expires": None,  # This will trigger TypeError in parsedate_to_datetime
        }

        # When: Storing data with None expires header
        cache.set("GET", "/test", data, headers)
        cached = cache.get("GET", "/test")

        # Then: Data should be cached with default TTL (5 minutes)
        assert cached is not None
        assert cached["data"] == data
        # Verify it uses default expiry (~5 minutes = 300 seconds)
        assert cached["expires_at"] > time.time() + 290
        assert cached["expires_at"] < time.time() + 310

    def test_expiry_with_invalid_cache_control_max_age(self, cache):
        """
        GIVEN cache backend with invalid cache-control max-age
        WHEN storing data with non-numeric max-age value
        THEN fallback to 5-minute default TTL
        """
        # Given: Data with invalid max-age in cache-control
        data = {"test": "data"}
        headers = {
            "etag": "test-etag",
            "cache-control": "max-age=invalid",  # This will fail to parse
        }

        # When: Storing data with invalid cache-control
        cache.set("GET", "/test", data, headers)
        cached = cache.get("GET", "/test")

        # Then: Data should be cached with default TTL (5 minutes)
        assert cached is not None
        assert cached["data"] == data
        # Verify it uses default expiry (~5 minutes = 300 seconds)
        assert cached["expires_at"] > time.time() + 290
        assert cached["expires_at"] < time.time() + 310

    def test_expiry_with_malformed_cache_control_directive(self, cache):
        """
        GIVEN cache backend with malformed cache-control directive
        WHEN storing data with cache-control directive without '=' separator
        THEN fallback to 5-minute default TTL
        """
        # Given: Data with malformed cache-control directive
        data = {"test": "data"}
        headers = {
            "etag": "test-etag",
            "cache-control": "max-age",  # Missing '=' and value
        }

        # When: Storing data with malformed cache-control
        cache.set("GET", "/test", data, headers)
        cached = cache.get("GET", "/test")

        # Then: Data should be cached with default TTL (5 minutes)
        assert cached is not None
        assert cached["data"] == data
        # Verify it uses default expiry (~5 minutes = 300 seconds)
        assert cached["expires_at"] > time.time() + 290
        assert cached["expires_at"] < time.time() + 310

    def test_expiry_with_no_cache_headers(self, cache):
        """
        GIVEN cache backend with no cache-related headers
        WHEN storing data without expires or cache-control headers
        THEN fallback to 5-minute default TTL
        """
        # Given: Data with no cache headers
        data = {"test": "data"}
        headers = {"etag": "test-etag"}  # No expires or cache-control

        # When: Storing data without cache headers
        cache.set("GET", "/test", data, headers)
        cached = cache.get("GET", "/test")

        # Then: Data should be cached with default TTL (5 minutes)
        assert cached is not None
        assert cached["data"] == data
        # Verify it uses default expiry (~5 minutes = 300 seconds)
        assert cached["expires_at"] > time.time() + 290
        assert cached["expires_at"] < time.time() + 310

    def test_invalidate_matching_pattern(self, cache):
        """
        GIVEN cache backend with multiple cached entries
        WHEN invalidating entries matching a pattern
        THEN only matching entries are removed
        """
        # Given: Multiple cached entries
        headers = {"expires": "Mon, 01 Jan 2099 00:00:00 GMT"}

        cache.set("GET", "/markets/prices", {"data": 1}, headers)
        cache.set("GET", "/markets/orders", {"data": 2}, headers)
        cache.set("GET", "/universe/systems", {"data": 3}, headers)

        # When: Invalidating entries matching '/markets/'
        cache.invalidate("/markets/")

        # Then: Only /markets/ entries are removed
        assert cache.get("GET", "/markets/prices") is None
        assert cache.get("GET", "/markets/orders") is None
        assert cache.get("GET", "/universe/systems") is not None

    def test_invalidate_no_matches(self, cache):
        """
        GIVEN cache backend with cached entries
        WHEN invalidating with pattern that matches nothing
        THEN no entries are removed
        """
        # Given: Cached entries
        headers = {"expires": "Mon, 01 Jan 2099 00:00:00 GMT"}

        cache.set("GET", "/markets/prices", {"data": 1}, headers)
        cache.set("GET", "/universe/systems", {"data": 2}, headers)

        # When: Invalidating with non-matching pattern
        cache.invalidate("/does-not-exist/")

        # Then: All entries remain
        assert cache.get("GET", "/markets/prices") is not None
        assert cache.get("GET", "/universe/systems") is not None

    def test_get_etag_for_missing_entry(self, cache):
        """
        GIVEN cache backend without cached entry
        WHEN getting ETag for non-existent entry
        THEN return None
        """
        # Given: No cached entry for this path
        # When: Getting ETag for non-existent entry
        etag = cache.get_etag("GET", "/nonexistent")

        # Then: Should return None
        assert etag is None

    def test_cache_with_character_id(self, cache):
        """
        GIVEN cache backend for authenticated requests
        WHEN caching data with different character IDs
        THEN entries are stored separately per character
        """
        # Given: Data for different characters
        headers = {"expires": "Mon, 01 Jan 2099 00:00:00 GMT"}

        # When: Caching same path for different characters
        cache.set(
            "GET",
            "/characters/123/assets",
            {"assets": "char123"},
            headers,
            character_id=123,
        )
        cache.set(
            "GET",
            "/characters/456/assets",
            {"assets": "char456"},
            headers,
            character_id=456,
        )

        # Then: Each character has separate cache entry
        cached_123 = cache.get("GET", "/characters/123/assets", character_id=123)
        cached_456 = cache.get("GET", "/characters/456/assets", character_id=456)

        assert cached_123 is not None
        assert cached_456 is not None
        assert cached_123["data"]["assets"] == "char123"
        assert cached_456["data"]["assets"] == "char456"
