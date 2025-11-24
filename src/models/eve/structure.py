"""EVE Online structure data model."""

from pydantic import BaseModel, Field

from .position import EvePosition


class EveStructure(BaseModel):
    """Represents a player-owned structure.

    Only mention data sources in field descriptions when the field is
    unique to that source.
    """

    name: str = Field(..., description="Name of the structure")
    owner_id: int = Field(..., description="Corporation ID that owns the structure")
    solar_system_id: int = Field(
        ..., description="Solar system where structure is located"
    )
    type_id: int | None = Field(None, description="Type ID of the structure")
    position: EvePosition | None = Field(
        None, description="Structure coordinates (x, y, z)"
    )
