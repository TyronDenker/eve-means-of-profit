"""EVE Online asset data models."""

from pydantic import BaseModel, Field


class EveAsset(BaseModel):
    """Represents a character or corporation asset from ESI."""

    item_id: int = Field(..., description="Unique ID for this asset")
    type_id: int = Field(..., description="Type ID of the item")
    quantity: int = Field(..., ge=1, description="Quantity of items")
    location_id: int = Field(..., description="Location ID where asset is stored")
    location_type: str = Field(
        ..., description="Type of location (station, solar_system, etc)"
    )
    location_flag: str = Field(
        ..., description="Specific location flag (Hangar, Cargo, etc)"
    )
    is_singleton: bool = Field(..., description="Whether this is a unique item")
    is_blueprint_copy: bool | None = Field(
        None, description="If blueprint, whether it's a copy"
    )
