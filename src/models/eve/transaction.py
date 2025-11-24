"""EVE Online wallet transaction data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class EveTransaction(BaseModel):
    """Represents a wallet transaction from ESI.

    Wallet transactions show the history of market buy/sell trades for a character.
    """

    transaction_id: int = Field(..., description="Unique transaction ID")
    date: datetime = Field(..., description="When transaction occurred")
    type_id: int = Field(..., description="Item type traded")
    quantity: int = Field(..., description="Quantity traded")
    unit_price: float = Field(..., description="Price per unit")
    client_id: int = Field(..., description="Buyer/seller character/corp ID")
    location_id: int = Field(..., description="Where trade happened")
    is_buy: bool = Field(..., description="True if character bought, False if sold")
    is_personal: bool = Field(..., description="True if personal trade, False if corp")
    journal_ref_id: int = Field(..., description="Link to journal entry")
