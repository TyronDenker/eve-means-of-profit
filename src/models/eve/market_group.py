"""EVE Online market group data models."""

from pydantic import BaseModel, Field


class EveMarketGroup(BaseModel):
    """Represents an EVE Online market group."""

    id: int = Field(
        ...,
        ge=2,
        description="The unique identifier for the Eve market group.",
    )
    description: str | None = Field(
        None, description="A description of the market group."
    )
    has_types: bool = Field(..., description="Whether the market group has types.")
    icon_id: int | None = Field(
        None, ge=15, description="The icon ID for the market group."
    )
    name: str = Field(..., description="The name of the market group.")
    parent_group_id: int | None = Field(
        None, ge=2, description="The parent market group ID."
    )
