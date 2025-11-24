"""Market-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveMarketOrder

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class MarketEndpoints:
    """Handles all market-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        orders = await client.market.get_orders(character_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize market endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_orders(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> list[EveMarketOrder]:
        """Get market orders for a character.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveMarketOrder models

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/orders/"

        data, _ = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug(
            "Retrieved %d orders for character %d",
            len(data) if isinstance(data, list) else 0,
            character_id,
        )
        return (
            [EveMarketOrder.model_validate(order) for order in data]
            if isinstance(data, list)
            else []
        )
