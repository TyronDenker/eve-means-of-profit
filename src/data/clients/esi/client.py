"""
ESI API Client.

Main client that orchestrates authentication, rate limiting, and caching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from .auth import TokenProvider
from .cache import CacheBackend
from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ESIClient:
    """
    Main ESI API client.

    Handles authenticated and public requests with automatic caching,
    rate limiting, and token refresh.
    """

    def __init__(
        self,
        client_id: str,
        token_file: str | Path,
        cache_dir: str | Path,
        base_url: str,
        user_agent: str,
        rate_limit_threshold: int = 10,
    ):
        """
        Initialize ESI client.

        Args:
            client_id: ESI application client ID
            token_file: Path to token storage file
            cache_dir: Directory for cache storage
            user_agent: User agent string for HTTP requests
            rate_limit_threshold: Start throttling when errors fall below this value
        """
        self.client_id = client_id
        self.user_agent = user_agent
        self.base_url = base_url

        # Initialize components with provided config values
        self.token_provider = TokenProvider(
            client_id=self.client_id, token_file=token_file
        )
        self.cache = CacheBackend(cache_dir=cache_dir)
        self.rate_limiter = RateLimiter(threshold=rate_limit_threshold)

        # HTTP client
        self._http_client: httpx.AsyncClient | None = None
        self._active_character_id: int | None = None

    async def __aenter__(self) -> ESIClient:
        """Async context provider entry."""
        self._http_client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context provider exit."""
        if self._http_client:
            await self._http_client.aclose()

    def set_active_character(self, character_id: int) -> None:
        """
        Set active character for authenticated requests.

        Args:
            character_id: Character ID to use for requests
        """
        self._active_character_id = character_id

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
        use_cache: bool = True,
    ) -> Any:
        """
        Make GET request to ESI.

        Args:
            path: API path (e.g., '/markets/prices')
            params: Query parameters
            authenticated: Whether request requires authentication
            use_cache: Whether to use cache

        Returns:
            Response data

        Raises:
            ValueError: If authentication required but no character set
        """
        # Check cache first
        character_id = self._active_character_id if authenticated else None

        if use_cache:
            cached = self.cache.get("GET", path, params, character_id)
            if cached:
                return cached["data"]

        # Wait for rate limit
        await self.rate_limiter.acquire()

        # Build request
        url = f"{self.base_url}{path}"
        headers = {}

        # Add ETag header if available
        if use_cache:
            etag = self.cache.get_etag("GET", path, params, character_id)
            if etag:
                headers["If-None-Match"] = etag

        # Add authentication if needed
        if authenticated:
            if not self.token_provider or self._active_character_id is None:
                msg = "Authentication required but no character set"
                raise ValueError(msg)

            token = await self.token_provider.get_token(self._active_character_id)
            headers["Authorization"] = f"Bearer {token}"

        # Make request
        if not self._http_client:
            msg = "Client not initialized. Use 'async with' context provider."
            raise RuntimeError(msg)

        response = await self._http_client.get(url, params=params, headers=headers)

        # Update rate limiter
        self.rate_limiter.update_from_headers(response.headers)

        # Log rate limit and cache status
        self._log_response_details(response, path, "GET")

        # Handle 304 Not Modified
        if response.status_code == 304:
            logger.info(f"304 Not Modified: {path} - Serving from cache (ETag match)")
            cached = self.cache.get("GET", path, params, character_id)
            if cached:
                return cached["data"]

        # Raise for errors
        response.raise_for_status()

        # Parse response
        data = response.json()

        # Cache response
        if use_cache and response.status_code == 200:
            self.cache.set("GET", path, data, response.headers, params, character_id)

        return data

    async def post(
        self,
        path: str,
        data: dict[str, Any],
        params: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> Any:
        """
        Make POST request to ESI.

        Args:
            path: API path
            data: Request body
            params: Query parameters
            authenticated: Whether request requires authentication

        Returns:
            Response data
        """
        # Wait for rate limit
        await self.rate_limiter.acquire()

        # Build request
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}

        # Add authentication
        if authenticated:
            if not self.token_provider or self._active_character_id is None:
                msg = "Authentication required but no character set"
                raise ValueError(msg)

            token = await self.token_provider.get_token(self._active_character_id)
            headers["Authorization"] = f"Bearer {token}"

        # Make request
        if not self._http_client:
            msg = "Client not initialized. Use 'async with' context provider."
            raise RuntimeError(msg)

        response = await self._http_client.post(
            url, json=data, params=params, headers=headers
        )

        # Update rate limiter
        self.rate_limiter.update_from_headers(response.headers)

        # Raise for errors
        response.raise_for_status()

        # Parse response if not 204
        if response.status_code == 204:
            return None
        return response.json()

    async def get_public_market_prices(self) -> list[dict[str, Any]]:
        """
        Get market prices (example convenience method).

        Returns:
            List of market price data
        """
        return await self.get("/markets/prices/")

    async def get_character_info(self, character_id: int) -> dict[str, Any]:
        """
        Get public character information.

        Args:
            character_id: Character ID

        Returns:
            Character information
        """
        return await self.get(f"/characters/{character_id}/")

    def get_rate_limit_metrics(self) -> dict[str, int | float]:
        """
        Get current rate limit metrics.

        Returns:
            Rate limit metrics dictionary
        """
        return self.rate_limiter.get_metrics()

    def _log_response_details(
        self, response: httpx.Response, path: str, method: str
    ) -> None:
        """
        Log rate limit and cache information from response headers.

        Args:
            response: HTTP response
            path: Request path
            method: HTTP method
        """
        headers = response.headers

        # Extract rate limit info
        rate_group = headers.get("x-ratelimit-group", "N/A")
        rate_limit = headers.get("x-ratelimit-limit", "N/A")
        rate_remaining = headers.get("x-ratelimit-remaining", "N/A")
        rate_used = headers.get("x-ratelimit-used", "N/A")

        # Extract cache info
        expires = headers.get("expires", "N/A")
        etag = headers.get("etag", "N/A")

        # Log comprehensive info
        logger.info(
            f"RESPONSE: {method} {path} [{response.status_code}] | "
            f"Group: {rate_group} | "
            f"Tokens: {rate_remaining}/{rate_limit.split('/')[0] if '/' in rate_limit else rate_limit} "
            f"(used: {rate_used}) | "
            f"Expires: {expires} | "
            f"ETag: {etag[:12] if etag != 'N/A' and len(etag) > 12 else etag}..."
        )

    async def get_paginated(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
        limit: int = 100,
        before: str | None = None,
        after: str | None = None,
    ) -> dict[str, Any]:
        """
        Make GET request with cursor-based pagination support.

        Args:
            path: API path
            params: Query parameters (limit/before/after will be added automatically)
            authenticated: Whether request requires authentication
            limit: Maximum records per request (default 100)
            before: Cursor token to get records before this position
            after: Cursor token to get records after this position

        Returns:
            Dictionary with 'records' and 'cursor' keys

        Example:
            response = await client.get_paginated(
                "/characters/123/assets/",
                authenticated=True,
                limit=100
            )
            records = response.get('records', [])
            cursor = response.get('cursor', {})
            next_after = cursor.get('after')
        """
        # Build pagination parameters
        pagination_params = {"limit": limit}
        if before:
            pagination_params["before"] = before
        if after:
            pagination_params["after"] = after

        # Merge with existing params
        all_params = {**(params or {}), **pagination_params}

        # Make request (returns full response including cursor)
        # Note: For paginated endpoints, we need the raw response structure
        return await self.get(path, params=all_params, authenticated=authenticated)

    async def collect_all_pages(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Collect all historical records using cursor pagination.

        This implements the "Initial Data Collection" pattern from ESI docs.
        Starts from the most recent and walks backward to get all data.

        Args:
            path: API path
            params: Query parameters
            authenticated: Whether request requires authentication
            limit: Records per request

        Returns:
            Tuple of (all_records, last_after_token) for monitoring updates

        Example:
            all_records, after_token = await client.collect_all_pages(
                "/characters/123/assets/",
                authenticated=True
            )
            # Later, check for new data:
            new_records = await client.get_new_records(..., after=after_token)
        """
        all_records = []
        after_token = None
        before_token = None

        while True:
            response = await self.get_paginated(
                path,
                params=params,
                authenticated=authenticated,
                limit=limit,
                before=before_token,
            )

            records = response.get("records", [])
            cursor = response.get("cursor", {})

            if not records:
                break

            # Store records (older records, so don't overwrite existing)
            all_records.extend(records)

            # Remember the after token from first request
            if after_token is None:
                after_token = cursor.get("after")

            # Get next page token
            before_token = cursor.get("before")

        return all_records, after_token or ""

    async def get_new_records(
        self,
        path: str,
        after_token: str,
        params: dict[str, Any] | None = None,
        authenticated: bool = False,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], str]:
        """
        Get new or modified records since last check.

        This implements the "Monitor for new data" pattern from ESI docs.

        Args:
            path: API path
            after_token: Token from previous request
            params: Query parameters
            authenticated: Whether request requires authentication
            limit: Records per request

        Returns:
            Tuple of (new_records, latest_after_token)

        Example:
            new_records, new_token = await client.get_new_records(
                "/characters/123/assets/",
                after_token=last_token,
                authenticated=True
            )
            # Update last_token = new_token for next check
        """
        new_records = []
        current_after = after_token

        while True:
            response = await self.get_paginated(
                path,
                params=params,
                authenticated=authenticated,
                limit=limit,
                after=current_after,
            )

            records = response.get("records", [])
            cursor = response.get("cursor", {})

            if not records:
                break

            # All records from "after" are newer
            new_records.extend(records)

            # Update token for next iteration
            current_after = cursor.get("after")

        return new_records, current_after or after_token
