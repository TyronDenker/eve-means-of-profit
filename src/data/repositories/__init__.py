"""Repository layer for historical data storage.

This package provides a unified SQLite repository for all application data
with organized access methods for different data types:

- Repository: Single database connection for all data
- assets: Functions for asset tracking and history (delta-based)
- prices: Functions for market price history (Fuzzwork data)
- transactions: Functions for wallet transaction tracking
- journal: Functions for wallet journal tracking
- market_orders: Functions for market order tracking
- contracts: Functions for contract tracking
- industry_jobs: Functions for industry job tracking
- networth: Functions for networth snapshots, PLEX tracking, and lifecycle events

Usage:
    from data.repositories import Repository, assets, prices, networth

    repo = Repository()
    await repo.initialize()

    # Use asset functions
    snapshot_id = await assets.save_snapshot(repo, character_id, asset_list)
    current = await assets.get_current_assets(repo, character_id)

    # Use networth functions
    plex_id = await networth.save_account_plex_snapshot(repo, account_id, units, price)
    active = await networth.get_active_characters_at_time(repo, target_time)
"""

from __future__ import annotations

from . import (
    assets,
    contracts,
    custom_prices,
    industry_jobs,
    journal,
    market_orders,
    networth,
    prices,
    transactions,
)
from .repository import Repository

__all__ = [
    "Repository",
    "assets",
    "contracts",
    "custom_prices",
    "industry_jobs",
    "journal",
    "market_orders",
    "networth",
    "prices",
    "transactions",
]
