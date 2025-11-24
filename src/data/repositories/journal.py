"""Repository functions for wallet journal entries.

This module provides functions for storing and querying wallet journal
history for characters.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from models.eve import EveJournalEntry

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_journal_entries(
    repo: Repository, character_id: int, entries: list[EveJournalEntry]
) -> int:
    """Save wallet journal entries for a character.

    Uses INSERT OR REPLACE to handle incremental appending without creating duplicates.
    Since entry_id is unique, existing entries are updated rather than duplicated.
    This allows safe repeated syncing of overlapping journal history.

    Args:
        repo: Repository instance
        character_id: Character ID
        entries: List of journal entries to save

    Returns:
        Number of entries saved (new + updated)
    """
    if not entries:
        return 0

    # Use INSERT OR REPLACE to handle duplicates
    # entry_id is PRIMARY KEY, so duplicates are automatically replaced
    sql = """
    INSERT OR REPLACE INTO wallet_journal (
        entry_id, character_id, date, ref_type, first_party_id, second_party_id,
        amount, balance, reason, description, context_id, context_id_type
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params = [
        (
            entry.id,
            character_id,
            entry.date,
            entry.ref_type,
            entry.first_party_id,
            entry.second_party_id,
            entry.amount,
            entry.balance,
            entry.reason,
            entry.description,
            entry.context_id,
            entry.context_id_type,
        )
        for entry in entries
    ]

    await repo.executemany(sql, params)
    logger.info("Saved %d journal entries for character %d", len(entries), character_id)
    return len(entries)


async def get_journal_entries(
    repo: Repository, character_id: int, limit: int = 100
) -> list[EveJournalEntry]:
    """Get recent wallet journal entries for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        limit: Maximum number of entries to return

    Returns:
        List of journal entries, most recent first
    """
    sql = """
    SELECT entry_id, date, ref_type, first_party_id, second_party_id,
           amount, balance, reason, description, context_id, context_id_type
    FROM wallet_journal
    WHERE character_id = ?
    ORDER BY date DESC
    LIMIT ?
    """

    rows = await repo.fetchall(sql, (character_id, limit))
    return [
        EveJournalEntry(
            entry_id=row["entry_id"],
            date=datetime.fromisoformat(row["date"]),
            ref_type=row["ref_type"],
            first_party_id=row["first_party_id"],
            second_party_id=row["second_party_id"],
            amount=row["amount"],
            balance=row["balance"],
            reason=row["reason"],
            description=row["description"],
            context_id=row["context_id"],
            context_id_type=row["context_id_type"],
        )
        for row in rows
    ]


async def get_latest_journal_date(
    repo: Repository, character_id: int
) -> datetime | None:
    """Get the date of the most recent journal entry for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Date of most recent entry, or None if no entries
    """
    sql = """
    SELECT MAX(date) as latest_date
    FROM wallet_journal
    WHERE character_id = ?
    """

    row = await repo.fetchone(sql, (character_id,))
    if row and row["latest_date"]:
        return datetime.fromisoformat(row["latest_date"])
    return None


async def get_entries_by_type(
    repo: Repository, character_id: int, ref_type: str
) -> list[EveJournalEntry]:
    """Get all journal entries of a specific type.

    Args:
        repo: Repository instance
        character_id: Character ID
        ref_type: Reference type (e.g., 'bounty_prizes', 'market_transaction')

    Returns:
        List of journal entries of the specified type
    """
    sql = """
    SELECT entry_id, date, ref_type, first_party_id, second_party_id,
           amount, balance, reason, description, context_id, context_id_type
    FROM wallet_journal
    WHERE character_id = ? AND ref_type = ?
    ORDER BY date DESC
    """

    rows = await repo.fetchall(sql, (character_id, ref_type))
    return [
        EveJournalEntry(
            entry_id=row["entry_id"],
            date=datetime.fromisoformat(row["date"]),
            ref_type=row["ref_type"],
            first_party_id=row["first_party_id"],
            second_party_id=row["second_party_id"],
            amount=row["amount"],
            balance=row["balance"],
            reason=row["reason"],
            description=row["description"],
            context_id=row["context_id"],
            context_id_type=row["context_id_type"],
        )
        for row in rows
    ]


async def get_balance_history(
    repo: Repository, character_id: int, days: int = 30
) -> list[tuple[datetime, float]]:
    """Get wallet balance history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        days: Number of days to look back

    Returns:
        List of (datetime, balance) tuples
    """
    sql = """
    SELECT date, balance
    FROM wallet_journal
    WHERE character_id = ? AND date >= datetime('now', '-' || ? || ' days')
    ORDER BY date ASC
    """

    rows = await repo.fetchall(sql, (character_id, days))
    return [(datetime.fromisoformat(row["date"]), row["balance"]) for row in rows]


async def get_current_balance(repo: Repository, character_id: int) -> float | None:
    """Get the current wallet balance from the most recent journal entry.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Most recent balance from journal, or None if no entries exist
    """
    sql = """
    SELECT balance
    FROM wallet_journal
    WHERE character_id = ?
    ORDER BY date DESC
    LIMIT 1
    """

    row = await repo.fetchone(sql, (character_id,))
    return float(row["balance"]) if row else None


__all__ = [
    "get_balance_history",
    "get_current_balance",
    "get_entries_by_type",
    "get_journal_entries",
    "get_latest_journal_date",
    "save_journal_entries",
]
