"""
ESI API Client.

Main client that orchestrates authentication, rate limiting, and caching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx

from models.eve import EveCharacter, EVEMarketPrice

from .auth import TokenProvider
from .cache import CacheBackend
from .rate_limiter import RateLimiter

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ESIClient:
    """
    ESI (EVE Swagger Interface) API Client.

    A comprehensive async client for CCP's EVE Online ESI API with built-in
    support for OAuth2 authentication, automatic rate limiting, response caching,
    and ETag-based cache validation.

    Architecture:
        The client orchestrates three key components:
        - TokenProvider: Handles OAuth2 PKCE flow and token refresh
        - CacheBackend: Manages disk-based caching with ETag support
        - RateLimiter: Tracks and enforces ESI rate limits

    Usage:
        Must be used as an async context manager to properly manage HTTP connections:

        >>> async with ESIClient(
        ...     client_id="your_esi_app_id",
        ...     token_file="path/to/tokens.json",
        ...     cache_dir="path/to/cache/",
        ...     base_url="https://esi.evetech.net/latest",
        ...     user_agent="YourApp/1.0 (contact@example.com)",
        ... ) as client:
        ...     # Public endpoints
        ...     prices = await client.get_public_market_prices()
        ...     character = await client.get_character_info(123456789)
        ...
        ...     # Authenticated endpoints
        ...     client.set_active_character(123456789)
        ...     assets = await client.get(
        ...         "/characters/123456789/assets/", authenticated=True
        ...     )

    Features:
        - Automatic rate limit handling with adaptive throttling
        - Response caching with HTTP ETag validation (304 Not Modified)
        - OAuth2 PKCE authentication flow for secure token management
        - Automatic token refresh when expired
        - Support for cursor-based pagination
        - Typed return values using EVE data models

    Thread Safety:
        This client is NOT thread-safe. Create separate instances for concurrent usage.
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
        """
        Enter async context manager.

        Initializes the HTTP client for making requests.

        Returns:
            Self for context manager usage

        """
        self._http_client = httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=30.0,
        )
        return self

    async def __aexit__(self, *args: Any) -> None:
        """
        Exit async context manager.

        Properly closes HTTP client connections and cleans up resources.

        """
        if self._http_client:
            await self._http_client.aclose()

    def set_active_character(self, character_id: int) -> None:
        """
        Set the active character for authenticated API requests.

        Must be called before making any authenticated requests. The character
        must have previously authenticated via OAuth2 and have a valid token
        stored by the TokenProvider.

        Args:
            character_id: EVE Online character ID to use for authenticated requests

        Example:
            >>> client.set_active_character(123456789)
            >>> assets = await client.get(
            ...     "/characters/123456789/assets/", authenticated=True
            ... )

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
        Make a GET request to the ESI API.

        Handles caching, rate limiting, authentication, and ETag validation automatically.
        Cached responses are served when available, and 304 Not Modified responses are
        handled transparently.

        Args:
            path: API endpoint path (e.g., '/markets/prices/', '/characters/123/assets/')
            params: Optional query parameters as key-value pairs
            authenticated: Whether this request requires OAuth2 authentication.
                          If True, set_active_character() must be called first.
            use_cache: Whether to use cached responses and cache this response.
                      Set to False for real-time data requirements.

        Returns:
            Parsed JSON response data (typically dict or list)

        Raises:
            ValueError: If authenticated=True but no active character is set
            RuntimeError: If called outside of async context manager
            httpx.HTTPStatusError: If the API returns an error status code

        Example:
            >>> # Public endpoint
            >>> data = await client.get("/markets/prices/")
            >>>
            >>> # Authenticated endpoint
            >>> client.set_active_character(123456789)
            >>> assets = await client.get(
            ...     "/characters/123456789/assets/", authenticated=True
            ... )
            >>>
            >>> # With query parameters
            >>> orders = await client.get(
            ...     "/markets/10000002/orders/",
            ...     params={"type_id": 34, "order_type": "sell"},
            ... )

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
        Make a POST request to the ESI API.

        Used for endpoints that modify data or require request bodies.
        Most POST endpoints require authentication.

        Args:
            path: API endpoint path
            data: Request body data as dictionary (will be JSON-encoded)
            params: Optional query parameters
            authenticated: Whether this request requires OAuth2 authentication (default: True).
                          If True, set_active_character() must be called first.

        Returns:
            Parsed JSON response data, or None for 204 No Content responses

        Raises:
            ValueError: If authenticated=True but no active character is set
            RuntimeError: If called outside of async context manager
            httpx.HTTPStatusError: If the API returns an error status code

        Example:
            >>> client.set_active_character(123456789)
            >>> result = await client.post(
            ...     "/ui/openwindow/information/",
            ...     data={"target_id": 34},
            ...     authenticated=True,
            ... )

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

    async def get_public_market_prices(self) -> list[EVEMarketPrice]:
        """
        Get current market prices for all tradeable items.

        Retrieves aggregate market price data from ESI's /markets/prices/ endpoint.
        This is a public endpoint that doesn't require authentication.

        Returns:
            List of EVEMarketPrice objects containing average and adjusted prices

        Example:
            >>> prices = await client.get_public_market_prices()
            >>> for price in prices:
            ...     print(f"Type {price.type_id}: {price.weighted_average:,.2f} ISK")

        """
        data = await self.get("/markets/prices/")
        return [EVEMarketPrice.from_esi(item) for item in data]

    async def get_character_info(self, character_id: int) -> EveCharacter:
        """
        Get public information about a character.

        Retrieves publicly available character data from ESI including name,
        corporation, alliance, and other basic information.

        Args:
            character_id: The character ID to query

        Returns:
            EveCharacter object with character information

        Example:
            >>> character = await client.get_character_info(123456789)
            >>> print(f"{character.name} is in corp {character.corporation_id}")

        """
        data = await self.get(f"/characters/{character_id}/")
        # Add character_id to data since ESI doesn't include it in response
        data["character_id"] = character_id
        return EveCharacter.from_esi(data)

    def get_rate_limit_metrics(self) -> dict[str, int | float]:
        """
        Get current rate limit status and metrics.

        Provides information about ESI rate limit tracking including error
        budget remaining, throttle delays, and rate limit group usage.

        Returns:
            Dictionary containing rate limit metrics:
                - errors_remaining: Number of error budget points left
                - throttle_delay: Current throttle delay in seconds
                - last_update: Timestamp of last rate limit update

        Example:
            >>> metrics = client.get_rate_limit_metrics()
            >>> print(f"Errors remaining: {metrics['errors_remaining']}")

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
        Make a GET request with cursor-based pagination support.

        ESI uses cursor-based pagination for endpoints that return large datasets.
        This method handles the cursor parameters automatically. For most use cases,
        prefer using collect_all_pages() or get_new_records() instead.

        Args:
            path: API endpoint path
            params: Query parameters (limit/before/after will be added automatically)
            authenticated: Whether request requires authentication
            limit: Maximum records per request (default: 100, ESI maximum: 1000)
            before: Cursor token to get records before this position (walk backwards)
            after: Cursor token to get records after this position (walk forwards)

        Returns:
            Dictionary with 'records' (list of data) and 'cursor' (pagination info) keys

        Example:
            >>> # Manual pagination
            >>> response = await client.get_paginated(
            ...     "/characters/123456789/assets/", authenticated=True, limit=100
            ... )
            >>> records = response.get("records", [])
            >>> cursor = response.get("cursor", {})
            >>> next_after = cursor.get("after")
            >>>
            >>> # Get next page
            >>> if next_after:
            ...     next_response = await client.get_paginated(
            ...         "/characters/123456789/assets/",
            ...         authenticated=True,
            ...         after=next_after,
            ...     )

        Note:
            For collecting all pages, use collect_all_pages() instead.
            For monitoring new data, use get_new_records() instead.

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
        Collect all records from a paginated endpoint.

        Implements ESI's "Initial Data Collection" pattern by walking backwards
        through all pages starting from the most recent data. Use this for the
        first-time fetch of large datasets.

        The returned 'after' token can be saved and used with get_new_records()
        to efficiently fetch only new/updated records on subsequent calls.

        Args:
            path: API endpoint path that supports pagination
            params: Optional query parameters
            authenticated: Whether request requires authentication
            limit: Records per page (default: 100, max: 1000)

        Returns:
            Tuple of (all_records, after_token):
                - all_records: Complete list of all records from all pages
                - after_token: Token for monitoring future updates (save this!)

        Example:
            >>> # Initial data collection
            >>> client.set_active_character(123456789)
            >>> all_assets, after_token = await client.collect_all_pages(
            ...     "/characters/123456789/assets/", authenticated=True
            ... )
            >>> print(f"Collected {len(all_assets)} total assets")
            >>>
            >>> # Save after_token for next time
            >>> save_token(after_token)
            >>>
            >>> # Later, fetch only new data
            >>> new_assets, new_token = await client.get_new_records(
            ...     "/characters/123456789/assets/",
            ...     after_token=after_token,
            ...     authenticated=True,
            ... )

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
        Get new or modified records since the last check.

        Implements ESI's "Monitor for New Data" pattern by efficiently fetching
        only records that were added or changed since the provided 'after' token.
        This is much more efficient than re-fetching all data.

        The returned token should be saved and used for the next check to continue
        the monitoring pattern.

        Args:
            path: API endpoint path that supports pagination
            after_token: Token from previous collect_all_pages() or get_new_records() call
            params: Optional query parameters
            authenticated: Whether request requires authentication
            limit: Records per page (default: 100, max: 1000)

        Returns:
            Tuple of (new_records, latest_after_token):
                - new_records: List of only new/modified records
                - latest_after_token: Updated token for next check (save this!)

        Example:
            >>> # Load saved token from previous run
            >>> last_token = load_token()
            >>>
            >>> # Get only new assets since last check
            >>> client.set_active_character(123456789)
            >>> new_assets, updated_token = await client.get_new_records(
            ...     "/characters/123456789/assets/",
            ...     after_token=last_token,
            ...     authenticated=True,
            ... )
            >>>
            >>> if new_assets:
            ...     print(f"Found {len(new_assets)} new/modified assets")
            ...     process_assets(new_assets)
            ... else:
            ...     print("No changes since last check")
            >>>
            >>> # Save updated token for next time
            >>> save_token(updated_token)

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
