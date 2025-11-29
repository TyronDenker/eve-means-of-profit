"""Framework-agnostic application service for market operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from data.repositories import Repository, market_orders
from models.eve import EveMarketOrder

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class MarketService:
    """Business logic for market order management."""

    def __init__(self, esi_client: ESIClient, repository: Repository):
        self._esi_client = esi_client
        self._repo = repository

    async def sync_orders(self, character_id: int):
        """Sync market orders for a character."""
        result = await self._esi_client.market.get_orders(
            character_id, use_cache=True, bypass_cache=False
        )
        if isinstance(result, tuple):
            orders, headers = result
        else:
            orders = result
            headers = {}
        count = await market_orders.save_orders(self._repo, character_id, orders)
        etag = headers.get("etag")
        expires = headers.get("expires")
        if etag or expires:
            logger.info(
                "Synced %d market orders for character %d (etag=%s expires=%s)",
                count,
                character_id,
                etag,
                expires,
            )
        else:
            logger.info("Synced %d market orders for character %d", count, character_id)

    async def get_order_history(
        self, character_id: int, limit: int = 100
    ) -> list[EveMarketOrder]:
        """Get market order history for a character."""
        return await market_orders.get_order_history(self._repo, character_id, limit)

    async def get_active_orders(self, character_id: int) -> list[EveMarketOrder]:
        """Get active market orders for a character."""
        return await market_orders.get_active_orders(self._repo, character_id)

    async def get_market_exposure(self, character_id: int) -> dict:
        """Calculate market exposure (escrow and sell value) for a character."""
        return await market_orders.calculate_market_exposure(self._repo, character_id)
