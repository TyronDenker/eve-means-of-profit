"""EVE Online location data models."""

from pydantic import BaseModel, Field


class EveLocation(BaseModel):
    """Represents a character's current location from ESI."""

    solar_system_id: int = Field(
        ..., description="Solar system ID where character is located"
    )
    station_id: int | None = Field(None, description="Station ID if docked")
    structure_id: int | None = Field(
        None, description="Structure ID if docked at player structure"
    )
