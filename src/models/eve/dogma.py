"""EVE Online dogma data models."""

from typing import Literal

from pydantic import BaseModel, Field

from .text import EveLocalizedText, EveLocalizedTextRequired


class EveDogmaAttributeCategory(BaseModel):
    """Represents an EVE Online dogma attribute category."""

    id: int = Field(
        ...,
        ge=1,
        le=52,
        alias="_key",
        description="The unique identifier for the dogma attribute category.",
    )
    description: str | None = Field(
        None, description="Description of the attribute category."
    )
    name: str = Field(..., description="Name of the attribute category.")


class EveDogmaAttribute(BaseModel):
    """Represents an EVE Online dogma attribute."""

    id: int = Field(
        ...,
        ge=2,
        le=5964,
        alias="_key",
        description="The unique identifier for the dogma attribute.",
    )
    attribute_category_id: int | None = Field(
        None,
        ge=1,
        le=52,
        alias="attributeCategoryID",
        description="The category ID this attribute belongs to.",
    )
    charge_recharge_time_id: int | None = Field(
        None,
        ge=55,
        le=479,
        alias="chargeRechargeTimeID",
        description="Charge recharge time ID.",
    )
    data_type: int = Field(
        ..., ge=0, le=13, alias="dataType", description="Data type of the attribute."
    )
    default_value: float = Field(
        ...,
        ge=-1000,
        le=2147483648000,
        alias="defaultValue",
        description="Default value of the attribute.",
    )
    description: str | None = Field(None, description="Description of the attribute.")
    display_name: EveLocalizedText | None = Field(
        None, alias="displayName", description="Localized display name."
    )
    display_when_zero: bool = Field(
        ..., alias="displayWhenZero", description="Whether to display when zero."
    )
    high_is_good: bool = Field(
        ..., alias="highIsGood", description="Whether higher values are better."
    )
    icon_id: int | None = Field(
        None, ge=0, le=25874, alias="iconID", description="Icon ID."
    )
    max_attribute_id: int | None = Field(
        None,
        ge=263,
        le=5732,
        alias="maxAttributeID",
        description="Maximum attribute ID.",
    )
    min_attribute_id: int | None = Field(
        None,
        ge=2266,
        le=2266,
        alias="minAttributeID",
        description="Minimum attribute ID.",
    )
    name: str = Field(..., description="Name of the attribute.")
    published: bool = Field(..., description="Whether the attribute is published.")
    stackable: bool = Field(..., description="Whether the attribute is stackable.")
    tooltip_description: EveLocalizedText | None = Field(
        None, alias="tooltipDescription", description="Localized tooltip description."
    )
    tooltip_title: EveLocalizedText | None = Field(
        None, alias="tooltipTitle", description="Localized tooltip title."
    )
    unit_id: int | None = Field(
        None, ge=1, le=205, alias="unitID", description="Unit ID."
    )


class EveDogmaEffectModifierInfo(BaseModel):
    """Represents modifier info for dogma effects."""

    domain: Literal[
        "shipID", "targetID", "charID", "itemID", "otherID", "target", "structureID"
    ] = Field(..., description="Domain of the modifier.")
    effect_id: int | None = Field(
        None, ge=4921, le=6442, alias="effectID", description="Effect ID."
    )
    func: Literal[
        "ItemModifier",
        "LocationModifier",
        "LocationGroupModifier",
        "LocationRequiredSkillModifier",
        "OwnerRequiredSkillModifier",
        "EffectStopper",
    ] = Field(..., description="Function type.")
    group_id: int | None = Field(
        None, ge=38, le=4117, alias="groupID", description="Group ID."
    )
    modified_attribute_id: int | None = Field(
        None,
        ge=4,
        le=5960,
        alias="modifiedAttributeID",
        description="Modified attribute ID.",
    )
    modifying_attribute_id: int | None = Field(
        None,
        ge=4,
        le=5964,
        alias="modifyingAttributeID",
        description="Modifying attribute ID.",
    )
    operation: int | None = Field(None, ge=-1, le=9, description="Operation type.")
    skill_type_id: int | None = Field(
        None, ge=3300, le=86260, alias="skillTypeID", description="Skill type ID."
    )


class EveDogmaEffect(BaseModel):
    """Represents an EVE Online dogma effect."""

    id: int = Field(
        ...,
        ge=4,
        le=12579,
        alias="_key",
        description="The unique identifier for the dogma effect.",
    )
    description: EveLocalizedTextRequired | None = Field(
        None, description="Localized description."
    )
    disallow_auto_repeat: bool = Field(
        ...,
        alias="disallowAutoRepeat",
        description="Whether auto repeat is disallowed.",
    )
    discharge_attribute_id: int | None = Field(
        None,
        ge=6,
        le=5660,
        alias="dischargeAttributeID",
        description="Discharge attribute ID.",
    )
    display_name: EveLocalizedTextRequired | None = Field(
        None, alias="displayName", description="Localized display name."
    )
    distribution: int | None = Field(None, ge=1, le=2, description="Distribution type.")
    duration_attribute_id: int | None = Field(
        None,
        ge=51,
        le=5657,
        alias="durationAttributeID",
        description="Duration attribute ID.",
    )
    effect_category_id: int = Field(
        ..., ge=0, le=7, alias="effectCategoryID", description="Effect category ID."
    )
    electronic_chance: bool = Field(
        ..., alias="electronicChance", description="Electronic chance flag."
    )
    falloff_attribute_id: int | None = Field(
        None,
        ge=158,
        le=5659,
        alias="falloffAttributeID",
        description="Falloff attribute ID.",
    )
    fitting_usage_chance_attribute_id: int | None = Field(
        None,
        ge=1089,
        le=1093,
        alias="fittingUsageChanceAttributeID",
        description="Fitting usage chance attribute ID.",
    )
    guid: str | None = Field(None, description="GUID.")
    icon_id: int | None = Field(
        None, ge=0, le=3756, alias="iconID", description="Icon ID."
    )
    is_assistance: bool = Field(
        ..., alias="isAssistance", description="Whether it's assistance."
    )
    is_offensive: bool = Field(
        ..., alias="isOffensive", description="Whether it's offensive."
    )
    is_warp_safe: bool = Field(
        ..., alias="isWarpSafe", description="Whether it's warp safe."
    )
    modifier_info: list[EveDogmaEffectModifierInfo] | None = Field(
        None, alias="modifierInfo", description="List of modifier info."
    )
    name: str = Field(..., description="Name of the effect.")
    npc_activation_chance_attribute_id: int | None = Field(
        None,
        ge=930,
        le=1682,
        alias="npcActivationChanceAttributeID",
        description="NPC activation chance attribute ID.",
    )
    npc_usage_chance_attribute_id: int | None = Field(
        None,
        ge=504,
        le=1664,
        alias="npcUsageChanceAttributeID",
        description="NPC usage chance attribute ID.",
    )
    propulsion_chance: bool = Field(
        ..., alias="propulsionChance", description="Propulsion chance flag."
    )
    published: bool = Field(..., description="Whether the effect is published.")
    range_attribute_id: int | None = Field(
        None,
        ge=54,
        le=5658,
        alias="rangeAttributeID",
        description="Range attribute ID.",
    )
    range_chance: bool = Field(
        ..., alias="rangeChance", description="Range chance flag."
    )
    resistance_attribute_id: int | None = Field(
        None,
        ge=2045,
        le=2253,
        alias="resistanceAttributeID",
        description="Resistance attribute ID.",
    )
    tracking_speed_attribute_id: int | None = Field(
        None,
        ge=160,
        le=160,
        alias="trackingSpeedAttributeID",
        description="Tracking speed attribute ID.",
    )


class EveDogmaUnit(BaseModel):
    """Represents an EVE Online dogma unit."""

    id: int = Field(
        ...,
        ge=1,
        le=205,
        alias="_key",
        description="The unique identifier for the dogma unit.",
    )
    description: EveLocalizedTextRequired | None = Field(
        None, description="Localized description."
    )
    display_name: EveLocalizedTextRequired | None = Field(
        None, alias="displayName", description="Localized display name."
    )
    name: str = Field(..., description="Name of the unit.")
