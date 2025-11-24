"""EVE Online wallet journal data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class EveJournalEntry(BaseModel):
    """Represents a wallet journal entry from ESI.

    Wallet journal shows complete ISK flow ledger (bounties, taxes, contract
    payments, etc.) for a character.
    """

    id: int = Field(..., description="Unique journal entry ID", alias="entry_id")
    date: datetime = Field(..., description="Entry timestamp")
    ref_type: str = Field(
        ..., description="Entry type (bounty_prizes, market_transaction, etc.)"
    )
    first_party_id: int = Field(..., description="First party involved")
    second_party_id: int | None = Field(
        None, description="Second party (if applicable)"
    )
    amount: float = Field(..., description="ISK amount (can be negative)")
    balance: float = Field(..., description="Wallet balance after entry")
    reason: str | None = Field(None, description="Additional context")
    description: str = Field(..., description="Human-readable description")
    context_id: int | None = Field(
        None, description="Related entity (contract ID, etc.)"
    )
    context_id_type: str | None = Field(
        None, description="Type of context (contract, structure, etc.)"
    )

    class Config:
        """Pydantic config."""

        populate_by_name = True
