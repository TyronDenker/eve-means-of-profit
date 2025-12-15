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
    planet_id: int | None = None
    planet_name: str = ""
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
        # Use explicit None checks instead of falsy evaluation to preserve 0.0 for blueprint copies
        price = (
            self.market_value
            if self.market_value is not None
            else (self.base_price if self.base_price is not None else 0.0)
        )
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
        if self.planet_name:
            return self.planet_name
        if self.system_name:
            return f"{self.system_name} (Space)"
        # Friendly mapping for common EVE location flags when unresolved
        flag_map = {
            "Hangar": "Station Hangar",
            "CorpDeliveries": "Corp Deliveries",
            "CorpHangar": "Corp Hangar",
            "CorpSAG1": "Corp Hangar Division 1",
            "CorpSAG2": "Corp Hangar Division 2",
            "CorpSAG3": "Corp Hangar Division 3",
            "CorpSAG4": "Corp Hangar Division 4",
            "CorpSAG5": "Corp Hangar Division 5",
            "CorpSAG6": "Corp Hangar Division 6",
            "CorpSAG7": "Corp Hangar Division 7",
            "Cargo": "Ship Cargo",
            "FleetHangar": "Fleet Hangar",
            "ShipHangar": "Ship Hangar",
            "DroneBay": "Drone Bay",
            "FighterBay": "Fighter Bay",
            "FighterTube": "Fighter Tube",
            "RigSlot0": "Fitted: Rig Slot 0",
            "RigSlot1": "Fitted: Rig Slot 1",
            "RigSlot2": "Fitted: Rig Slot 2",
            "RigSlot3": "Fitted: Rig Slot 3",
            "HiSlot0": "Fitted: High Slot 0",
            "HiSlot1": "Fitted: High Slot 1",
            "HiSlot2": "Fitted: High Slot 2",
            "HiSlot3": "Fitted: High Slot 3",
            "HiSlot4": "Fitted: High Slot 4",
            "HiSlot5": "Fitted: High Slot 5",
            "HiSlot6": "Fitted: High Slot 6",
            "HiSlot7": "Fitted: High Slot 7",
            "MedSlot0": "Fitted: Mid Slot 0",
            "MedSlot1": "Fitted: Mid Slot 1",
            "MedSlot2": "Fitted: Mid Slot 2",
            "MedSlot3": "Fitted: Mid Slot 3",
            "MedSlot4": "Fitted: Mid Slot 4",
            "MedSlot5": "Fitted: Mid Slot 5",
            "MedSlot6": "Fitted: Mid Slot 6",
            "MedSlot7": "Fitted: Mid Slot 7",
            "LoSlot0": "Fitted: Low Slot 0",
            "LoSlot1": "Fitted: Low Slot 1",
            "LoSlot2": "Fitted: Low Slot 2",
            "LoSlot3": "Fitted: Low Slot 3",
            "LoSlot4": "Fitted: Low Slot 4",
            "LoSlot5": "Fitted: Low Slot 5",
            "LoSlot6": "Fitted: Low Slot 6",
            "LoSlot7": "Fitted: Low Slot 7",
            "SubsystemSlot0": "Fitted: Subsystem Slot 0",
            "SubsystemSlot1": "Fitted: Subsystem Slot 1",
            "SubsystemSlot2": "Fitted: Subsystem Slot 2",
            "SubsystemSlot3": "Fitted: Subsystem Slot 3",
            "ServiceSlot0": "Structure Service Slot 0",
            "ServiceSlot1": "Structure Service Slot 1",
            "ServiceSlot2": "Structure Service Slot 2",
            "ServiceSlot3": "Structure Service Slot 3",
            "ServiceSlot4": "Structure Service Slot 4",
            "ServiceSlot5": "Structure Service Slot 5",
            "ServiceSlot6": "Structure Service Slot 6",
            "ServiceSlot7": "Structure Service Slot 7",
            "SpecializedFuelBay": "Fuel Bay",
            "SpecializedOreHold": "Ore Hold",
            "SpecializedGasHold": "Gas Hold",
            "SpecializedMineralHold": "Mineral Hold",
            "SpecializedSalvageHold": "Salvage Hold",
            "SpecializedShipHold": "Ship Hold",
            "SpecializedSmallShipHold": "Small Ship Hold",
            "SpecializedMediumShipHold": "Medium Ship Hold",
            "SpecializedLargeShipHold": "Large Ship Hold",
            "SpecializedIndustrialShipHold": "Industrial Ship Hold",
            "SpecializedAmmoHold": "Ammo Hold",
            "SpecializedCommandCenterHold": "Command Center Hold",
            "SpecializedPlanetaryCommoditiesHold": "Planetary Commodities Hold",
            "SpecializedMaterialBay": "Material Bay",
        }
        friendly_flag = flag_map.get(self.location_flag, self.location_flag)
        return f"Location #{self.location_id} ({self.location_type}/{friendly_flag})"

    @computed_field  # type: ignore[misc]
    @property
    def tags_display(self) -> str:
        """Tags as comma-separated string."""
        return ", ".join(self.tags) if self.tags else ""
