"""Location information models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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
    esi_name: str | None = Field(
        default=None,
        description="Canonical name returned by ESI/SDE (kept alongside custom)",
    )
    custom_name: str | None = Field(
        default=None,
        description="User-defined custom name (takes precedence over ESI name)",
    )
    is_placeholder: bool = Field(
        default=False,
        description="True if name couldn't be resolved and is a placeholder",
    )
    solar_system_id: int | None = Field(
        default=None,
        description="Solar system ID where this location exists (for structures/stations)",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Additional cache metadata (timestamps, source, etc.)",
    )


class AssetLocationOption(BaseModel):
    """Summarized asset location data for selection dialogs."""

    location_id: int = Field(..., description="Underlying EVE location identifier")
    display_name: str = Field(..., description="Resolved name shown to the user")
    location_type: str = Field(
        default="",
        description="Location category (station, structure, solar_system, etc.)",
    )
    asset_count: int = Field(
        default=0,
        description="Number of asset rows mapped to this location",
    )
    character_count: int = Field(
        default=0,
        description="Distinct characters owning assets at this location",
    )
    system_name: str | None = Field(
        default=None,
        description="Resolved solar system name, when available",
    )
