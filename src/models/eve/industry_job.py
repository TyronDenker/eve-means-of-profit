"""EVE Online industry job data models."""

from datetime import datetime

from pydantic import BaseModel, Field


class EveIndustryJob(BaseModel):
    """Represents an industry job from ESI.

    Industry jobs include manufacturing, research, invention, and reaction jobs.
    """

    job_id: int = Field(..., description="Unique job ID")
    installer_id: int = Field(..., description="Character who installed")
    facility_id: int = Field(..., description="Structure/station ID")
    station_id: int = Field(default=0, description="Deprecated, use facility_id")
    activity_id: int = Field(
        ..., description="Activity type (1=manufacturing, 3=research_time, etc.)"
    )
    blueprint_id: int = Field(..., description="Blueprint item ID")
    blueprint_type_id: int = Field(..., description="Blueprint type")
    blueprint_location_id: int = Field(..., description="Where blueprint is")
    output_location_id: int = Field(..., description="Where output goes")
    runs: int = Field(..., description="Number of runs")
    cost: float = Field(..., description="Job cost")
    licensed_runs: int | None = Field(None, description="Licensed runs (for BPCs)")
    probability: float | None = Field(
        None, description="Success probability (invention)"
    )
    product_type_id: int | None = Field(
        None, description="Output type (if manufacturing)"
    )
    status: str = Field(..., description="active, paused, ready, delivered, cancelled")
    duration: int = Field(..., description="Duration in seconds")
    start_date: datetime = Field(..., description="When started")
    end_date: datetime = Field(..., description="When finishes")
    pause_date: datetime | None = Field(None, description="If paused")
    completed_date: datetime | None = Field(None, description="When completed")
    completed_character_id: int | None = Field(None, description="Who completed")
    successful_runs: int | None = Field(None, description="Successful runs")
