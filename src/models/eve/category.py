"""EVE Online category data models."""

from pydantic import BaseModel, Field

from .text import EveLocalizedTextRequired


class EveCategory(BaseModel):
    """Represents an EVE Online category."""

    id: int = Field(
        ..., ge=0, le=350001, description="The unique identifier for the Eve category."
    )
    icon_id: int | None = Field(
        None, ge=0, le=24296, description="The icon ID for the category."
    )
    name: EveLocalizedTextRequired
    published: bool = Field(..., description="Whether the category is published.")
