from pydantic import BaseModel, Field


class EveBlueprintMaterial(BaseModel):
    """Base model for blueprint materials."""

    quantity: int = Field(..., ge=1)
    type_id: int = Field(..., ge=1)


class EveBlueprintSkill(BaseModel):
    """Base model for blueprint skills."""

    level: int = Field(..., ge=0)
    type_id: int = Field(..., ge=1)


class EveBlueprintProduct(BaseModel):
    """Base model for blueprint products."""

    quantity: int = Field(..., ge=1)
    type_id: int = Field(..., ge=1)
    probability: float | None = Field(None, ge=0.0, le=1.0)


# Specific material classes
class CopyingMaterial(EveBlueprintMaterial):
    """Material for copying activity."""

    quantity: int = Field(..., ge=1, le=600)
    type_id: int = Field(..., ge=3812, le=30386)


class InventionMaterial(EveBlueprintMaterial):
    """Material for invention activity."""

    quantity: int = Field(..., ge=1, le=85)
    type_id: int = Field(..., ge=11496, le=81051)


class ManufacturingMaterial(EveBlueprintMaterial):
    """Material for manufacturing activity."""

    quantity: int = Field(..., ge=1, le=80000000)
    type_id: int = Field(..., ge=18, le=88087)


class ReactionMaterial(EveBlueprintMaterial):
    """Material for reaction activity."""

    quantity: int = Field(..., ge=1, le=10000)
    type_id: int = Field(..., ge=34, le=57462)


class ResearchMaterialMaterial(EveBlueprintMaterial):
    """Material for research material activity."""

    quantity: int = Field(..., ge=1, le=140)
    type_id: int = Field(..., ge=3814, le=30386)


class ResearchTimeMaterial(EveBlueprintMaterial):
    """Material for research time activity."""

    quantity: int = Field(..., ge=1, le=120)
    type_id: int = Field(..., ge=3814, le=30386)


# Specific skill classes
class CopyingSkill(EveBlueprintSkill):
    """Skill for copying activity."""

    level: int = Field(..., ge=1, le=5)
    type_id: int = Field(..., ge=3365, le=81050)


class InventionSkill(EveBlueprintSkill):
    """Skill for invention activity."""

    level: int = Field(..., ge=0, le=1)
    type_id: int = Field(..., ge=3400, le=81050)


class ManufacturingSkill(EveBlueprintSkill):
    """Skill for manufacturing activity."""

    level: int = Field(..., ge=0, le=5)
    type_id: int = Field(..., ge=3364, le=81896)


class ReactionSkill(EveBlueprintSkill):
    """Skill for reaction activity."""

    level: int = Field(..., ge=1, le=5)
    type_id: int = Field(..., ge=45746, le=45746)


# Specific product classes
class InventionProduct(BaseModel):
    """Product for invention activity."""

    probability: float = Field(..., ge=0.14, le=0.34)
    quantity: int = Field(..., ge=1, le=20)
    type_id: int = Field(..., ge=784, le=88003)


class ManufacturingProduct(BaseModel):
    """Product for manufacturing activity."""

    quantity: int = Field(..., ge=1, le=5000)
    type_id: int = Field(..., ge=165, le=88721)


class ReactionProduct(BaseModel):
    """Product for reaction activity."""

    quantity: int = Field(..., ge=1, le=10000)
    type_id: int = Field(..., ge=16654, le=57469)


# Activity classes
class EveBlueprintCopying(BaseModel):
    """Copying activity for blueprints."""

    materials: list[CopyingMaterial] | None = None
    skills: list[CopyingSkill] | None = None
    time: int = Field(..., ge=0, le=7200000)


class EveBlueprintInvention(BaseModel):
    """Invention activity for blueprints."""

    materials: list[InventionMaterial] | None = None
    products: list[InventionProduct] | None = None
    skills: list[InventionSkill] | None = None
    time: int = Field(..., ge=0, le=1980000)


class EveBlueprintManufacturing(BaseModel):
    """Manufacturing activity for blueprints."""

    materials: list[ManufacturingMaterial] | None = None
    products: list[ManufacturingProduct] | None = None
    skills: list[ManufacturingSkill] | None = None
    time: int = Field(..., ge=0, le=10800000)


class EveBlueprintReaction(BaseModel):
    """Reaction activity for blueprints."""

    materials: list[ReactionMaterial] = Field(min_length=1)
    products: list[ReactionProduct] = Field(min_length=1)
    skills: list[ReactionSkill] = Field(min_length=1)
    time: int = Field(..., ge=360, le=21600)


class EveBlueprintResearchMaterial(BaseModel):
    """Research material activity for blueprints."""

    materials: list[ResearchMaterialMaterial] | None = None
    skills: list[CopyingSkill] | None = None
    time: int = Field(..., ge=0, le=420000)


class EveBlueprintResearchTime(BaseModel):
    """Research time activity for blueprints."""

    materials: list[ResearchTimeMaterial] | None = None
    skills: list[CopyingSkill] | None = None
    time: int = Field(..., ge=0, le=420000)


class EveBlueprintActivities(BaseModel):
    """Activities for blueprints."""

    copying: EveBlueprintCopying | None = None
    invention: EveBlueprintInvention | None = None
    manufacturing: EveBlueprintManufacturing | None = None
    reaction: EveBlueprintReaction | None = None
    research_material: EveBlueprintResearchMaterial | None = None
    research_time: EveBlueprintResearchTime | None = None


class EveBlueprint(BaseModel):
    """Represents an EVE Online blueprint with various activities."""

    _key: int = Field(..., ge=681, le=88734)
    activities: EveBlueprintActivities
    blueprint_type_id: int = Field(..., ge=681, le=88734)
    max_production_limit: int = Field(..., ge=1, le=1000000)
