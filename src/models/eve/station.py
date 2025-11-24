"""EVE Online station data model."""

from pydantic import BaseModel, Field

from .position import EvePosition


class EveStation(BaseModel):
    """Station model combining ESI and SDE fields.

    Field descriptions only mention the data source when a field is
    unique to either ESI or SDE.
    """

    station_id: int | None = Field(
        None,
        alias="station_id",
    )

    name: str | None = Field(None, description="Name of the station.")

    owner: int | None = Field(
        None,
        description="Corporation ID that controls this station.",
    )

    system_id: int | None = Field(
        None,
        description="Solar system this station is in.",
    )

    type_id: int | None = Field(None, description="Type ID of the station.")

    position: EvePosition | None = Field(
        None,
        description="Station coordinates as an object with x, y, z.",
    )

    race_id: int | None = Field(None, description="Race ID of the station.")

    services: list[str] | None = Field(
        None,
        description="List of services available at the station (ESI-only).",
    )

    max_dockable_ship_volume: float | None = Field(
        None,
        description="Maximum dockable ship volume (ESI-only).",
    )
    office_rental_cost: float | None = Field(
        None,
        description="Office rental cost in ISK (ESI-only).",
    )

    # Reprocessing fields
    reprocessing_efficiency: float | None = Field(
        None, description="Reprocessing efficiency."
    )

    reprocessing_stations_take: float | None = Field(
        None,
        description="Portion taken by reprocessing stations.",
    )

    reprocessing_hangar_flag: int | None = Field(
        None, description="Reprocessing hangar flag (SDE-only)."
    )

    celestial_index: int | None = Field(
        None, description="SDE celestialIndex (SDE-only)."
    )
    operation_id: int | None = Field(None, description="SDE operationID (SDE-only).")
    orbit_id: int | None = Field(None, description="SDE orbitID (SDE-only).")
    orbit_index: int | None = Field(None, description="SDE orbitIndex (SDE-only).")
    use_operation_name: bool | None = Field(
        None, description="SDE useOperationName (SDE-only)."
    )
