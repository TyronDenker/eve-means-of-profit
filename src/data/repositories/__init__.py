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

Usage:
    from data.repositories import Repository, assets, prices, transactions

    repo = Repository()
    await repo.initialize()

    # Use asset functions
    snapshot_id = await assets.save_snapshot(repo, character_id, asset_list)
    current = await assets.get_current_assets(repo, character_id)

    # Use transaction functions
    count = await transactions.save_transactions(repo, character_id, tx_list)
    recent = await transactions.get_transactions(repo, character_id, limit=50)
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
    # New unified structure
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
