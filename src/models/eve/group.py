"""EVE Online group data models."""

from pydantic import BaseModel, Field

from .text import EveLocalizedTextRequired


class EveGroup(BaseModel):
    """Represents an EVE Online group."""

    id: int = Field(
        ..., ge=0, le=368726, description="The unique identifier for the Eve group."
    )
    anchorable: bool = Field(..., description="Whether the group is anchorable.")
    anchored: bool = Field(..., description="Whether the group is anchored.")
    category_id: int = Field(
        ..., ge=0, le=350001, description="The category ID this group belongs to."
    )
    fittable_non_singleton: bool = Field(
        ..., description="Whether the group is fittable non-singleton."
    )
    icon_id: int | None = Field(
        None, ge=0, le=26457, description="The icon ID for the group."
    )
    name: EveLocalizedTextRequired
    published: bool = Field(..., description="Whether the group is published.")
    use_base_price: bool = Field(..., description="Whether the group uses base price.")
