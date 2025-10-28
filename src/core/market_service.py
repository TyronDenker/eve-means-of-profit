"""Market service for orchestrating market operations.

This service provides high-level market operations and
coordinates between price analyzer and market data manager.
"""

import logging
from typing import Any

from src.data.managers import MarketDataManager
from src.models.eve import MarketPrice

logger = logging.getLogger(__name__)


class RegionalPriceComparison(dict[str, Any]):
    """Data structure for regional price comparison."""

    pass


class MarketService:
    """Service for orchestrating market-related operations.

    This service provides high-level market functionality,
    coordinating between various market data sources.
    """

    def __init__(self, market_manager: MarketDataManager):
        """Initialize the market service.

        Args:
            market_manager: MarketDataManager for price data access

        """
        self._market_manager = market_manager

    def get_market_summary(
        self, type_id: int, all_regions: bool = False
    ) -> dict[str, Any]:
        """Get market summary for a type.

        Args:
            type_id: Type ID to summarize
            all_regions: Include all regions or just major hubs

        Returns:
            Dictionary with market summary data

        """
        available_regions = self._market_manager.get_available_regions_for_type(type_id)

        summary: dict[str, Any] = {
            "type_id": type_id,
            "available_regions": available_regions,
            "total_regions": len(available_regions),
            "has_data": len(available_regions) > 0,
        }

        if not available_regions:
            return summary

        # Get price range across all regions
        all_sell_prices: list[float] = []
        all_buy_prices: list[float] = []

        for region_id in available_regions:
            sell = self._market_manager.get_price(
                type_id, region_id, is_buy_order=False
            )
            buy = self._market_manager.get_price(type_id, region_id, is_buy_order=True)

            if sell:
                all_sell_prices.append(sell.min_val)
            if buy:
                all_buy_prices.append(buy.max_val)

        if all_sell_prices:
            summary["lowest_sell"] = min(all_sell_prices)
            summary["highest_sell"] = max(all_sell_prices)
            summary["avg_sell"] = sum(all_sell_prices) / len(all_sell_prices)

        if all_buy_prices:
            summary["lowest_buy"] = min(all_buy_prices)
            summary["highest_buy"] = max(all_buy_prices)
            summary["avg_buy"] = sum(all_buy_prices) / len(all_buy_prices)

        return summary

    def compare_regional_prices(
        self, type_id: int, regions: list[int] | None = None
    ) -> list[dict[str, Any]]:
        """Compare prices across multiple regions.

        Args:
            type_id: Type ID to compare
            regions: List of region IDs (default: major hubs)

        Returns:
            List of regional price data dictionaries

        """
        if regions is None:
            # Default to major trade hubs
            regions = [
                10000002,  # The Forge (Jita)
                10000043,  # Domain (Amarr)
                10000032,  # Sinq Laison (Dodixie)
                10000030,  # Heimatar (Rens)
                10000042,  # Metropolis (Hek)
            ]

        comparisons: list[dict[str, Any]] = []

        for region_id in regions:
            sell_price = self._market_manager.get_price(
                type_id, region_id, is_buy_order=False
            )
            buy_price = self._market_manager.get_price(
                type_id, region_id, is_buy_order=True
            )

            comparison: dict[str, Any] = {
                "region_id": region_id,
                "has_data": sell_price is not None or buy_price is not None,
            }

            if sell_price:
                comparison["sell_min"] = sell_price.min_val
                comparison["sell_avg"] = sell_price.weighted_average
                comparison["sell_volume"] = sell_price.volume

            if buy_price:
                comparison["buy_max"] = buy_price.max_val
                comparison["buy_avg"] = buy_price.weighted_average
                comparison["buy_volume"] = buy_price.volume

            # Calculate spread if both available
            if sell_price and buy_price:
                spread = buy_price.max_val - sell_price.min_val
                comparison["spread"] = spread
                comparison["spread_percent"] = (
                    (spread / sell_price.min_val * 100)
                    if sell_price.min_val > 0
                    else 0.0
                )

            comparisons.append(comparison)

        return comparisons

    def get_market_statistics(
        self, type_id: int, region_id: int
    ) -> dict[str, Any] | None:
        """Get detailed market statistics for a type in a region.

        Args:
            type_id: Type ID to analyze
            region_id: Region ID

        Returns:
            Dictionary with comprehensive market statistics

        """
        sell_price = self._market_manager.get_price(
            type_id, region_id, is_buy_order=False
        )
        buy_price = self._market_manager.get_price(
            type_id, region_id, is_buy_order=True
        )

        if not sell_price and not buy_price:
            return None

        stats: dict[str, Any] = {
            "type_id": type_id,
            "region_id": region_id,
        }

        if sell_price:
            stats["sell"] = {
                "weighted_avg": sell_price.weighted_average,
                "min": sell_price.min_val,
                "max": sell_price.max_val,
                "median": sell_price.median,
                "std_dev": sell_price.std_dev,
                "volume": sell_price.volume,
                "orders": sell_price.num_orders,
            }

        if buy_price:
            stats["buy"] = {
                "weighted_avg": buy_price.weighted_average,
                "min": buy_price.min_val,
                "max": buy_price.max_val,
                "median": buy_price.median,
                "std_dev": buy_price.std_dev,
                "volume": buy_price.volume,
                "orders": buy_price.num_orders,
            }

        # Calculate spread
        if sell_price and buy_price:
            spread = buy_price.max_val - sell_price.min_val
            stats["spread"] = {
                "value": spread,
                "percent": (
                    (spread / sell_price.min_val * 100)
                    if sell_price.min_val > 0
                    else 0.0
                ),
            }

        return stats
