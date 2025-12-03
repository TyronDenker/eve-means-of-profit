"""EVE Online group data models."""

from pydantic import BaseModel, Field


class EveGroup(BaseModel):
    """Represents an EVE Online group."""

    group_id: int = Field(
        ..., ge=0, description="The unique identifier for the Eve group.", alias="id"
    )
    anchorable: bool = Field(..., description="Whether the group is anchorable.")
    anchored: bool = Field(..., description="Whether the group is anchored.")
    category_id: int = Field(
        ..., ge=0, description="The category ID this group belongs to."
    )
    fittable_non_singleton: bool = Field(
        ..., description="Whether the group is fittable non-singleton."
    )
    icon_id: int | None = Field(None, ge=0, description="The icon ID for the group.")
    name: str = Field(..., description="The name of the group.")
    published: bool = Field(..., description="Whether the group is published.")
    use_base_price: bool = Field(..., description="Whether the group uses base price.")
