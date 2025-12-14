"""Repository functions for character lifecycle tracking.

This module provides functions for storing and querying character lifecycle events
such as when characters are added, removed, or moved between accounts.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_lifecycle_event(
    repo: Repository,
    character_id: int,
    event_type: str,
    account_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    event_time: datetime | None = None,
) -> int:
    """Save a character lifecycle event.

    Args:
        repo: Repository instance
        character_id: Character ID
        event_type: Type of event ('added', 'removed', 'account_changed')
        account_id: Optional account ID (set for 'added' and 'account_changed')
        metadata: Optional JSON metadata dict
        event_time: Optional event timestamp (defaults to now)

    Returns:
        lifecycle_id of the created event
    """
    if event_type not in ("added", "removed", "account_changed"):
        raise ValueError(f"Invalid event_type: {event_type}")

    if event_time is None:
        event_time = datetime.now(datetime.now().astimezone().tzinfo)

    metadata_json = json.dumps(metadata) if metadata else None

    cursor = await repo.execute(
        """
        INSERT INTO character_lifecycle (
            character_id, account_id, event_type, event_time, metadata
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            character_id,
            account_id,
            event_type,
            event_time.isoformat(),
            metadata_json,
        ),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for lifecycle event.")
    lifecycle_id = int(cursor.lastrowid)
    await repo.commit()
    logger.info(
        "Saved lifecycle event %d: character %d %s",
        lifecycle_id,
        character_id,
        event_type,
    )
    return lifecycle_id


async def get_character_lifecycle(repo: Repository, character_id: int) -> list[dict]:
    """Get all lifecycle events for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        List of lifecycle events ordered by time
    """
    rows = await repo.fetchall(
        """
        SELECT
            lifecycle_id, character_id, account_id, event_type, event_time, metadata
        FROM character_lifecycle
        WHERE character_id = ?
        ORDER BY event_time ASC
        """,
        (character_id,),
    )

    return [dict(row) for row in rows]


async def get_character_added_time(
    repo: Repository, character_id: int
) -> datetime | None:
    """Get the time when a character was added.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        datetime of when character was added, or None if not found
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
        # Parse ISO format timestamp
        timestamp_str = row["event_time"]
        return datetime.fromisoformat(timestamp_str)
    return None


async def get_character_removed_time(
    repo: Repository, character_id: int
) -> datetime | None:
    """Get the time when a character was removed.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        datetime of when character was removed, or None if not removed
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
        # Parse ISO format timestamp
        timestamp_str = row["event_time"]
        return datetime.fromisoformat(timestamp_str)
    return None


async def get_active_characters_at_time(
    repo: Repository, target_time: datetime, character_ids: list[int] | None = None
) -> list[int]:
    """Get list of characters that were active at a specific time.

    A character is active at a time if:
    - It was added before or at the target time
    - It was not removed, OR was removed after the target time

    Args:
        repo: Repository instance
        target_time: Target timestamp
        character_ids: Optional list of character IDs to check (None = all)

    Returns:
        List of character IDs that were active at target_time
    """
    target_iso = target_time.isoformat()
    char_filter = ""
    params: list[object] = [target_iso]

    if character_ids:
        placeholders = ",".join("?" for _ in character_ids)
        char_filter = f"AND c.character_id IN ({placeholders})"
        params.extend(character_ids)

    rows = await repo.fetchall(
        f"""
        SELECT DISTINCT c.character_id
        FROM (
            SELECT DISTINCT character_id FROM character_lifecycle
        ) c
        WHERE 1=1
            -- Character must have been added by target_time
            AND EXISTS (
                SELECT 1 FROM character_lifecycle cl1
                WHERE cl1.character_id = c.character_id
                AND cl1.event_type = 'added'
                AND cl1.event_time <= ?
            )
            -- Character must NOT be removed at target_time (or removed after)
            AND NOT EXISTS (
                SELECT 1 FROM character_lifecycle cl2
                WHERE cl2.character_id = c.character_id
                AND cl2.event_type = 'removed'
                AND cl2.event_time <= ?
            )
            {char_filter}
        """,
        tuple([target_iso, target_iso] + params),
    )

    return [int(row["character_id"]) for row in rows]


__all__ = [
    "get_active_characters_at_time",
    "get_character_added_time",
    "get_character_lifecycle",
    "get_character_removed_time",
    "save_lifecycle_event",
]
