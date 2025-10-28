"""EVE Online data models."""

from .blueprint import EveBlueprint
from .category import EveCategory
from .dogma import (
    EveDogmaAttribute,
    EveDogmaAttributeCategory,
    EveDogmaEffect,
    EveDogmaUnit,
)
from .group import EveGroup
from .market_group import EveMarketGroup
from .market_price import MarketPrice
from .text import EveLocalizedText, EveLocalizedTextRequired
from .type import EveType
from .type_material import EveTypeMaterial

__all__ = [
    "EveBlueprint",
    "EveCategory",
    "EveDogmaAttribute",
    "EveDogmaAttributeCategory",
    "EveDogmaEffect",
    "EveDogmaUnit",
    "EveGroup",
    "EveLocalizedText",
    "EveLocalizedTextRequired",
    "EveMarketGroup",
    "EveType",
    "EveTypeMaterial",
    "MarketPrice",
]
