"""EVE Online market price data models."""

from typing import Any

from pydantic import BaseModel, Field


class EVEMarketPrice(BaseModel):
    """Represents market price data for an EVE type in a specific region.

    Data sourced from Fuzzwork's aggregate market data or ESI API.
    The 'what' field format is: regionID|typeID|isBuyOrder
    """

    type_id: int = Field(..., description="The type ID for this market entry")
    region_id: int = Field(..., description="The region ID for this market entry")
    is_buy_order: bool = Field(
        ..., description="True if this is a buy order, False if sell order"
    )
    weighted_average: float = Field(
        ..., description="Weighted average price based on volume"
    )
    max_val: float = Field(..., description="Maximum price in the dataset")
    min_val: float = Field(..., description="Minimum price in the dataset")
    std_dev: float = Field(..., description="Standard deviation of prices")
    median: float = Field(..., description="Median price")
    volume: float = Field(..., description="Total volume of orders")
    num_orders: int = Field(..., description="Number of orders")
    five_percent: float = Field(
        ..., description="5th percentile price (best 5% of orders)"
    )
    order_set: int = Field(..., description="Order set identifier (usually region ID)")

    @classmethod
    def from_esi(cls, data: dict[str, Any]) -> "EVEMarketPrice":
        """Create MarketPrice from ESI API response.

        Args:
            data: Raw dictionary from ESI /markets/prices/ endpoint

        Returns:
            MarketPrice instance

        Example ESI response:
            {
                "adjusted_price": 123456.78,
                "average_price": 654321.12,
                "type_id": 34
            }

        Note: ESI /markets/prices/ returns simple price data.
        This method creates a MarketPrice with sensible defaults
        for fields not provided by ESI.
        """
        # ESI market prices don't have region/order type info
        # Use average_price as the primary price metric
        average_price = data.get("average_price", 0.0)
        adjusted_price = data.get("adjusted_price", 0.0)

        # Use average_price as the main price, fallback to adjusted
        price = average_price if average_price > 0 else adjusted_price

        return cls(
            type_id=data["type_id"],
            region_id=0,  # ESI prices are global
            is_buy_order=False,  # ESI prices aren't order-specific
            weighted_average=price,
            max_val=price,
            min_val=price,
            std_dev=0.0,
            median=price,
            volume=0.0,
            num_orders=0,
            five_percent=price,
            order_set=0,
        )

    def __str__(self) -> str:
        """Return string representation of market price."""
        order_type = "BUY" if self.is_buy_order else "SELL"
        return (
            f"MarketPrice(type={self.type_id}, region={self.region_id}, "
            f"{order_type}: {self.weighted_average:,.2f} ISK)"
        )

    def get_best_price(self) -> float:
        """Get the best price for this order type.

        For buy orders, returns max_val (highest buy price).
        For sell orders, returns min_val (lowest sell price).

        Returns:
            Best price for the order type

        """
        return self.max_val if self.is_buy_order else self.min_val
