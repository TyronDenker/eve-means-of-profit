"""ESI endpoint classes for organized API access."""

from .assets import AssetsEndpoints
from .character import CharacterEndpoints
from .contracts import ContractsEndpoints
from .corporation import CorporationEndpoints
from .industry import IndustryEndpoints
from .location import LocationEndpoints
from .market import MarketEndpoints
from .universe import UniverseEndpoints
from .wallet import WalletEndpoints

__all__ = [
    "AssetsEndpoints",
    "CharacterEndpoints",
    "ContractsEndpoints",
    "CorporationEndpoints",
    "IndustryEndpoints",
    "LocationEndpoints",
    "MarketEndpoints",
    "UniverseEndpoints",
    "WalletEndpoints",
]
