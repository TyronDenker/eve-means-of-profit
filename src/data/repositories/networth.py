"""Repository functions for net worth tracking.

This module provides functions for storing and querying net worth snapshots
and their detailed component breakdowns.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from models.app import NetWorthSnapshot

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_snapshot(
    repo: Repository,
    character_id: int,
    totals: NetWorthSnapshot,
    account_id: int | None = None,
    snapshot_group_id: int | None = None,
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
            character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value, wallet_balance,
            market_escrow, market_sell_value, contract_collateral,
            contract_value, industry_job_value, plex_vault
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            character_id,
            account_id,
            snapshot_group_id,
            totals.snapshot_time.isoformat(),
            totals.total_asset_value,
            totals.wallet_balance,
            totals.market_escrow,
            totals.market_sell_value,
            totals.contract_collateral,
            totals.contract_value,
            totals.industry_job_value,
            totals.plex_vault,
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
            snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
            total_asset_value,
            wallet_balance, market_escrow, market_sell_value,
            contract_collateral, contract_value, industry_job_value, plex_vault
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
    repo: Repository,
    character_id: int,
    limit: int | None = 30,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[NetWorthSnapshot]:
    """Get net worth history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        limit: Maximum number of snapshots to return (set to None for no limit)
        start: Optional earliest snapshot_time (inclusive)
        end: Optional latest snapshot_time (inclusive)

    Returns:
        List of NetWorthSnapshot models in reverse chronological order
    """
    clauses = ["character_id = ?"]
    params: list[object] = [character_id]
    if start is not None:
        clauses.append("snapshot_time >= ?")
        params.append(start.isoformat())
    if end is not None:
        clauses.append("snapshot_time <= ?")
        params.append(end.isoformat())

    sql = """
        SELECT
            snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
            total_asset_value,
            wallet_balance, market_escrow, market_sell_value,
            contract_collateral, contract_value, industry_job_value, plex_vault
        FROM networth_snapshots
        WHERE {where}
        ORDER BY snapshot_time DESC
    """.format(where=" AND ".join(clauses))

    if limit is not None:
        sql += "\n        LIMIT ?"
        params.append(limit)

    rows = await repo.fetchall(sql, tuple(params))

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
            ns.snapshot_id, ns.character_id, ns.account_id, ns.snapshot_group_id, ns.snapshot_time,
            ns.total_asset_value,
            ns.wallet_balance, ns.market_escrow, ns.market_sell_value,
            ns.contract_collateral, ns.contract_value, ns.industry_job_value, ns.plex_vault
        FROM networth_snapshots ns
        INNER JOIN (
            SELECT character_id, MAX(snapshot_time) as max_time
            FROM networth_snapshots
            GROUP BY character_id
        ) latest ON ns.character_id = latest.character_id
                 AND ns.snapshot_time = latest.max_time
        ORDER BY ns.snapshot_time DESC
        """
    )

    return [NetWorthSnapshot(**dict(row)) for row in rows]


async def get_snapshots_up_to_time(
    repo: Repository, target_time: datetime, character_ids: list[int] | None = None
) -> list[NetWorthSnapshot]:
    """Get, for each character, the latest snapshot whose snapshot_time <= target_time.

    This returns at most one snapshot per character where that snapshot's
    snapshot_time is the greatest value less than or equal to `target_time`.
    Works with both grouped and legacy (ungrouped) snapshots.

    Args:
        repo: Repository instance
        target_time: Target timestamp (inclusive upper bound)
        character_ids: Optional list of character ids to limit the query

    Returns:
        List of NetWorthSnapshot models (one per character)
    """
    params: list[object] = [target_time.isoformat()]
    char_filter = ""
    if character_ids:
        placeholders = ",".join("?" for _ in character_ids)
        char_filter = f"AND ns.character_id IN ({placeholders})"
        params.extend(character_ids)

    # Use ROW_NUMBER to pick the latest snapshot per character by time
    rows = await repo.fetchall(
        f"""
        SELECT
            snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
            total_asset_value,
            wallet_balance, market_escrow, market_sell_value,
            contract_collateral, contract_value, industry_job_value, plex_vault
        FROM (
            SELECT ns.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY ns.character_id
                       ORDER BY ns.snapshot_time DESC
                   ) as rn
            FROM networth_snapshots ns
            WHERE ns.snapshot_time <= ?
            {char_filter}
        ) t
        WHERE rn = 1
        ORDER BY character_id
        """,
        tuple(params),
    )

    return [NetWorthSnapshot(**dict(row)) for row in rows]


async def get_snapshots_for_group(
    repo: Repository, snapshot_group_id: int, character_ids: list[int] | None = None
) -> list[NetWorthSnapshot]:
    """Get, for each character, the latest snapshot whose snapshot_group_id <= target.

    This returns at most one snapshot per character where that snapshot's
    snapshot_group_id is the greatest value less than or equal to
    `snapshot_group_id`. Useful for building an aggregate 'Total' for a
    snapshot group by summing the returned per-character snapshots.

    Note: This only considers snapshots with a non-NULL snapshot_group_id.
    For mixed aggregation (grouped + legacy), use get_snapshots_up_to_time instead.

    Args:
        repo: Repository instance
        snapshot_group_id: Target snapshot group id
        character_ids: Optional list of character ids to limit the query

    Returns:
        List of NetWorthSnapshot models (one per character)
    """
    params: list[object] = [snapshot_group_id]
    char_filter = ""
    if character_ids:
        placeholders = ",".join("?" for _ in character_ids)
        char_filter = f"AND ns.character_id IN ({placeholders})"
        params.extend(character_ids)

    # SQLite supports window functions; use ROW_NUMBER to pick the latest
    # snapshot per character ordering by snapshot_group_id DESC, then time.
    rows = await repo.fetchall(
        f"""
        SELECT
            snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
            total_asset_value,
            wallet_balance, market_escrow, market_sell_value,
            contract_collateral, contract_value, industry_job_value, plex_vault
        FROM (
            SELECT ns.*,
                   ROW_NUMBER() OVER (
                       PARTITION BY ns.character_id
                       ORDER BY ns.snapshot_group_id DESC, ns.snapshot_time DESC
                   ) as rn
            FROM networth_snapshots ns
            WHERE ns.snapshot_group_id IS NOT NULL AND ns.snapshot_group_id <= ?
            {char_filter}
        ) t
        WHERE rn = 1
        ORDER BY character_id
        """,
        tuple(params),
    )

    return [NetWorthSnapshot(**dict(row)) for row in rows]


async def update_snapshot(repo: Repository, snapshot: NetWorthSnapshot) -> None:
    """Update an existing net worth snapshot in-place.

    Allows updating all editable fields including character_id for
    reassigning a snapshot to a different character.
    """

    await repo.execute(
        """
        UPDATE networth_snapshots
        SET character_id = ?, total_asset_value = ?, wallet_balance = ?, market_escrow = ?,
            market_sell_value = ?, contract_collateral = ?, contract_value = ?,
            industry_job_value = ?, plex_vault = ?
        WHERE snapshot_id = ?
        """,
        (
            snapshot.character_id,
            snapshot.total_asset_value,
            snapshot.wallet_balance,
            snapshot.market_escrow,
            snapshot.market_sell_value,
            snapshot.contract_collateral,
            snapshot.contract_value,
            snapshot.industry_job_value,
            snapshot.plex_vault,
            snapshot.snapshot_id,
        ),
    )
    await repo.commit()
    logger.info("Updated networth snapshot %s", snapshot.snapshot_id)


async def delete_snapshot(repo: Repository, snapshot_id: int) -> None:
    """Delete a net worth snapshot by ID."""

    await repo.execute(
        "DELETE FROM networth_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    )
    await repo.commit()
    logger.info("Deleted networth snapshot %s", snapshot_id)


async def save_account_plex_snapshot(
    repo: Repository,
    account_id: int,
    plex_units: int,
    plex_unit_price: float,
    snapshot_group_id: int | None = None,
    snapshot_time: datetime | None = None,
) -> int:
    """Save an account-level PLEX snapshot.

    Stores PLEX vault data at the account level, linked to snapshot groups
    for proper aggregation during graph generation.

    Args:
        repo: Repository instance
        account_id: Account ID
        plex_units: PLEX units in vault
        plex_unit_price: Market price per PLEX unit (ISK)
        snapshot_group_id: Optional snapshot group to associate with
        snapshot_time: Optional snapshot timestamp (defaults to now)

    Returns:
        plex_snapshot_id of the created snapshot

    Example:
        plex_id = await networth.save_account_plex_snapshot(
            repo,
            account_id=1,
            plex_units=500,
            plex_unit_price=2500.0,
            snapshot_group_id=42
        )
    """
    if snapshot_time is None:
        snapshot_time = datetime.now(UTC)

    plex_total_value = float(plex_units) * float(plex_unit_price)
    cursor = await repo.execute(
        """
        INSERT INTO account_plex_snapshots (
            account_id, snapshot_group_id, snapshot_time, plex_units, plex_unit_price, plex_total_value
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            account_id,
            snapshot_group_id,
            snapshot_time.isoformat(),
            plex_units,
            plex_unit_price,
            plex_total_value,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for account PLEX snapshot.")
    snapshot_id = int(cursor.lastrowid)
    await repo.commit()
    logger.info(
        "Saved account PLEX snapshot %d for account %d (units=%d, group=%s)",
        snapshot_id,
        account_id,
        plex_units,
        snapshot_group_id,
    )
    return snapshot_id


async def save_character_lifecycle_event(
    repo: Repository,
    character_id: int,
    event_type: str,
    account_id: int | None = None,
    metadata: str | None = None,
) -> int:
    """Track character lifecycle changes (added, removed, account_changed).

    Records when characters are added to tracking, removed, or moved between
    accounts. Used by Phase 3 graph aggregation to filter characters by
    lifecycle status at specific points in time.

    Args:
        repo: Repository instance
        character_id: Character ID

        event_type: 'added', 'removed', or 'account_changed'
        account_id: Associated account ID
        metadata: JSON string with additional context (optional)

    Returns:
        lifecycle_id of created event

    Example:
        # Character added
        await networth.save_character_lifecycle_event(
            repo,
            character_id=12345,
            event_type='added',
            account_id=1,
            metadata='{"source": "import"}'
        )

        # Character removed
        await networth.save_character_lifecycle_event(
            repo,
            character_id=12345,
            event_type='removed',
            account_id=1,
            metadata='{"reason": "inactive"}'
        )

    """
    if event_type not in ("added", "removed", "account_changed"):
        raise ValueError(f"Invalid event_type: {event_type}")

    event_time = datetime.now(UTC).isoformat()
    cursor = await repo.execute(
        """
        INSERT INTO character_lifecycle
        (character_id, account_id, event_type, event_time, metadata)
        VALUES (?, ?, ?, ?, ?)
        """,
        (character_id, account_id, event_type, event_time, metadata),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for lifecycle event.")
    lifecycle_id = int(cursor.lastrowid)
    await repo.commit()
    logger.info(
        "Saved lifecycle event %d for character %d: %s",
        lifecycle_id,
        character_id,
        event_type,
    )
    return lifecycle_id


async def get_character_added_time(
    repo: Repository, character_id: int
) -> datetime | None:
    """Get the time when a character was added.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        datetime when character was added, or None if not found
    """
    row = await repo.fetchone(
        """
        SELECT event_time
        FROM character_lifecycle
        WHERE character_id = ? AND event_type = 'added'
        ORDER BY event_time ASC
        LIMIT 1
        """,
        (character_id,),
    )

    if row and row["event_time"]:
        return datetime.fromisoformat(row["event_time"])
    return None


async def get_character_removed_time(
    repo: Repository, character_id: int
) -> datetime | None:
    """Get the time when a character was removed.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        datetime when character was removed, or None if not removed
    """
    row = await repo.fetchone(
        """
        SELECT event_time
        FROM character_lifecycle
        WHERE character_id = ? AND event_type = 'removed'
        ORDER BY event_time DESC
        LIMIT 1
        """,
        (character_id,),
    )

    if row and row["event_time"]:
        return datetime.fromisoformat(row["event_time"])
    return None


async def get_active_characters_at_time(
    repo: Repository, target_time: str | None = None
) -> list[int]:
    """Get list of characters that were active at a given time.

    A character is considered active at a time if:
    - It has an 'added' event on or before the time
    - It has no 'removed' event before the time (or no removed event at all)

    Args:
        repo: Repository instance
        target_time: ISO format timestamp (defaults to now)

    Returns:
        List of active character IDs
    """
    if target_time is None:
        target_time = datetime.now(UTC).isoformat()

    rows = await repo.fetchall(
        """
        SELECT DISTINCT cl.character_id
        FROM character_lifecycle cl
        WHERE cl.event_type = 'added'
        AND cl.event_time <= ?
        AND NOT EXISTS (
            SELECT 1 FROM character_lifecycle cl2
            WHERE cl2.character_id = cl.character_id
            AND cl2.event_type = 'removed'
            AND cl2.event_time <= ?
        )
        """,
        (target_time, target_time),
    )

    return [int(row["character_id"]) for row in rows]


async def get_account_plex_for_group(
    repo: Repository, snapshot_group_id: int
) -> list[dict]:
    """Get all PLEX snapshots for a snapshot group.

    Args:
        repo: Repository instance
        snapshot_group_id: Snapshot group ID

    Returns:
        List of PLEX snapshot records
    """
    rows = await repo.fetchall(
        """
        SELECT plex_snapshot_id, account_id, snapshot_group_id, snapshot_time,
               plex_units, plex_unit_price, plex_total_value
        FROM account_plex_snapshots
        WHERE snapshot_group_id = ?
        """,
        (snapshot_group_id,),
    )
    return [dict(row) for row in rows]


__all__ = [
    "delete_snapshot",
    "get_account_plex_for_group",
    "get_active_characters_at_time",
    "get_all_characters_networth",
    "get_character_added_time",
    "get_character_removed_time",
    "get_latest_networth",
    "get_networth_history",
    "get_snapshots_for_group",
    "get_snapshots_up_to_time",
    "save_account_plex_snapshot",
    "save_character_lifecycle_event",
    "save_snapshot",
    "update_snapshot",
]
