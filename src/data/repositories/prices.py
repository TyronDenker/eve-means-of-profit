"""Price data access methods.

This module provides functions for accessing and managing market price data
through the unified Repository. All functions accept a Repository instance
as their first parameter.

Functions:
    - save_snapshot: Save a new price snapshot from market data
    - get_latest_jita_price: Get the most recent Jita price for an item
    - get_jita_prices: Get historical Jita prices for an item
    - get_price_history: Get price history for any region
    - get_snapshots: Get price snapshot metadata
    - get_items_with_history: Get all items that have price data
    - delete_old_prices: Clean up old price records
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from models.app import FuzzworkMarketDataPoint, PriceHistory, PriceSnapshot

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)

# Jita region ID constant
JITA_REGION_ID = 10000002


async def save_snapshot(
    repo: Repository,
    market_data: list[FuzzworkMarketDataPoint],
    notes: str | None = None,
    custom_prices: dict[int, dict[str, float | None]] | None = None,
    snapshot_group_id: int | None = None,
) -> int:
    """Save a new price snapshot from Fuzzwork data including custom prices.

    Args:
        repo: Repository instance
        market_data: List of market data points to save
        notes: Optional notes about this snapshot
        custom_prices: Optional dict of custom prices at snapshot time {type_id: {buy, sell}}
        snapshot_group_id: Optional snapshot group to link this price snapshot to

    Returns:
        snapshot_id of the created snapshot
    """
    snapshot_time = datetime.now(UTC)

    # Create price snapshot record
    cursor = await repo.execute(
        """
        INSERT INTO price_snapshots (snapshot_time, source, total_items, notes, snapshot_group_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            snapshot_time.isoformat(),
            "fuzzwork",
            len(market_data),
            notes,
            snapshot_group_id,
        ),
    )
    snapshot_id = cursor.lastrowid

    # Save price data for each item/region combination
    price_records = []
    for item in market_data:
        for region_id, region_data in item.region_data.items():
            # Extract buy stats
            buy_weighted_avg = None
            buy_max = None
            buy_min = None
            buy_stddev = None
            buy_median = None
            buy_volume = None
            buy_num_orders = None
            buy_five_pct = None

            if region_data.buy_stats:
                buy_weighted_avg = region_data.buy_stats.weighted_average
                buy_max = region_data.buy_stats.max_price
                buy_min = region_data.buy_stats.min_price
                buy_stddev = region_data.buy_stats.stddev
                buy_median = region_data.buy_stats.median
                buy_volume = region_data.buy_stats.volume
                buy_num_orders = region_data.buy_stats.num_orders
                buy_five_pct = region_data.buy_stats.five_percent

            # Extract sell stats
            sell_weighted_avg = None
            sell_max = None
            sell_min = None
            sell_stddev = None
            sell_median = None
            sell_volume = None
            sell_num_orders = None
            sell_five_pct = None

            if region_data.sell_stats:
                sell_weighted_avg = region_data.sell_stats.weighted_average
                sell_max = region_data.sell_stats.max_price
                sell_min = region_data.sell_stats.min_price
                sell_stddev = region_data.sell_stats.stddev
                sell_median = region_data.sell_stats.median
                sell_volume = region_data.sell_stats.volume
                sell_num_orders = region_data.sell_stats.num_orders
                sell_five_pct = region_data.sell_stats.five_percent

            # Check for custom prices
            custom_buy = None
            custom_sell = None
            if custom_prices and item.type_id in custom_prices:
                cp = custom_prices[item.type_id]
                custom_buy = cp.get("buy")
                custom_sell = cp.get("sell")

            price_records.append(
                (
                    item.type_id,
                    region_id,
                    snapshot_id,
                    buy_weighted_avg,
                    buy_max,
                    buy_min,
                    buy_stddev,
                    buy_median,
                    buy_volume,
                    buy_num_orders,
                    buy_five_pct,
                    sell_weighted_avg,
                    sell_max,
                    sell_min,
                    sell_stddev,
                    sell_median,
                    sell_volume,
                    sell_num_orders,
                    sell_five_pct,
                    custom_buy,
                    custom_sell,
                )
            )

    # Batch insert all price records
    if price_records:
        await repo.executemany(
            """
            INSERT INTO price_history (
                type_id, region_id, snapshot_id,
                buy_weighted_average, buy_max_price, buy_min_price,
                buy_stddev, buy_median, buy_volume, buy_num_orders,
                buy_five_percent,
                sell_weighted_average, sell_max_price, sell_min_price,
                sell_stddev, sell_median, sell_volume, sell_num_orders,
                sell_five_percent,
                custom_buy_price, custom_sell_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            price_records,
        )

    await repo.commit()
    logger.info(
        "Saved price snapshot %d with %d items and %d price records",
        snapshot_id,
        len(market_data),
        len(price_records),
    )

    if snapshot_id is None:
        raise RuntimeError("Failed to retrieve lastrowid for price snapshot.")
    return int(snapshot_id)


async def get_jita_prices(
    repo: Repository, type_id: int, limit: int = 100
) -> list[PriceHistory]:
    """Get historical Jita prices for a specific item type.

    Args:
        repo: Repository instance
        type_id: Item type ID
        limit: Maximum number of historical records to return

    Returns:
        List of PriceHistory models with buy and sell data
    """
    rows = await repo.fetchall(
        """
        SELECT
            price_id, type_id, region_id, snapshot_id,
            buy_weighted_average, buy_max_price, buy_min_price,
            buy_stddev, buy_median, buy_volume, buy_num_orders,
            buy_five_percent,
            sell_weighted_average, sell_max_price, sell_min_price,
            sell_stddev, sell_median, sell_volume, sell_num_orders,
            sell_five_percent
        FROM price_history
        WHERE type_id = ? AND region_id = ?
        ORDER BY snapshot_id DESC
        LIMIT ?
        """,
        (type_id, JITA_REGION_ID, limit),
    )

    return [PriceHistory(**dict(row)) for row in rows]


async def get_latest_jita_price(repo: Repository, type_id: int) -> PriceHistory | None:
    """Get the most recent Jita price for an item.

    Args:
        repo: Repository instance
        type_id: Item type ID

    Returns:
        Latest PriceHistory model or None if not found
    """
    row = await repo.fetchone(
        """
        SELECT
            price_id, type_id, region_id, snapshot_id,
            buy_weighted_average, buy_max_price, buy_min_price,
            buy_stddev, buy_median, buy_volume, buy_num_orders,
            buy_five_percent,
            sell_weighted_average, sell_max_price, sell_min_price,
            sell_stddev, sell_median, sell_volume, sell_num_orders,
            sell_five_percent
        FROM price_history
        WHERE type_id = ? AND region_id = ?
        ORDER BY snapshot_id DESC
        LIMIT 1
        """,
        (type_id, JITA_REGION_ID),
    )

    return PriceHistory(**dict(row)) if row else None


async def get_price_history(
    repo: Repository, type_id: int, region_id: int, limit: int = 100
) -> list[PriceHistory]:
    """Get historical prices for a specific item in any region.

    Args:
        repo: Repository instance
        type_id: Item type ID
        region_id: Region ID
        limit: Maximum number of historical records to return

    Returns:
        List of PriceHistory models
    """
    rows = await repo.fetchall(
        """
        SELECT
            price_id, type_id, region_id, snapshot_id,
            buy_weighted_average, buy_max_price, buy_min_price,
            buy_stddev, buy_median, buy_volume, buy_num_orders,
            buy_five_percent,
            sell_weighted_average, sell_max_price, sell_min_price,
            sell_stddev, sell_median, sell_volume, sell_num_orders,
            sell_five_percent
        FROM price_history
        WHERE type_id = ? AND region_id = ?
        ORDER BY snapshot_id DESC
        LIMIT ?
        """,
        (type_id, region_id, limit),
    )

    return [PriceHistory(**dict(row)) for row in rows]


async def get_snapshots(repo: Repository, limit: int = 50) -> list[PriceSnapshot]:
    """Get price snapshot history.

    Args:
        repo: Repository instance
        limit: Maximum number of snapshots to return

    Returns:
        List of PriceSnapshot models with metadata
    """
    rows = await repo.fetchall(
        """
        SELECT snapshot_id, snapshot_time, source, total_items, notes, snapshot_group_id
        FROM price_snapshots
        ORDER BY snapshot_time DESC
        LIMIT ?
        """,
        (limit,),
    )

    return [PriceSnapshot(**dict(row)) for row in rows]


async def get_items_with_history(repo: Repository) -> list[int]:
    """Get list of all item type IDs that have price history.

    Args:
        repo: Repository instance

    Returns:
        List of type IDs
    """
    rows = await repo.fetchall(
        """
        SELECT DISTINCT type_id
        FROM price_history
        ORDER BY type_id
        """
    )

    return [row["type_id"] for row in rows]


async def get_latest_snapshot_prices(
    repo: Repository,
    region_id: int = JITA_REGION_ID,
    price_type: str = "sell",
    weighted_buy_ratio: float = 0.3,
) -> dict[int, float]:
    """Load prices from latest snapshot, applying market preferences.

    This enables instant price loading at startup without waiting for Fuzzwork.
    Prices are loaded from the most recent price snapshot in the database,
    with market preferences (region, price type) applied.

    Args:
        repo: Repository instance
        region_id: Region ID (default: Jita)
        price_type: "buy", "sell", or "weighted"
        weighted_buy_ratio: Ratio for weighted price calculation (0.3 = 30% buy, 70% sell)

    Returns:
        Dictionary mapping type_id -> price (float)
    """
    # Get the latest snapshot_id
    snapshot_row = await repo.fetchone(
        """
        SELECT snapshot_id FROM price_snapshots
        ORDER BY snapshot_time DESC
        LIMIT 1
        """
    )

    if not snapshot_row:
        logger.debug("No price snapshots found in database")
        return {}

    snapshot_id = snapshot_row["snapshot_id"]

    # Fetch all prices from this snapshot for the target region
    rows = await repo.fetchall(
        """
        SELECT
            type_id,
            buy_weighted_average, buy_median, buy_max_price,
            sell_weighted_average, sell_median, sell_max_price,
            custom_buy_price, custom_sell_price
        FROM price_history
        WHERE snapshot_id = ? AND region_id = ?
        """,
        (snapshot_id, region_id),
    )

    prices: dict[int, float] = {}

    for row in rows:
        type_id = row["type_id"]
        price = None

        # Custom prices take precedence
        if row["custom_sell_price"] is not None:
            price = float(row["custom_sell_price"])
        elif row["custom_buy_price"] is not None:
            price = float(row["custom_buy_price"])
        # Then apply price_type preference
        elif price_type == "buy":
            candidates = [
                row["buy_median"],
                row["buy_weighted_average"],
                row["buy_max_price"],
            ]
            price = next(
                (float(v) for v in candidates if v is not None and v > 0), None
            )
        elif price_type == "sell":
            candidates = [
                row["sell_median"],
                row["sell_weighted_average"],
                row["sell_max_price"],
            ]
            price = next(
                (float(v) for v in candidates if v is not None and v > 0), None
            )
        elif price_type == "weighted":
            buy_price = None
            sell_price = None
            if row["buy_median"] is not None and row["buy_median"] > 0:
                buy_price = float(row["buy_median"])
            if row["sell_median"] is not None and row["sell_median"] > 0:
                sell_price = float(row["sell_median"])

            if buy_price and sell_price:
                price = (buy_price * weighted_buy_ratio) + (
                    sell_price * (1 - weighted_buy_ratio)
                )
            elif sell_price:
                price = sell_price
            elif buy_price:
                price = buy_price

        if price and price > 0:
            prices[type_id] = price

    logger.debug(
        "Loaded %d prices from snapshot %d (region %d, type=%s)",
        len(prices),
        snapshot_id,
        region_id,
        price_type,
    )

    return prices


async def delete_old_prices(repo: Repository, days: int = 90) -> int:
    """Delete price history older than specified days.

    Args:
        repo: Repository instance
        days: Number of days to keep

    Returns:
        Number of records deleted
    """
    cutoff = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    ) - timedelta(days=days)

    # Delete price_history rows that reference snapshots older than cutoff
    cursor = await repo.execute(
        """
        DELETE FROM price_history
        WHERE snapshot_id IN (
            SELECT snapshot_id FROM price_snapshots WHERE snapshot_time < ?
        )
        """,
        (cutoff.isoformat(),),
    )

    deleted_count = cursor.rowcount

    # Also remove the old snapshot records themselves
    await repo.execute(
        """
        DELETE FROM price_snapshots WHERE snapshot_time < ?
        """,
        (cutoff.isoformat(),),
    )

    await repo.commit()

    logger.info("Deleted %d price records older than %d days", deleted_count, days)

    return deleted_count


__all__ = [
    "JITA_REGION_ID",
    "delete_old_prices",
    "get_items_with_history",
    "get_jita_prices",
    "get_latest_jita_price",
    "get_latest_snapshot_prices",
    "get_price_history",
    "get_snapshots",
    "save_snapshot",
]
