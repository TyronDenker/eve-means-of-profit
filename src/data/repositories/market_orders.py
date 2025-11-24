"""Repository functions for market orders.

This module provides functions for storing and querying market order
information for characters.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from models.eve import EveMarketOrder

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_orders(
    repo: Repository, character_id: int, orders: list[EveMarketOrder]
) -> int:
    """Save market orders for a character.

    Uses INSERT OR REPLACE to keep only the latest status per order_id.
    This ensures we always have the most recent state of each order without duplicates.

    Args:
        repo: Repository instance
        character_id: Character ID
        orders: List of orders to save

    Returns:
        Number of orders saved
    """
    if not orders:
        return 0

    # Use INSERT OR REPLACE to handle updates - keeps only latest status per order_id
    # Since order_id is PRIMARY KEY, this automatically replaces old records
    sql = """
    INSERT OR REPLACE INTO market_orders (
        order_id, character_id, type_id, location_id, volume_total, volume_remain,
        min_volume, price, is_buy_order, duration, issued, range, state,
        region_id, is_corporation, escrow, last_updated
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    now = datetime.now(UTC)
    params = [
        (
            order.order_id,
            character_id,
            order.type_id,
            order.location_id,
            order.volume_total,
            order.volume_remain,
            order.min_volume,
            order.price,
            1 if order.is_buy_order else 0,
            order.duration,
            order.issued,
            order.range,
            order.state,  # Latest state stored here
            order.region_id,
            1 if order.is_corporation else 0,
            order.escrow,
            now,
        )
        for order in orders
    ]

    await repo.executemany(sql, params)
    logger.info(
        "Saved %d orders for character %d (latest status per order)",
        len(orders),
        character_id,
    )
    return len(orders)


async def get_active_orders(
    repo: Repository, character_id: int
) -> list[EveMarketOrder]:
    """Get active market orders for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        List of active market orders
    """
    sql = """
    SELECT order_id, type_id, location_id, volume_total, volume_remain,
           min_volume, price, is_buy_order, duration, issued, range, state,
           region_id, is_corporation, escrow
    FROM market_orders
    WHERE character_id = ? AND state = 'active'
    ORDER BY issued DESC
    """

    rows = await repo.fetchall(sql, (character_id,))
    return [
        EveMarketOrder(
            order_id=row["order_id"],
            type_id=row["type_id"],
            location_id=row["location_id"],
            volume_total=row["volume_total"],
            volume_remain=row["volume_remain"],
            min_volume=row["min_volume"],
            price=row["price"],
            is_buy_order=bool(row["is_buy_order"]),
            duration=row["duration"],
            issued=datetime.fromisoformat(row["issued"]),
            range=row["range"],
            state=row["state"],
            region_id=row["region_id"],
            is_corporation=bool(row["is_corporation"]),
            escrow=row["escrow"],
        )
        for row in rows
    ]


async def get_orders_by_type(
    repo: Repository, character_id: int, type_id: int
) -> list[EveMarketOrder]:
    """Get all orders for a specific item type.

    Args:
        repo: Repository instance
        character_id: Character ID
        type_id: Item type ID

    Returns:
        List of orders for the specified type
    """
    sql = """
    SELECT order_id, type_id, location_id, volume_total, volume_remain,
           min_volume, price, is_buy_order, duration, issued, range, state,
           region_id, is_corporation, escrow
    FROM market_orders
    WHERE character_id = ? AND type_id = ?
    ORDER BY issued DESC
    """

    rows = await repo.fetchall(sql, (character_id, type_id))
    return [
        EveMarketOrder(
            order_id=row["order_id"],
            type_id=row["type_id"],
            location_id=row["location_id"],
            volume_total=row["volume_total"],
            volume_remain=row["volume_remain"],
            min_volume=row["min_volume"],
            price=row["price"],
            is_buy_order=bool(row["is_buy_order"]),
            duration=row["duration"],
            issued=datetime.fromisoformat(row["issued"]),
            range=row["range"],
            state=row["state"],
            region_id=row["region_id"],
            is_corporation=bool(row["is_corporation"]),
            escrow=row["escrow"],
        )
        for row in rows
    ]


async def get_order_history(
    repo: Repository, character_id: int, limit: int = 100
) -> list[EveMarketOrder]:
    """Get order history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        limit: Maximum number of orders to return

    Returns:
        List of orders, most recent first
    """
    sql = """
    SELECT order_id, type_id, location_id, volume_total, volume_remain,
           min_volume, price, is_buy_order, duration, issued, range, state,
           region_id, is_corporation, escrow
    FROM market_orders
    WHERE character_id = ?
    ORDER BY issued DESC
    LIMIT ?
    """

    rows = await repo.fetchall(sql, (character_id, limit))
    return [
        EveMarketOrder(
            order_id=row["order_id"],
            type_id=row["type_id"],
            location_id=row["location_id"],
            volume_total=row["volume_total"],
            volume_remain=row["volume_remain"],
            min_volume=row["min_volume"],
            price=row["price"],
            is_buy_order=bool(row["is_buy_order"]),
            duration=row["duration"],
            issued=datetime.fromisoformat(row["issued"]),
            range=row["range"],
            state=row["state"],
            region_id=row["region_id"],
            is_corporation=bool(row["is_corporation"]),
            escrow=row["escrow"],
        )
        for row in rows
    ]


async def calculate_market_exposure(repo: Repository, character_id: int) -> dict:
    """Calculate total ISK exposure in market orders.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Dictionary with exposure statistics
    """
    sql = """
    SELECT
        SUM(CASE WHEN is_buy_order = 1 THEN volume_remain * price ELSE 0 END) as buy_exposure,
        SUM(CASE WHEN is_buy_order = 0 THEN volume_remain * price ELSE 0 END) as sell_exposure,
        SUM(CASE WHEN escrow IS NOT NULL THEN escrow ELSE 0 END) as total_escrow,
        COUNT(*) as total_orders
    FROM market_orders
    WHERE character_id = ? AND state = 'active'
    """

    row = await repo.fetchone(sql, (character_id,))
    if row:
        return {
            "buy_exposure": row["buy_exposure"] or 0.0,
            "sell_exposure": row["sell_exposure"] or 0.0,
            "total_escrow": row["total_escrow"] or 0.0,
            "total_orders": row["total_orders"] or 0,
        }
    return {
        "buy_exposure": 0.0,
        "sell_exposure": 0.0,
        "total_escrow": 0.0,
        "total_orders": 0,
    }


__all__ = [
    "calculate_market_exposure",
    "get_active_orders",
    "get_order_history",
    "get_orders_by_type",
    "save_orders",
]
