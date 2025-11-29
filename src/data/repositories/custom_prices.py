"""Repository functions for user custom price overrides.

These functions allow saving and querying user-specified custom buy/sell
prices as snapshots (versioned), similar to how market price snapshots are
stored. Custom overrides are stored in `custom_price_overrides` and are
linked to `price_snapshots` rows with source='custom'.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from models.app import CustomPrice

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_custom_snapshot(
    repo: Repository,
    custom_prices: dict[int, dict[str, float | None]] | list[CustomPrice],
    notes: str | None = None,
) -> int:
    """Save a versioned snapshot of custom buy/sell overrides.

    Args:
        repo: Repository instance
        custom_prices: Either a dict mapping type_id -> {"buy": float|None, "sell": float|None}
                       or a list of `CustomPrice` models.
        notes: Optional notes stored with the snapshot

    Returns:
        snapshot_id of the created snapshot
    """
    # Normalize input to list of tuples (type_id, buy, sell)
    records: list[tuple[int, float | None, float | None]] = []

    if isinstance(custom_prices, dict):
        for type_id, p in custom_prices.items():
            buy = p.get("buy") if isinstance(p, dict) else None
            sell = p.get("sell") if isinstance(p, dict) else None
            records.append((type_id, buy, sell))
    else:
        for cp in custom_prices:
            records.append((cp.type_id, cp.custom_buy_price, cp.custom_sell_price))

    snapshot_time = datetime.now(UTC)

    # Insert snapshot metadata into price_snapshots with source 'custom'
    cursor = await repo.execute(
        """
        INSERT INTO price_snapshots (snapshot_time, source, total_items, notes)
        VALUES (?, ?, ?, ?)
        """,
        (snapshot_time.isoformat(), "custom", len(records), notes),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for custom price snapshot.")
    snapshot_id = int(cursor.lastrowid)

    if records:
        params = [(snapshot_id, type_id, buy, sell) for (type_id, buy, sell) in records]

        await repo.executemany(
            """
            INSERT INTO custom_price_overrides (
                snapshot_id, type_id, custom_buy_price, custom_sell_price
            ) VALUES (?, ?, ?, ?)
            """,
            params,
        )

    await repo.commit()
    logger.info(
        "Saved custom price snapshot %d with %d overrides",
        snapshot_id,
        len(records),
    )

    return snapshot_id


async def get_custom_prices_for_snapshot(
    repo: Repository, snapshot_id: int
) -> list[CustomPrice]:
    """Return all custom price overrides for a given snapshot."""
    rows = await repo.fetchall(
        """
        SELECT type_id, snapshot_id, custom_buy_price, custom_sell_price
        FROM custom_price_overrides
        WHERE snapshot_id = ?
        ORDER BY type_id
        """,
        (snapshot_id,),
    )

    return [CustomPrice(**dict(row)) for row in rows]


async def get_latest_custom_price(repo: Repository, type_id: int) -> CustomPrice | None:
    """Get the most recent custom price override for a specific type_id.

    Returns the latest `CustomPrice` or None if not found.
    """
    row = await repo.fetchone(
        """
        SELECT c.type_id, c.snapshot_id, c.custom_buy_price, c.custom_sell_price
        FROM custom_price_overrides c
        JOIN price_snapshots ps ON c.snapshot_id = ps.snapshot_id
        WHERE c.type_id = ? AND ps.source = 'custom'
        ORDER BY ps.snapshot_time DESC
        LIMIT 1
        """,
        (type_id,),
    )

    return CustomPrice(**dict(row)) if row else None


__all__ = [
    "get_custom_prices_for_snapshot",
    "get_latest_custom_price",
    "save_custom_snapshot",
]
