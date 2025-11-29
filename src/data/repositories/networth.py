"""Repository functions for net worth tracking.

This module provides functions for storing and querying net worth snapshots
and their detailed component breakdowns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.app import NetWorthSnapshot

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_snapshot(
    repo: Repository,
    character_id: int,
    totals: NetWorthSnapshot,
) -> int:
    """Save a net worth snapshot with component breakdown.

    Args:
        repo: Repository instance
        character_id: Character ID
        components: List of net worth components
        totals: Aggregated net worth snapshot

    Returns:
        snapshot_id of the created snapshot
    """
    # Create snapshot record
    cursor = await repo.execute(
        """
        INSERT INTO networth_snapshots (
            character_id, snapshot_time, total_asset_value, wallet_balance,
            market_escrow, market_sell_value, contract_collateral,
            contract_value, industry_job_value
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            character_id,
            totals.snapshot_time.isoformat(),
            totals.total_asset_value,
            totals.wallet_balance,
            totals.market_escrow,
            totals.market_sell_value,
            totals.contract_collateral,
            totals.contract_value,
            totals.industry_job_value,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for networth snapshot.")
    snapshot_id = int(cursor.lastrowid)
    await repo.commit()
    logger.info(
        "Saved net worth snapshot %d for character %d",
        snapshot_id,
        character_id,
    )
    return snapshot_id


async def get_latest_networth(
    repo: Repository, character_id: int
) -> NetWorthSnapshot | None:
    """Get the most recent net worth snapshot for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        NetWorthSnapshot if found, None otherwise
    """
    row = await repo.fetchone(
        """
        SELECT
            snapshot_id, character_id, snapshot_time,
            total_asset_value,
            wallet_balance, market_escrow, market_sell_value,
            contract_collateral, contract_value, industry_job_value,
        FROM networth_snapshots
        WHERE character_id = ?
        ORDER BY snapshot_time DESC
        LIMIT 1
        """,
        (character_id,),
    )

    if row:
        return NetWorthSnapshot(**dict(row))
    return None


async def get_networth_history(
    repo: Repository, character_id: int, limit: int = 30
) -> list[NetWorthSnapshot]:
    """Get net worth history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        limit: Maximum number of snapshots to return

    Returns:
        List of NetWorthSnapshot models in reverse chronological order
    """
    rows = await repo.fetchall(
        """
        SELECT
            snapshot_id, character_id, snapshot_time,
            total_asset_value,
            wallet_balance, market_escrow, market_sell_value,
            contract_collateral, contract_value, industry_job_value,
        FROM networth_snapshots
        WHERE character_id = ?
        ORDER BY snapshot_time DESC
        LIMIT ?
        """,
        (character_id, limit),
    )

    return [NetWorthSnapshot(**dict(row)) for row in rows]


async def get_all_characters_networth(
    repo: Repository,
) -> list[NetWorthSnapshot]:
    """Get latest net worth for all characters.

    Args:
        repo: Repository instance

    Returns:
        List of NetWorthSnapshot models (one per character)
    """
    rows = await repo.fetchall(
        """
        SELECT
            ns.snapshot_id, ns.character_id, ns.snapshot_time,
            ns.total_asset_value,
            ns.wallet_balance, ns.market_escrow, ns.market_sell_value,
            ns.contract_collateral, ns.contract_value, ns.industry_job_value,
        FROM networth_snapshots ns
        INNER JOIN (
            SELECT character_id, MAX(snapshot_time) as max_time
            FROM networth_snapshots
            GROUP BY character_id
        ) latest ON ns.character_id = latest.character_id
                 AND ns.snapshot_time = latest.max_time
        ORDER BY ns.total_net_worth DESC
        """
    )

    return [NetWorthSnapshot(**dict(row)) for row in rows]


__all__ = [
    "get_all_characters_networth",
    "get_latest_networth",
    "get_networth_history",
    "save_snapshot",
]
