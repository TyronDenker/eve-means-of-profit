"""
ESI (EVE Swagger Interface) API Client for EVE Online.

This package provides a comprehensive client for interacting with CCP's ESI API,
including OAuth2 authentication, automatic rate limiting, response caching,
and convenience methods for common endpoints.

Architecture:
    - ESIClient: Main client orchestrating all operations
    - TokenProvider: OAuth2 PKCE authentication and token management
    - CacheBackend: Disk-based response caching with ETag support
    - RateLimiter: Automatic rate limit tracking and throttling

Basic Usage:
    >>> from data.clients.esi import ESIClient
    >>>
    >>> async with ESIClient(
    ...     client_id="your_client_id",
    ...     token_file="tokens.json",
    ...     cache_dir="cache/",
    ...     base_url="https://esi.evetech.net/latest",
    ...     user_agent="YourApp/1.0",
    ... ) as client:
    ...     # Get public market prices
    ...     prices = await client.get_public_market_prices()
    ...
    ...     # Get character information
    ...     character = await client.get_character_info(123456789)
    ...
    ...     # Make authenticated requests
    ...     client.set_active_character(123456789)
    ...     response = await client.get(
    ...         "/characters/123456789/assets/", authenticated=True
    ...     )

Components:
    ESIClient: Main API client with request handling and convenience methods
    TokenProvider: Manages OAuth2 tokens for authenticated requests
    CacheBackend: Handles response caching and ETags for efficiency
    RateLimiter: Monitors and enforces ESI rate limits automatically

For detailed documentation, see the individual class docstrings.
"""

from .auth import TokenProvider
from .cache import CacheBackend
from .client import ESIClient
from .rate_limiter import RateLimiter

__all__ = ["CacheBackend", "ESIClient", "RateLimiter", "TokenProvider"]
