"""EVE Online type material data models."""

from pydantic import BaseModel, Field


class EveTypeMaterialItem(BaseModel):
    """Represents a material item for an EVE Online type."""

    material_type_id: int = Field(
        ..., ge=34, le=88087, description="The material type ID."
    )
    quantity: int = Field(
        ..., ge=1, le=387522911, description="The quantity of the material."
    )


class EveTypeMaterial(BaseModel):
    """Represents materials for an EVE Online type."""

    id: int = Field(
        ..., ge=18, le=89606, description="The unique identifier for the Eve type."
    )
    materials: list[EveTypeMaterialItem] = Field(
        ..., description="The list of materials for the type."
    )
