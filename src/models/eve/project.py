"""EVE Online corporation project data models."""

from pydantic import BaseModel, Field


class EveCorporationProject(BaseModel):
    """Represents a corporation infrastructure project from ESI."""

    project_id: int = Field(..., description="Unique project ID")
    location_id: int = Field(..., description="Location where project is running")
    blueprint_type_id: int = Field(..., description="Type ID of the blueprint")
    runs: int = Field(..., ge=1, description="Number of runs for this project")
    completed: int = Field(..., ge=0, description="Number of completed runs")
    status: str = Field(
        ..., description="Project status (active, delivered, cancelled)"
    )
