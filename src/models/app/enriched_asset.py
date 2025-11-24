"""Enriched asset model with SDE and location data."""

from pydantic import BaseModel, ConfigDict, Field, computed_field


class EnrichedAsset(BaseModel):
    """Asset with SDE enrichment, location resolution, and computed fields."""

    model_config = ConfigDict(
        validate_assignment=True,  # Validate when fields are set
        arbitrary_types_allowed=True,
    )

    # Raw ESI fields
    item_id: int
    type_id: int
    quantity: int
    location_id: int
    location_type: str
    location_flag: str
    is_singleton: bool
    is_blueprint_copy: bool | None

    # Hierarchy (from flattener)
    parent_id: int | None = None
    depth: int = 0
    container_path: str = ""

    # SDE enrichment
    type_name: str = ""
    group_id: int | None = None
    group_name: str = ""
    category_id: int | None = None
    category_name: str = ""
    volume: float = 0.0
    packaged_volume: float | None = None

    # Market data (optional)
    base_price: float | None = None
    market_value: float | None = None

    # Location enrichment
    region_id: int | None = None
    region_name: str = ""
    constellation_id: int | None = None
    constellation_name: str = ""
    system_id: int | None = None
    system_name: str = ""
    station_id: int | None = None
    station_name: str = ""
    structure_id: int | None = None  # ID of the player structure (if in a structure)
    structure_name: str = ""

    # User metadata (TODO: persistence)
    tags: list[str] = Field(default_factory=list)
    notes: str = ""

    # Ownership (character that owns this asset)
    owner_character_id: int | None = None
    owner_character_name: str = ""

    # Computed fields
    @computed_field  # type: ignore[misc]
    @property
    def total_volume(self) -> float:
        """Total volume for this stack."""
        if self.is_singleton:
            return self.volume
        return self.volume * self.quantity

    @computed_field  # type: ignore[misc]
    @property
    def total_value(self) -> float:
        """Total estimated value for this stack."""
        price = self.market_value or self.base_price or 0.0
        return price * self.quantity

    @computed_field  # type: ignore[misc]
    @property
    def packaged(self) -> str:
        """Human-readable packaged status."""
        return "No" if self.is_singleton else "Yes"

    @computed_field  # type: ignore[misc]
    @property
    def location_display(self) -> str:
        """Human-readable location string."""
        if self.structure_name:
            return self.structure_name
        if self.station_name:
            return self.station_name
        if self.system_name:
            return f"{self.system_name} (Space)"
        # Show location type and flag for debugging unresolved locations
        return (
            f"Location #{self.location_id} ({self.location_type}/{self.location_flag})"
        )

    @computed_field  # type: ignore[misc]
    @property
    def tags_display(self) -> str:
        """Tags as comma-separated string."""
        return ", ".join(self.tags) if self.tags else ""
