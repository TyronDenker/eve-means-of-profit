"""EVE Online market order data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class EveMarketOrder(BaseModel):
    """Represents a market order from ESI.

    Market orders show active buy/sell orders on the market for a character.
    """

    order_id: int = Field(..., description="Unique order ID")
    type_id: int = Field(..., description="Item type being traded")
    location_id: int = Field(..., description="Where order is placed")
    volume_total: int = Field(..., description="Original volume")
    volume_remain: int = Field(..., description="Remaining volume")
    min_volume: int = Field(1, description="Minimum buy volume")
    price: float = Field(..., description="ISK per unit")
    is_buy_order: bool | None = Field(None, description="Buy or sell order")
    duration: int = Field(..., description="Days duration")
    issued: datetime = Field(..., description="When order was placed")
    range: str = Field(..., description="Order range (station, region, etc.)")
    state: str = Field("active", description="Order state (active, cancelled, expired)")
    region_id: int = Field(..., description="Region ID")
    is_corporation: bool = Field(..., description="Corp order or personal")
    escrow: float | None = Field(None, description="ISK in escrow (buy orders)")
