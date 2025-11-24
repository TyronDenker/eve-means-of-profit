"""Repository functions for contracts.

This module provides functions for storing and querying contract
information for characters.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from models.eve import EveContract, EveContractItem

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_contracts(
    repo: Repository, character_id: int, contracts: list[EveContract]
) -> int:
    """Save contracts for a character.

    Uses INSERT OR REPLACE to handle incremental appending without creating duplicates.
    Since contract_id is unique, existing contracts are updated with their latest status.
    This ensures we always have the current state of each contract (outstanding, completed, etc.).

    Args:
        repo: Repository instance
        character_id: Character ID
        contracts: List of contracts to save

    Returns:
        Number of contracts saved (new + updated)
    """
    if not contracts:
        return 0

    # Use INSERT OR REPLACE to handle updates
    # contract_id is PRIMARY KEY, so duplicates are automatically replaced with latest status
    sql = """
    INSERT OR REPLACE INTO contracts (
        contract_id, character_id, issuer_id, issuer_corporation_id, assignee_id,
        acceptor_id, start_location_id, end_location_id, type, status, title,
        for_corporation, availability, date_issued, date_expired, date_accepted,
        date_completed, days_to_complete, price, reward, collateral, buyout, volume
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    params = [
        (
            contract.contract_id,
            character_id,
            contract.issuer_id,
            contract.issuer_corporation_id,
            contract.assignee_id,
            contract.acceptor_id,
            contract.start_location_id,
            contract.end_location_id,
            contract.type,
            contract.status,
            contract.title,
            1 if contract.for_corporation else 0,
            contract.availability,
            contract.date_issued,
            contract.date_expired,
            contract.date_accepted,
            contract.date_completed,
            contract.days_to_complete,
            contract.price,
            contract.reward,
            contract.collateral,
            contract.buyout,
            contract.volume,
        )
        for contract in contracts
    ]

    await repo.executemany(sql, params)
    logger.info("Saved %d contracts for character %d", len(contracts), character_id)
    return len(contracts)


async def save_contract_items(
    repo: Repository, contract_id: int, items: list[EveContractItem]
) -> int:
    """Save items for a specific contract.

    Args:
        repo: Repository instance
        contract_id: Contract ID
        items: List of contract items to save

    Returns:
        Number of items saved
    """
    if not items:
        return 0

    # Use INSERT OR REPLACE to handle updates
    sql = """
    INSERT OR REPLACE INTO contract_items (
        record_id, contract_id, type_id, quantity, is_included, is_singleton
    ) VALUES (?, ?, ?, ?, ?, ?)
    """

    params = [
        (
            item.record_id,
            contract_id,
            item.type_id,
            item.quantity,
            1 if item.is_included else 0,
            1 if item.is_singleton else 0,
        )
        for item in items
    ]

    await repo.executemany(sql, params)
    logger.info("Saved %d items for contract %d", len(items), contract_id)
    return len(items)


async def get_contracts(
    repo: Repository, character_id: int, status: str | None = None
) -> list[EveContract]:
    """Get contracts for a character, optionally filtered by status.

    Args:
        repo: Repository instance
        character_id: Character ID
        status: Optional status filter (outstanding, in_progress, finished, etc.)

    Returns:
        List of contracts
    """
    if status:
        sql = """
        SELECT contract_id, issuer_id, issuer_corporation_id, assignee_id,
               acceptor_id, start_location_id, end_location_id, type, status, title,
               for_corporation, availability, date_issued, date_expired, date_accepted,
               date_completed, days_to_complete, price, reward, collateral, buyout, volume
        FROM contracts
        WHERE character_id = ? AND status = ?
        ORDER BY date_issued DESC
        """
        rows = await repo.fetchall(sql, (character_id, status))
    else:
        sql = """
        SELECT contract_id, issuer_id, issuer_corporation_id, assignee_id,
               acceptor_id, start_location_id, end_location_id, type, status, title,
               for_corporation, availability, date_issued, date_expired, date_accepted,
               date_completed, days_to_complete, price, reward, collateral, buyout, volume
        FROM contracts
        WHERE character_id = ?
        ORDER BY date_issued DESC
        """
        rows = await repo.fetchall(sql, (character_id,))

    return [
        EveContract(
            contract_id=row["contract_id"],
            issuer_id=row["issuer_id"],
            issuer_corporation_id=row["issuer_corporation_id"],
            assignee_id=row["assignee_id"],
            acceptor_id=row["acceptor_id"],
            start_location_id=row["start_location_id"],
            end_location_id=row["end_location_id"],
            type=row["type"],
            status=row["status"],
            title=row["title"],
            for_corporation=bool(row["for_corporation"]),
            availability=row["availability"],
            date_issued=datetime.fromisoformat(row["date_issued"]),
            date_expired=datetime.fromisoformat(row["date_expired"]),
            date_accepted=datetime.fromisoformat(row["date_accepted"])
            if row["date_accepted"]
            else None,
            date_completed=datetime.fromisoformat(row["date_completed"])
            if row["date_completed"]
            else None,
            days_to_complete=row["days_to_complete"],
            price=row["price"],
            reward=row["reward"],
            collateral=row["collateral"],
            buyout=row["buyout"],
            volume=row["volume"],
        )
        for row in rows
    ]


async def get_contract_items(
    repo: Repository, contract_id: int
) -> list[EveContractItem]:
    """Get items for a specific contract.

    Args:
        repo: Repository instance
        contract_id: Contract ID

    Returns:
        List of contract items
    """
    sql = """
    SELECT record_id, contract_id, type_id, quantity, is_included, is_singleton
    FROM contract_items
    WHERE contract_id = ?
    """

    rows = await repo.fetchall(sql, (contract_id,))
    return [
        EveContractItem(
            record_id=row["record_id"],
            contract_id=row["contract_id"],
            type_id=row["type_id"],
            quantity=row["quantity"],
            is_included=bool(row["is_included"]),
            is_singleton=bool(row["is_singleton"]),
        )
        for row in rows
    ]


async def get_active_contracts(
    repo: Repository, character_id: int
) -> list[EveContract]:
    """Get active (outstanding or in_progress) contracts for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        List of active contracts
    """
    sql = """
    SELECT contract_id, issuer_id, issuer_corporation_id, assignee_id,
           acceptor_id, start_location_id, end_location_id, type, status, title,
           for_corporation, availability, date_issued, date_expired, date_accepted,
           date_completed, days_to_complete, price, reward, collateral, buyout, volume
    FROM contracts
    WHERE character_id = ? AND status IN ('outstanding', 'in_progress')
    ORDER BY date_issued DESC
    """

    rows = await repo.fetchall(sql, (character_id,))
    return [
        EveContract(
            contract_id=row["contract_id"],
            issuer_id=row["issuer_id"],
            issuer_corporation_id=row["issuer_corporation_id"],
            assignee_id=row["assignee_id"],
            acceptor_id=row["acceptor_id"],
            start_location_id=row["start_location_id"],
            end_location_id=row["end_location_id"],
            type=row["type"],
            status=row["status"],
            title=row["title"],
            for_corporation=bool(row["for_corporation"]),
            availability=row["availability"],
            date_issued=datetime.fromisoformat(row["date_issued"]),
            date_expired=datetime.fromisoformat(row["date_expired"]),
            date_accepted=datetime.fromisoformat(row["date_accepted"])
            if row["date_accepted"]
            else None,
            date_completed=datetime.fromisoformat(row["date_completed"])
            if row["date_completed"]
            else None,
            days_to_complete=row["days_to_complete"],
            price=row["price"],
            reward=row["reward"],
            collateral=row["collateral"],
            buyout=row["buyout"],
            volume=row["volume"],
        )
        for row in rows
    ]


__all__ = [
    "get_active_contracts",
    "get_contract_items",
    "get_contracts",
    "save_contract_items",
    "save_contracts",
]
