"""
ESI Cache Backend.

Implements HTTP caching with ETag and Expires header support using diskcache.
"""

from __future__ import annotations

import hashlib
import logging
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from diskcache import Cache

if TYPE_CHECKING:
    from collections.abc import Mapping

logger = logging.getLogger(__name__)


class CacheBackend:
    """
    Persistent HTTP cache for ESI responses.

    Supports ETag-based caching and respects Expires headers.
    """

    def __init__(self, cache_dir: str | Path | None = None):
        """
        Initialize cache backend.

        Args:
            cache_dir: Directory to store cache (default: data/esi/cache)
        """
        if cache_dir is None:
            cache_dir = Path("data/esi/cache")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache = Cache(str(self.cache_dir))

    def _make_key(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        character_id: int | None = None,
    ) -> str:
        """
        Generate cache key from request parameters.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            params: Query parameters
            character_id: Character ID for authenticated requests

        Returns:
            Cache key string
        """
        # Create deterministic key from request components
        key_parts = [method, path]

        if character_id:
            key_parts.append(f"char_{character_id}")

        if params:
            # Sort params for consistent key generation
            sorted_params = sorted(params.items())
            params_str = str(sorted_params)
            params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
            key_parts.append(f"params_{params_hash}")

        return ":".join(key_parts)

    def get(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        character_id: int | None = None,
    ) -> dict[str, Any] | None:
        """
        Get cached response.

        Args:
            method: HTTP method
            path: Request path
            params: Query parameters
            character_id: Character ID for authenticated requests

        Returns:
            Cached response data or None if not found/expired
        """
        key = self._make_key(method, path, params, character_id)
        cached = self._cache.get(key)

        if cached is None:
            logger.debug(f"CACHE MISS: {method} {path}")
            return None

        # Check if expired
        expires_at = cached.get("expires_at", 0)
        if expires_at < time.time():
            time_until_refresh = 0
            logger.debug(f"CACHE EXPIRED: {method} {path}")
            self._cache.delete(key)
            return None

        # Cache hit - log details
        time_until_refresh = int(expires_at - time.time())
        cached_at = cached.get("cached_at", 0)
        age_seconds = int(time.time() - cached_at)

        logger.info(
            f"CACHE HIT: {method} {path} | "
            f"Age: {age_seconds}s | "
            f"Expires in: {time_until_refresh}s | "
            f"ETag: {cached.get('etag', 'N/A')}"
        )

        return cached

    def set(
        self,
        method: str,
        path: str,
        data: Any,
        headers: Mapping[str, str],
        params: dict[str, Any] | None = None,
        character_id: int | None = None,
    ) -> None:
        """
        Store response in cache.

        Args:
            method: HTTP method
            path: Request path
            data: Response data
            headers: Response headers
            params: Query parameters
            character_id: Character ID for authenticated requests
        """
        key = self._make_key(method, path, params, character_id)

        # Calculate expiry time from headers
        expires_at = self._calculate_expiry(headers)
        ttl_seconds = int(max(0, expires_at - time.time()))

        cached_data = {
            "data": data,
            "etag": headers.get("etag"),
            "expires_at": expires_at,
            "cached_at": time.time(),
            "headers": dict(headers),
        }

        # Set TTL based on expires_at
        ttl = max(0, expires_at - time.time())
        self._cache.set(key, cached_data, expire=ttl)

        logger.info(
            f"CACHED: {method} {path} | "
            f"TTL: {ttl_seconds}s | "
            f"ETag: {headers.get('etag', 'N/A')}"
        )

    def _calculate_expiry(self, headers: Mapping[str, str]) -> float:
        """
        Calculate expiry timestamp from response headers.

        Args:
            headers: Response headers

        Returns:
            Unix timestamp when cache should expire
        """
        # Check Expires header
        if "expires" in headers:
            try:
                expires_dt = parsedate_to_datetime(headers["expires"])
                return expires_dt.timestamp()
            except (ValueError, TypeError):
                pass

        # Check Cache-Control max-age
        if "cache-control" in headers:
            cache_control = headers["cache-control"]
            for directive in cache_control.split(","):
                directive = directive.strip()
                if directive.startswith("max-age="):
                    try:
                        max_age = int(directive.split("=")[1])
                        return time.time() + max_age
                    except (ValueError, IndexError):
                        pass

        # Default: 5 minutes
        return time.time() + 300

    def get_etag(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        character_id: int | None = None,
    ) -> str | None:
        """
        Get ETag for cached response.

        Args:
            method: HTTP method
            path: Request path
            params: Query parameters
            character_id: Character ID for authenticated requests

        Returns:
            ETag value or None
        """
        cached = self.get(method, path, params, character_id)
        return cached.get("etag") if cached else None

    def clear(self) -> None:
        """Clear entire cache."""
        self._cache.clear()

    def invalidate(self, pattern: str) -> None:
        """
        Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match against cache keys
        """
        # Get all keys and delete matching ones
        for key in list(self._cache.iterkeys()):
            if pattern in key:
                self._cache.delete(key)
