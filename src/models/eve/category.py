"""EVE Online category data models."""

from pydantic import BaseModel, Field


class EveCategory(BaseModel):
    """Represents an EVE Online category."""

    id: int = Field(
        ..., ge=0, description="The unique identifier for the Eve category."
    )
    icon_id: int | None = Field(None, ge=0, description="The icon ID for the category.")
    name: str = Field(..., description="The name of the category.")
    published: bool = Field(..., description="Whether the category is published.")
