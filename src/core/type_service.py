"""Type service for business operations on EVE types.

This service provides business logic for type-related operations,
combining SDE data with market data for comprehensive type information.
"""

import logging
from typing import Any

from data.providers import MarketDataProvider, SDEProvider
from models.eve import EveType

logger = logging.getLogger(__name__)


class TypeService:
    """Service for type-related business operations.

    This service orchestrates SDE and market data to provide
    comprehensive type information and search functionality.
    """

    def __init__(
        self,
        sde_provider: SDEProvider,
        market_provider: MarketDataProvider | None = None,
    ):
        """Initialize the type service.

        Args:
            sde_provider: SDEProvider for type data access
            market_provider: Optional MarketDataProvider for price data

        """
        self._sde_provider = sde_provider
        self._market_provider = market_provider

    def get_type_with_market_data(
        self, type_id: int, region_id: int = 10000002
    ) -> dict[str, Any] | None:
        """Get type information combined with market data.

        Args:
            type_id: Type ID to retrieve
            region_id: Region ID for market prices (default: Jita)

        Returns:
            Dictionary combining type and market data, or None

        """
        eve_type = self._sde_provider.get_type_by_id(type_id)
        if not eve_type:
            return None

        result: dict[str, Any] = {
            "type": eve_type,
            "market_data": None,
        }

        if self._market_provider:
            sell_price = self._market_provider.get_price(
                type_id, region_id, is_buy_order=False
            )
            buy_price = self._market_provider.get_price(
                type_id, region_id, is_buy_order=True
            )

            if sell_price or buy_price:
                result["market_data"] = {
                    "sell": sell_price,
                    "buy": buy_price,
                    "region_id": region_id,
                }

        return result

    def search_types(
        self,
        query: str,
        published_only: bool = True,
        category_id: int | None = None,
        group_id: int | None = None,
        has_market_data: bool = False,
        region_id: int = 10000002,
    ) -> list[EveType]:
        """Search for types with filters.

        Args:
            query: Search query (name or ID)
            published_only: Only include published types
            category_id: Filter by category ID
            group_id: Filter by group ID
            has_market_data: Only types with market data
            region_id: Region to check for market data

        Returns:
            List of matching EveType objects

        """
        # Start with all types or filtered by category/group
        if group_id is not None:
            types = self._sde_provider.get_types_by_group(group_id)
        elif category_id is not None:
            types = self._sde_provider.get_types_by_category(category_id)
        else:
            types = self._sde_provider.get_all_types()

        # Apply published filter
        if published_only:
            types = [t for t in types if t.published]

        # Apply search query
        query_lower = query.lower()
        if query:
            types = [
                t
                for t in types
                if query_lower in t.name.en.lower() or query_lower in str(t.id)
            ]

        # Apply market data filter
        if has_market_data and self._market_provider:
            types = [
                t
                for t in types
                if self._market_provider.has_market_data(t.id, region_id)
            ]

        return types

    def get_profitable_types(
        self,
        region_id: int = 10000002,
        min_margin_percent: float = 5.0,
        min_volume: float = 1000.0,
    ) -> list[tuple[EveType, float]]:
        """Find types with good profit margins.

        Args:
            region_id: Region ID to analyze
            min_margin_percent: Minimum profit margin %
            min_volume: Minimum trade volume

        Returns:
            List of (type, margin_percent) tuples sorted by margin

        """
        if not self._market_provider:
            return []

        profitable: list[tuple[EveType, float]] = []

        # Get all types with market data
        all_types = self._sde_provider.get_published_types()

        for eve_type in all_types:
            if not self._market_provider.has_market_data(eve_type.id, region_id):
                continue

            sell_price = self._market_provider.get_price(
                eve_type.id, region_id, is_buy_order=False
            )
            buy_price = self._market_provider.get_price(
                eve_type.id, region_id, is_buy_order=True
            )

            if not sell_price or not buy_price:
                continue

            # Check volume threshold
            if sell_price.volume < min_volume:
                continue

            # Calculate margin
            spread = buy_price.max_val - sell_price.min_val
            margin_pct = (
                (spread / sell_price.min_val * 100) if sell_price.min_val > 0 else 0.0
            )

            if margin_pct >= min_margin_percent:
                profitable.append((eve_type, margin_pct))

        # Sort by margin (highest first)
        profitable.sort(key=lambda x: x[1], reverse=True)

        return profitable

    def get_type_full_info(self, type_id: int) -> dict[str, Any] | None:
        """Get comprehensive type information.

        Combines SDE data, market data, group, category, etc.

        Args:
            type_id: Type ID to retrieve

        Returns:
            Dictionary with all available type information

        """
        eve_type = self._sde_provider.get_type_by_id(type_id)
        if not eve_type:
            return None

        info: dict[str, Any] = {
            "type": eve_type,
            "group": None,
            "category": None,
            "market_group": None,
            "available_regions": [],
        }

        # Get group
        if eve_type.group_id is not None:
            info["group"] = self._sde_provider.get_group_by_id(eve_type.group_id)

            # Get category from group
            if info["group"] is not None:
                info["category"] = self._sde_provider.get_category_by_id(
                    info["group"].category_id
                )

        # Get market group
        if eve_type.market_group_id is not None:
            info["market_group"] = self._sde_provider.get_market_group_by_id(
                eve_type.market_group_id
            )

        # Get available regions
        if self._market_provider:
            info["available_regions"] = (
                self._market_provider.get_available_regions_for_type(type_id)
            )

        return info
