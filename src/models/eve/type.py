"""EVE Online type data models."""

from pydantic import BaseModel, Field

from .text import EveLocalizedText


class EveType(BaseModel):
    """Represents an EVE Online type with various attributes."""

    _key: int = Field(
        ..., ge=0, le=371027, description="The unique identifier for the Eve type."
    )
    base_price: float | None = Field(
        None, ge=1, le=700_000_000_000, description="The base price of the Eve type."
    )
    capacity: float | None = Field(None, ge=0.01, le=999_999_999)
    description: EveLocalizedText | None = None
    faction_id: int | None = Field(None, ge=500_001, le=1_000_419)
    graphic_id: int | None = Field(None, ge=10, le=28_898)
    group_id: int = Field(..., ge=0, le=368_726)
    icon_id: int | None = Field(None, ge=0, le=27_110)
    market_group_id: int | None = Field(None, ge=20, le=3_794)
    mass: float | None = Field(
        None, ge=0.001, le=100_000_000_000_000_000_000_000_000_000_000_000
    )
    meta_group_id: int | None = Field(None, ge=1, le=54)
    name: EveLocalizedText
    portion_size: int = Field(..., ge=1, le=57_344)
    published: bool
    race_id: int | None = Field(None, ge=1, le=168)
    radius: float | None = Field(None, ge=2, le=5_000_000_000_000)
    sound_id: int | None = Field(None, ge=9, le=79_428)
    variation_parent_type_id: int | None = Field(None, ge=178, le=85_230)
    volume: float | None = Field(None, ge=0.0002, le=100_000_000_000)
