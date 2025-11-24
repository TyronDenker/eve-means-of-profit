"""Shared geometric types for EVE models."""

from pydantic import BaseModel, Field


class EvePosition(BaseModel):
    """3D coordinates (x, y, z)."""

    x: float = Field(..., description="X coordinate")
    y: float = Field(..., description="Y coordinate")
    z: float = Field(..., description="Z coordinate")
