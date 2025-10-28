"""EVE Online market price data models."""

from pydantic import BaseModel, Field


class MarketPrice(BaseModel):
    """Represents market price data for an EVE type in a specific region.

    Data sourced from Fuzzwork's aggregate market data.
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
