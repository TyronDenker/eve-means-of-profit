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

    def _get_expiration(self, headers: dict) -> str | None:
        """Extract expiration time from ESI headers as ISO string.

        Respects standard expires header.

        Args:
            headers: Response headers

        Returns:
            Expiration time as ISO 8601 string or None if no expiration found
        """
        expires_time = None

        if expires := headers.get("expires"):
            try:
                dt = parsedate_to_datetime(expires)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                expires_time = dt.astimezone(UTC).isoformat()
            except (TypeError, ValueError):
                pass

        return expires_time

    def get(
        self, method: str, url: str, params: dict | None = None, json_body: Any = None
    ) -> tuple[Any, dict, str | None, str | None, str | None] | None:
        """Get cached response if valid.

        Args:
            method: HTTP method
            url: Request URL
            params: Query parameters
            json_body: JSON body for POST/PUT requests

        Returns:
            Tuple of (response_data, headers, expires_at_iso, etag, cached_at_iso) or None if cache miss/expired
            Note: expires_at_iso and cached_at_iso are ISO 8601 strings, not datetime objects
        """
        key = self._make_key(method, url, params, json_body)
        cached = self.cache.get(key)

        if cached is None:
            return None

        # We store and expect a 5-tuple: (data, headers_normalized, expires_at_iso, etag, cached_at_iso)
        try:
            if len(cached) == 5:
                data, headers, expires_at_iso, etag, cached_at_iso = cached
            else:
                # Unexpected format - delete and treat as miss
                self.cache.delete(key)
                return None
        except Exception:
            # If the cache contains an unexpected value, remove it and treat as miss
            self.cache.delete(key)
            return None

        # Check if cache entry is still valid by expiration
        if expires_at_iso:
            try:
                expires_at = datetime.fromisoformat(expires_at_iso)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
            except (ValueError, TypeError) as e:
                # Failed to parse expiration - treat as expired without ETag support
                logger.debug("Failed to parse expires_at '%s': %s", expires_at_iso, e)
                self.cache.delete(key)
                return None

            if datetime.now(UTC) > expires_at:
                # Keep expired entry if it has an ETag - we can use conditional requests
                if etag:
                    # Return conditional-ready tuple (data, headers, expires_at_iso, etag, cached_at_iso)
                    return data, headers, expires_at_iso, etag, cached_at_iso
                # No etag - delete expired entry
                self.cache.delete(key)
                return None

        return data, headers, expires_at_iso, (etag if etag else None), cached_at_iso

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

        # Expect 5-tuple format: (data, headers, expires_at_iso, etag, cached_at_iso)
        try:
            if len(cached) == 5:
                _, headers, _, etag, _ = cached
            else:
                return None
        except Exception:
            # Unexpected format
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
        """Store response in cache with ETag support.

        Args:
            method: HTTP method
            url: Request URL
            data: Response data to cache
            headers: Response headers
            params: Query parameters
            json_body: JSON body for POST/PUT requests
        """
        key = self._make_key(method, url, params, json_body)

        # Normalize header names to lowercase for consistent lookup later
        headers_normalized = {k.lower(): v for k, v in (headers or {}).items()}

        expires_at = self._get_expiration(headers_normalized)
        etag = headers_normalized.get("etag")
        cached_at = datetime.now(UTC).isoformat()

        # Store data, normalized headers, expiration time, etag, and cached_at timestamp
        self.cache.set(key, (data, headers_normalized, expires_at, etag, cached_at))

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

        # cached format: (data, headers, expires_at_iso, etag, cached_at_iso) or old (data, headers, expires_at_iso, etag)
        if len(cached) in (4, 5):
            expires_at_iso = cached[2]
            if expires_at_iso:
                try:
                    expires_at = datetime.fromisoformat(expires_at_iso)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=UTC)
                    return (expires_at - datetime.now(UTC)).total_seconds()
                except (ValueError, TypeError):
                    return None

        return None
