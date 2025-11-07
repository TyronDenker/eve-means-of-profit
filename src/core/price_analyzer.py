"""Price analysis service for market data.

This service provides business logic for analyzing market prices,
calculating profit margins, and identifying trading opportunities.
"""

import logging
from typing import Any, TypedDict

from data.providers import MarketDataProvider

logger = logging.getLogger(__name__)


class SpreadData(TypedDict):
    """Data structure for price spread information."""

    spread: float
    spread_percent: float
    sell_price: float
    buy_price: float
    profit_per_unit: float


class MarketStatistics(TypedDict):
    """Market statistics for a type in a region."""

    type_id: int
    region_id: int
    sell_weighted_avg: float | None
    sell_min: float | None
    sell_max: float | None
    buy_weighted_avg: float | None
    buy_min: float | None
    buy_max: float | None
    sell_volume: float | None
    buy_volume: float | None
    spread: float | None
    spread_percent: float | None


class PriceAnalyzer:
    """Service for analyzing market prices and calculating profit metrics.

    This service encapsulates all business logic related to price analysis,
    profit calculations, and trading opportunity identification.
    """

    # Default tax rates for EVE Online
    DEFAULT_SALES_TAX = 0.08  # 8% (can be reduced with skills)
    DEFAULT_BROKER_FEE = 0.03  # 3% (can be reduced with skills/standings)

    def __init__(self, market_provider: MarketDataProvider):
        """Initialize the price analyzer.

        Args:
            market_provider: MarketDataProvider for price data access

        """
        self._market_provider = market_provider

    def calculate_spread(self, type_id: int, region_id: int) -> SpreadData | None:
        """Calculate price spread between buy and sell orders.

        The spread represents the immediate profit potential from
        station trading (buying and immediately selling).

        Args:
            type_id: Type ID to analyze
            region_id: Region ID for price data

        Returns:
            SpreadData with spread information, or None if data unavailable

        """
        sell_price = self._market_provider.get_price(
            type_id, region_id, is_buy_order=False
        )
        buy_price = self._market_provider.get_price(
            type_id, region_id, is_buy_order=True
        )

        if not sell_price or not buy_price:
            return None

        # Best prices: lowest sell, highest buy
        sell = sell_price.min_val
        buy = buy_price.max_val

        # Spread is the difference
        spread = buy - sell

        # Calculate percentage
        spread_pct = (spread / sell * 100) if sell > 0 else 0.0

        return SpreadData(
            spread=spread,
            spread_percent=spread_pct,
            sell_price=sell,
            buy_price=buy,
            profit_per_unit=spread,
        )

    def calculate_profit_margin(
        self,
        buy_price: float,
        sell_price: float,
        include_taxes: bool = True,
        sales_tax: float | None = None,
        broker_fee: float | None = None,
    ) -> dict[str, float]:
        """Calculate profit margin with optional tax considerations.

        Args:
            buy_price: Purchase price per unit
            sell_price: Selling price per unit
            include_taxes: Whether to include taxes in calculation
            sales_tax: Sales tax rate (default: 8%)
            broker_fee: Broker fee rate (default: 3%)

        Returns:
            Dictionary with profit metrics:
                - gross_profit: Profit before taxes
                - net_profit: Profit after taxes
                - gross_margin_pct: Gross margin percentage
                - net_margin_pct: Net margin percentage
                - roi: Return on investment percentage

        """
        if sales_tax is None:
            sales_tax = self.DEFAULT_SALES_TAX
        if broker_fee is None:
            broker_fee = self.DEFAULT_BROKER_FEE

        # Gross profit (no taxes)
        gross_profit = sell_price - buy_price

        # Net profit (with taxes)
        if include_taxes:
            # Sales tax on sell price
            tax_amount = sell_price * sales_tax
            # Broker fees on both buy and sell
            broker_buy = buy_price * broker_fee
            broker_sell = sell_price * broker_fee
            total_fees = tax_amount + broker_buy + broker_sell

            net_profit = gross_profit - total_fees
        else:
            net_profit = gross_profit

        # Calculate margins
        gross_margin_pct = (gross_profit / buy_price * 100) if buy_price > 0 else 0.0
        net_margin_pct = (net_profit / buy_price * 100) if buy_price > 0 else 0.0

        # ROI
        roi = (net_profit / buy_price * 100) if buy_price > 0 else 0.0

        return {
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "gross_margin_pct": gross_margin_pct,
            "net_margin_pct": net_margin_pct,
            "roi": roi,
        }

    def get_market_statistics(
        self, type_id: int, region_id: int
    ) -> MarketStatistics | None:
        """Get comprehensive market statistics for a type.

        Args:
            type_id: Type ID to analyze
            region_id: Region ID for price data

        Returns:
            MarketStatistics with all price metrics, or None if no data

        """
        sell_price = self._market_provider.get_price(
            type_id, region_id, is_buy_order=False
        )
        buy_price = self._market_provider.get_price(
            type_id, region_id, is_buy_order=True
        )

        if not sell_price and not buy_price:
            return None

        # Calculate spread if both prices available
        spread_data = None
        if sell_price and buy_price:
            spread_data = self.calculate_spread(type_id, region_id)

        return MarketStatistics(
            type_id=type_id,
            region_id=region_id,
            sell_weighted_avg=(sell_price.weighted_average if sell_price else None),
            sell_min=sell_price.min_val if sell_price else None,
            sell_max=sell_price.max_val if sell_price else None,
            buy_weighted_avg=(buy_price.weighted_average if buy_price else None),
            buy_min=buy_price.min_val if buy_price else None,
            buy_max=buy_price.max_val if buy_price else None,
            sell_volume=sell_price.volume if sell_price else None,
            buy_volume=buy_price.volume if buy_price else None,
            spread=spread_data["spread"] if spread_data else None,
            spread_percent=(spread_data["spread_percent"] if spread_data else None),
        )

    def find_arbitrage_opportunities(
        self, type_id: int, min_spread_percent: float = 5.0
    ) -> list[tuple[int, SpreadData]]:
        """Find arbitrage opportunities across all regions.

        Args:
            type_id: Type ID to analyze
            min_spread_percent: Minimum spread % to consider

        Returns:
            List of (region_id, spread_data) tuples sorted by spread %

        """
        opportunities: list[tuple[int, SpreadData]] = []

        # Get all regions with data for this type
        regions = self._market_provider.get_available_regions_for_type(type_id)

        for region_id in regions:
            spread_data = self.calculate_spread(type_id, region_id)

            if spread_data and spread_data["spread_percent"] >= min_spread_percent:
                opportunities.append((region_id, spread_data))

        # Sort by spread percentage (highest first)
        opportunities.sort(key=lambda x: x[1]["spread_percent"], reverse=True)

        return opportunities

    def get_best_trading_region(self, type_id: int) -> tuple[int, float] | None:
        """Find the best region for station trading.

        Args:
            type_id: Type ID to analyze

        Returns:
            Tuple of (region_id, spread_percent) or None

        """
        opportunities = self.find_arbitrage_opportunities(
            type_id, min_spread_percent=0.0
        )

        if not opportunities:
            return None

        best_region, best_spread = opportunities[0]
        return (best_region, best_spread["spread_percent"])

    def analyze_market_depth(
        self, type_id: int, region_id: int
    ) -> dict[str, Any] | None:
        """Analyze market depth (volume and order count).

        Args:
            type_id: Type ID to analyze
            region_id: Region ID for price data

        Returns:
            Dictionary with market depth metrics or None

        """
        sell_price = self._market_provider.get_price(
            type_id, region_id, is_buy_order=False
        )
        buy_price = self._market_provider.get_price(
            type_id, region_id, is_buy_order=True
        )

        if not sell_price and not buy_price:
            return None

        total_volume = 0.0
        total_orders = 0

        if sell_price:
            total_volume += sell_price.volume
            total_orders += sell_price.num_orders

        if buy_price:
            total_volume += buy_price.volume
            total_orders += buy_price.num_orders

        # Market health indicators
        volume_ratio = (
            buy_price.volume / sell_price.volume
            if (buy_price and sell_price and sell_price.volume > 0)
            else 0.0
        )

        return {
            "total_volume": total_volume,
            "total_orders": total_orders,
            "sell_volume": sell_price.volume if sell_price else 0.0,
            "buy_volume": buy_price.volume if buy_price else 0.0,
            "sell_orders": sell_price.num_orders if sell_price else 0,
            "buy_orders": buy_price.num_orders if buy_price else 0,
            "volume_ratio": volume_ratio,  # Buy/Sell ratio
            "market_active": total_orders >= 5,  # Arbitrary threshold
        }
