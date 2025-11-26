"""Disk-based cache for ESI responses using diskcache."""

import hashlib
import json
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import diskcache

from utils import global_config

logger = logging.getLogger(__name__)


class ESICache:
    """Wrapper around diskcache with ESI-specific expiration handling."""

    def __init__(self, cache_dir: str | Path | None = None):
        """Initialize the cache.

        Args:
            cache_dir: Directory for cache storage (defaults to config.esi.cache_dir_path)
        """
        if cache_dir is None:
            cache_dir = global_config.esi.cache_dir_path
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = diskcache.Cache(str(self.cache_dir))

    def _make_key(
        self, method: str, url: str, params: dict | None = None, json_body: Any = None
    ) -> str:
        """Generate a cache key from request components.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            params: Query parameters
            json_body: JSON body for POST/PUT requests

        Returns:
            Cache key string
        """
        # Normalize params for consistent keys
        param_str = json.dumps(params or {}, sort_keys=True)
        # Include JSON body in cache key for POST/PUT requests
        body_str = (
            json.dumps(json_body, sort_keys=True) if json_body is not None else ""
        )
        key_input = f"{method}:{url}:{param_str}:{body_str}"
        return hashlib.sha256(key_input.encode()).hexdigest()

    def make_key(
        self, method: str, url: str, params: dict | None = None, json_body: Any = None
    ) -> str:
        """Public wrapper for generating a cache key.

        Prefer this over accessing the private `_make_key` from outside the
        cache implementation.
        """
        return self._make_key(method, url, params, json_body)

    def _get_expiration(self, headers: dict) -> datetime | None:
        """Extract expiration time from ESI headers as a datetime object (UTC)."""
        if expires := headers.get("expires"):
            try:
                dt = parsedate_to_datetime(expires)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt.astimezone(UTC)
            except (TypeError, ValueError) as e:
                logger.warning(f"Failed to parse Expires header '{expires}': {e}")
                return None
        return None

    def get(
        self, method: str, url: str, params: dict | None = None, json_body: Any = None
    ) -> tuple[Any, dict, str | None, datetime | None] | None:
        """Get cached response if valid.

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            json_body: JSON body for POST/PUT requests

        Returns:
            Tuple of (response_data, headers, etag, cached_at) or None if cache miss/expired
        """
        key = self._make_key(method, url, params, json_body)
        cached = self.cache.get(key)

        if cached is None:
            return None

        # We store and expect a 4-tuple: (data, headers_normalized, etag, cached_at)
        try:
            if len(cached) == 4:
                data, headers, etag, cached_at = cached
            else:
                self.cache.delete(key)
                return None
        except Exception:
            self.cache.delete(key)
            return None

        # Handle legacy string format for cached_at
        if cached_at and isinstance(cached_at, str):
            try:
                dt = datetime.fromisoformat(cached_at)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                cached_at = dt
            except Exception:
                pass

        logger.debug(f"Cache hit for key={key} etag={etag}")
        return data, headers, (etag if etag else None), cached_at

    def get_etag(
        self, method: str, url: str, params: dict | None = None, json_body: Any = None
    ) -> str | None:
        """Get ETag for a cached entry (even if expired).

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            json_body: JSON body for POST/PUT requests

        Returns:
            ETag string or None
        """
        key = self._make_key(method, url, params, json_body)
        cached = self.cache.get(key)

        if cached is None:
            return None

        # Expect 4-tuple format: (data, headers, etag, cached_at)
        try:
            if len(cached) == 4:
                _, headers, etag, _ = cached
            else:
                return None
        except Exception:
            return None

        # Prefer explicit etag value; fall back to header if present
        if etag:
            return etag
        if isinstance(headers, dict):
            return headers.get("etag")
        return None

    def set(
        self,
        method: str,
        url: str,
        data: Any,
        headers: dict,
        params: dict | None = None,
        json_body: Any = None,
    ) -> None:
        """Store response in cache with ETag support and expiry."""
        key = self._make_key(method, url, params, json_body)
        headers_normalized = {k.lower(): v for k, v in (headers or {}).items()}
        expires_at = self._get_expiration(headers_normalized)
        etag = headers_normalized.get("etag")
        cached_at = datetime.now(UTC)

        # Only store expires_at if you need it for later logic; otherwise, remove from tuple
        cache_value = (data, headers_normalized, etag, cached_at)
        expire_seconds = None
        if expires_at:
            expire_seconds = (expires_at - datetime.now(UTC)).total_seconds()

        logger.debug(f"Caching key={key} expire_in={expire_seconds}s etag={etag}")
        self.cache.set(
            key,
            cache_value,
            expire=expire_seconds,
        )

    def clear(self) -> None:
        """Clear all cached entries."""
        self.cache.clear()

    def close(self) -> None:
        """Close the cache."""
        self.cache.close()

    def time_to_expiry(
        self, method: str, url: str, params: dict | None = None, json_body: Any = None
    ) -> float | None:
        """Return seconds until the cached entry expires, or None if no expiry.

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            json_body: JSON body for POST/PUT requests

        Returns:
            Seconds until expiry (float) or None if not present
        """
        key = self._make_key(method, url, params, json_body)
        cached = self.cache.get(key)
        if not cached:
            return None

        # cached format: (data, headers, etag, cached_at)
        # Expiry is managed by diskcache, so we can't calculate exact time left unless we store it separately
        # For now, return None to indicate expiry is managed by diskcache
        return None
