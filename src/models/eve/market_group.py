"""EVE Online market group data models."""

from pydantic import BaseModel, Field

from .text import EveLocalizedText


class EveMarketGroup(BaseModel):
    """Represents an EVE Online market group."""

    id: int = Field(
        ...,
        ge=2,
        le=3794,
        description="The unique identifier for the Eve market group.",
    )
    description: EveLocalizedText | None = None
    has_types: bool = Field(..., description="Whether the market group has types.")
    icon_id: int | None = Field(
        None, ge=15, le=26799, description="The icon ID for the market group."
    )
    name: EveLocalizedText
    parent_group_id: int | None = Field(
        None, ge=2, le=3719, description="The parent market group ID."
    )
