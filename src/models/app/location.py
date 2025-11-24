"""Location information models."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class LocationInfo(BaseModel):
    """Cached location information."""

    location_id: int = Field(...)
    name: str = Field(...)
    category: str = Field(
        ...,
        description="station, solar_system, region, constellation, structure",
    )
    last_checked: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When this data was last checked",
    )
    owner_id: int | None = Field(
        default=None,
        description="Character who owns the asset (for structure access)",
    )
    custom_name: str | None = Field(
        default=None,
        description="User-defined custom name (takes precedence over ESI name)",
    )
    is_placeholder: bool = Field(
        default=False,
        description="True if name couldn't be resolved and is a placeholder",
    )
