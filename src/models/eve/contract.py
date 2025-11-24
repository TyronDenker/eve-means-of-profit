"""EVE Online contract data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class EveContract(BaseModel):
    """Represents a contract from ESI.

    Contracts include item exchanges, auctions, and courier contracts.
    """

    contract_id: int = Field(..., description="Unique contract ID")
    issuer_id: int = Field(..., description="Character/corp that issued")
    issuer_corporation_id: int = Field(..., description="Corp of issuer")
    assignee_id: int = Field(..., description="Assigned to (0 = public)")
    acceptor_id: int = Field(..., description="Who accepted (0 if not accepted)")
    start_location_id: int = Field(..., description="Start location")
    end_location_id: int | None = Field(None, description="End location (for courier)")
    type: str = Field(..., description="item_exchange, auction, courier")
    status: str = Field(..., description="outstanding, in_progress, finished, etc.")
    title: str | None = Field(None, description="Contract title")
    for_corporation: bool = Field(..., description="Corp contract or personal")
    availability: str = Field(..., description="public, personal, corporation")
    date_issued: datetime = Field(..., description="When created")
    date_expired: datetime = Field(..., description="When expires")
    date_accepted: datetime | None = Field(None, description="When accepted")
    date_completed: datetime | None = Field(None, description="When completed")
    days_to_complete: int | None = Field(None, description="Days to complete")
    price: float | None = Field(None, description="Price (for auction/exchange)")
    reward: float | None = Field(None, description="Reward (for courier)")
    collateral: float | None = Field(None, description="Collateral (for courier)")
    buyout: float | None = Field(None, description="Buyout price (for auction)")
    volume: float | None = Field(None, description="m³ volume")


class EveContractItem(BaseModel):
    """Represents an item in a contract from ESI."""

    record_id: int = Field(..., description="Unique record ID")
    contract_id: int = Field(..., description="Parent contract")
    type_id: int = Field(..., description="Item type")
    quantity: int = Field(..., description="Quantity")
    is_included: bool = Field(..., description="True = included, False = requested")
    is_singleton: bool = Field(..., description="Unique item")
