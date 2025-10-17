"""EVE Online type data models."""

from pydantic import BaseModel, Field

from .text import EveLocalizedText


class EveType(BaseModel):
    """Represents an EVE Online type with various attributes."""

    id: int = Field(
        ..., ge=0, le=371027, description="The unique identifier for the Eve type."
    )
    base_price: float | None = Field(
        None,
        ge=1,
        le=700_000_000_000,
        description="The base price of the Eve type in ISK (Interstellar Kredits).",
    )
    capacity: float | None = Field(
        None,
        ge=0.01,
        le=999_999_999,
        description="The cargo capacity of the Eve type in cubic meters.",
    )
    description: EveLocalizedText | None = Field(
        None, description="A localized description of the Eve type."
    )
    faction_id: int | None = Field(
        None,
        ge=500_001,
        le=1_000_419,
        description="The ID of the faction associated with the Eve type.",
    )
    graphic_id: int | None = Field(
        None,
        ge=10,
        le=28_898,
        description="The ID of the graphic asset associated with the Eve type.",
    )
    group_id: int = Field(
        ...,
        ge=0,
        le=368_726,
        description="The ID of the group to which the Eve type belongs.",
    )
    icon_id: int | None = Field(
        None,
        ge=0,
        le=27_110,
        description="The ID of the icon associated with the Eve type.",
    )
    market_group_id: int | None = Field(
        None,
        ge=20,
        le=3_794,
        description="The ID of the market group where the Eve type is listed.",
    )
    mass: float | None = Field(
        None,
        ge=0.001,
        le=100_000_000_000_000_000_000_000_000_000_000_000,
        description="The mass of the Eve type in kilograms.",
    )
    meta_group_id: int | None = Field(
        None,
        ge=1,
        le=54,
        description="The ID of the meta group associated with the Eve type.",
    )
    name: EveLocalizedText = Field(
        ..., description="The localized name of the Eve type."
    )
    portion_size: int = Field(
        ...,
        ge=1,
        le=57_344,
        description="The portion size of the Eve type, used in manufacturing and reprocessing.",
    )
    published: bool = Field(
        ...,
        description="Indicates whether the Eve type is published and available in the game.",
    )
    race_id: int | None = Field(
        None,
        ge=1,
        le=168,
        description="The ID of the race associated with the Eve type.",
    )
    radius: float | None = Field(
        None,
        ge=2,
        le=5_000_000_000_000,
        description="The radius of the Eve type in meters.",
    )
    sound_id: int | None = Field(
        None,
        ge=9,
        le=79_428,
        description="The ID of the sound asset associated with the Eve type.",
    )
    variation_parent_type_id: int | None = Field(
        None,
        ge=178,
        le=85_230,
        description="The ID of the parent type for variations of the Eve type.",
    )
    volume: float | None = Field(
        None,
        ge=0.0002,
        le=100_000_000_000,
        description="The volume of the Eve type in cubic meters.",
    )
