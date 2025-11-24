"""Market data models for EVE Online market statistics."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class FuzzworkMarketStats(BaseModel):
    """Aggregate market statistics for buy or sell orders.

    Maps to Fuzzwork CSV aggregate data fields.
    """

    weighted_average: float = Field(ge=0, description="Weighted average price")
    max_price: float = Field(ge=0, description="Maximum price")
    min_price: float = Field(ge=0, description="Minimum price")
    stddev: float = Field(ge=0, description="Standard deviation")
    median: float = Field(ge=0, description="Median price")
    volume: int = Field(ge=0, description="Total volume")
    num_orders: int = Field(ge=0, description="Number of orders")
    five_percent: float = Field(ge=0, description="5th percentile price")


class FuzzworkRegionMarketData(BaseModel):
    """Market data for a specific region containing buy and sell statistics."""

    region_id: int = Field(description="EVE region identifier")
    buy_stats: FuzzworkMarketStats | None = Field(
        default=None, description="Buy order statistics"
    )
    sell_stats: FuzzworkMarketStats | None = Field(
        default=None, description="Sell order statistics"
    )

    def has_buy_orders(self) -> bool:
        """Check if this region has buy order data.

        Returns:
            True if buy statistics are available

        """
        return self.buy_stats is not None

    def has_sell_orders(self) -> bool:
        """Check if this region has sell order data.

        Returns:
            True if sell statistics are available

        """
        return self.sell_stats is not None


class FuzzworkMarketDataPoint(BaseModel):
    """Market data point for a single item type across all regions.

    Contains buy and sell statistics for each region where the item is traded.
    """

    type_id: int = Field(description="EVE item type identifier")
    snapshot_time: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this data was captured",
    )
    region_data: dict[int, FuzzworkRegionMarketData] = Field(
        default_factory=dict, description="Per-region market statistics"
    )

    def has_buy_orders(self) -> bool:
        """Check if this type has buy orders in any region.

        Returns:
            True if buy order statistics are available in any region

        """
        return any(region.has_buy_orders() for region in self.region_data.values())

    def has_sell_orders(self) -> bool:
        """Check if this type has sell orders in any region.

        Returns:
            True if sell order statistics are available in any region

        """
        return any(region.has_sell_orders() for region in self.region_data.values())
