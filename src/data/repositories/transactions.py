"""Repository functions for wallet transactions.

This module provides functions for storing and querying wallet transaction
history for characters.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from models.eve import EveTransaction

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_transactions(
    repo: Repository, character_id: int, transactions: list[EveTransaction]
) -> int:
    """Save wallet transactions for a character.

    Uses INSERT OR REPLACE to handle incremental appending without creating duplicates.
    Since transaction_id is unique, existing transactions are updated rather than duplicated.
    This allows safe repeated syncing of overlapping transaction history.

    Args:
        repo: Repository instance
        character_id: Character ID
        transactions: List of transactions to save

    Returns:
        Number of transactions saved (new + updated)
    """
    if not transactions:
        return 0

    # Use INSERT OR REPLACE to handle duplicates
    # transaction_id is PRIMARY KEY, so duplicates are automatically replaced
    sql = """
    INSERT OR REPLACE INTO wallet_transactions (
        transaction_id, character_id, date, type_id, quantity, unit_price,
        client_id, location_id, is_buy, is_personal, journal_ref_id
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params = [
        (
            tx.transaction_id,
            character_id,
            tx.date,
            tx.type_id,
            tx.quantity,
            tx.unit_price,
            tx.client_id,
            tx.location_id,
            1 if tx.is_buy else 0,
            1 if tx.is_personal else 0,
            tx.journal_ref_id,
        )
        for tx in transactions
    ]

    await repo.executemany(sql, params)
    logger.info(
        "Saved %d transactions for character %d", len(transactions), character_id
    )
    return len(transactions)


async def get_transactions(
    repo: Repository, character_id: int, limit: int = 100
) -> list[EveTransaction]:
    """Get recent wallet transactions for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        limit: Maximum number of transactions to return

    Returns:
        List of transactions, most recent first
    """
    sql = """
    SELECT transaction_id, date, type_id, quantity, unit_price, client_id,
           location_id, is_buy, is_personal, journal_ref_id
    FROM wallet_transactions
    WHERE character_id = ?
    ORDER BY date DESC
    LIMIT ?
    """

    rows = await repo.fetchall(sql, (character_id, limit))
    return [
        EveTransaction(
            transaction_id=row["transaction_id"],
            date=datetime.fromisoformat(row["date"]),
            type_id=row["type_id"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            client_id=row["client_id"],
            location_id=row["location_id"],
            is_buy=bool(row["is_buy"]),
            is_personal=bool(row["is_personal"]),
            journal_ref_id=row["journal_ref_id"],
        )
        for row in rows
    ]


async def get_latest_transaction_date(
    repo: Repository, character_id: int
) -> datetime | None:
    """Get the date of the most recent transaction for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Date of most recent transaction, or None if no transactions
    """
    sql = """
    SELECT MAX(date) as latest_date
    FROM wallet_transactions
    WHERE character_id = ?
    """

    row = await repo.fetchone(sql, (character_id,))
    if row and row["latest_date"]:
        return datetime.fromisoformat(row["latest_date"])
    return None


async def get_transactions_by_type(
    repo: Repository, character_id: int, type_id: int
) -> list[EveTransaction]:
    """Get all transactions for a specific item type.

    Args:
        repo: Repository instance
        character_id: Character ID
        type_id: Item type ID

    Returns:
        List of transactions for the specified type
    """
    sql = """
    SELECT transaction_id, date, type_id, quantity, unit_price, client_id,
           location_id, is_buy, is_personal, journal_ref_id
    FROM wallet_transactions
    WHERE character_id = ? AND type_id = ?
    ORDER BY date DESC
    """

    rows = await repo.fetchall(sql, (character_id, type_id))
    return [
        EveTransaction(
            transaction_id=row["transaction_id"],
            date=datetime.fromisoformat(row["date"]),
            type_id=row["type_id"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            client_id=row["client_id"],
            location_id=row["location_id"],
            is_buy=bool(row["is_buy"]),
            is_personal=bool(row["is_personal"]),
            journal_ref_id=row["journal_ref_id"],
        )
        for row in rows
    ]


async def get_transaction_count(repo: Repository, character_id: int) -> int:
    """Get total number of transactions for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Total transaction count
    """
    sql = """
    SELECT COUNT(*) as count
    FROM wallet_transactions
    WHERE character_id = ?
    """

    row = await repo.fetchone(sql, (character_id,))
    return row["count"] if row else 0


__all__ = [
    "get_latest_transaction_date",
    "get_transaction_count",
    "get_transactions",
    "get_transactions_by_type",
    "save_transactions",
]
