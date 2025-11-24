"""Assets-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models import EveAsset

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class AssetsEndpoints:
    """Handles all assets-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        assets: list[EveAsset] = await client.assets.get_assets(character_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize assets endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_assets(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
        return_headers: bool = False,
    ) -> list[EveAsset] | tuple[list[EveAsset], dict]:
        """Get all assets for a character (all pages combined).

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch
            return_headers: Return headers along with data

        Returns:
            List of validated EveAsset models, or tuple of (assets, headers) if return_headers=True

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/assets/"

        # Collect all pages using paginated_request
        all_assets: list[dict] = []
        first_headers: dict | None = None

        # If we need headers, make one direct request for first page to get them
        if return_headers:
            first_page_data, first_headers = await self._client.request(
                "GET",
                path,
                use_cache=(use_cache and not bypass_cache),
                owner_id=character_id,
                params={"page": 1},
            )
            if isinstance(first_page_data, list):
                all_assets.extend(first_page_data)

            # Get total pages from headers
            x_pages = first_headers.get("x-pages", "1")
            try:
                total_pages = int(x_pages)
            except (ValueError, TypeError):
                total_pages = 1

            # Fetch remaining pages
            for page in range(2, total_pages + 1):
                page_data, _ = await self._client.request(
                    "GET",
                    path,
                    use_cache=(use_cache and not bypass_cache),
                    owner_id=character_id,
                    params={"page": page},
                )
                if isinstance(page_data, list):
                    all_assets.extend(page_data)
        else:
            # When headers not needed, use the more efficient paginated_request
            async for page_data in self._client.paginated_request(
                "GET",
                path,
                use_cache=(use_cache and not bypass_cache),
                owner_id=character_id,
            ):
                if isinstance(page_data, list):
                    all_assets.extend(page_data)

        # Validate and return as Pydantic models
        logger.info(
            "Retrieved %d assets for character %d", len(all_assets), character_id
        )
        validated = [EveAsset.model_validate(asset) for asset in all_assets]
        if return_headers:
            return validated, first_headers or {}
        return validated
