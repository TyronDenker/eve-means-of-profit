"""Asset data access methods.

This module provides functions for accessing and managing asset data
through the unified Repository. All functions accept a Repository instance
as their first parameter.

Functions:
    - save_snapshot: Save a new asset snapshot and track changes
    - get_current_assets: Get current assets for a character
    - get_history: Get asset change history
    - get_snapshots: Get snapshot metadata history
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from models.app import AssetChange, AssetSnapshot
from models.eve import EveAsset

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


class _AssetChangeDelta:
    """Internal class for computing asset changes before DB insertion."""

    def __init__(
        self,
        item_id: int,
        type_id: int,
        change_type: str,
        old_quantity: int | None = None,
        new_quantity: int | None = None,
        old_location_id: int | None = None,
        new_location_id: int | None = None,
        old_location_flag: str | None = None,
        new_location_flag: str | None = None,
    ):
        self.item_id = item_id
        self.type_id = type_id
        self.change_type = change_type
        self.old_quantity = old_quantity
        self.new_quantity = new_quantity
        self.old_location_id = old_location_id
        self.new_location_id = new_location_id
        self.old_location_flag = old_location_flag
        self.new_location_flag = new_location_flag


async def save_snapshot(
    repo: Repository,
    character_id: int,
    assets: list[EveAsset],
    notes: str | None = None,
) -> int:
    """Save a new asset snapshot and compute changes.

    This function:
    1. Creates a new snapshot record
    2. Compares with current assets to find changes
    3. Records the changes (delta)
    4. Updates current assets to match new snapshot

    Args:
        repo: Repository instance
        character_id: Character ID owning the assets
        assets: List of assets in this snapshot
        notes: Optional notes about this snapshot

    Returns:
        snapshot_id of the created snapshot
    """
    snapshot_time = datetime.now(UTC)

    # Create snapshot record
    cursor = await repo.execute(
        """
        INSERT INTO asset_snapshots (character_id, snapshot_time, total_items, notes)
        VALUES (?, ?, ?, ?)
        """,
        (character_id, snapshot_time.isoformat(), len(assets), notes),
    )
    if cursor.lastrowid is None:
        raise RuntimeError("Failed to retrieve lastrowid for asset snapshot.")
    snapshot_id = int(cursor.lastrowid)

    # Get current assets for comparison
    current_assets = await _get_current_assets_dict(repo, character_id)

    # Compute changes
    changes = _compute_changes(current_assets, assets)

    # Save changes
    if changes:
        await _save_changes(repo, snapshot_id, character_id, changes)

    # Update current assets
    await _update_current_assets(repo, character_id, assets, snapshot_time)

    await repo.commit()
    logger.info(
        "Saved asset snapshot %d for character %d with %d items and %d changes",
        snapshot_id,
        character_id,
        len(assets),
        len(changes),
    )

    return int(snapshot_id)


async def get_current_assets(repo: Repository, character_id: int) -> list[EveAsset]:
    """Get current assets for a character, excluding removed assets.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        List of current assets
    """
    # Check if removed_at column exists before filtering on it
    try:
        table_info = await repo.get_table_info("current_assets")
        has_removed_at = any(
            col[1] == "removed_at"
            if isinstance(col, tuple)
            else col.get("name") == "removed_at"
            for col in table_info
        )
    except Exception:
        has_removed_at = False

    # Build query based on whether removed_at column exists
    if has_removed_at:
        where_clause = (
            "WHERE character_id = ? AND (removed_at IS NULL OR removed_at = '')"
        )
    else:
        where_clause = "WHERE character_id = ?"

    rows = await repo.fetchall(
        f"""
        SELECT item_id, type_id, quantity, location_id, location_type,
               location_flag, is_singleton, is_blueprint_copy
        FROM current_assets
        {where_clause}
        """,
        (character_id,),
    )

    return [
        EveAsset(
            item_id=row["item_id"],
            type_id=row["type_id"],
            quantity=row["quantity"],
            location_id=row["location_id"],
            location_type=row["location_type"],
            location_flag=row["location_flag"],
            is_singleton=bool(row["is_singleton"]),
            is_blueprint_copy=(
                bool(row["is_blueprint_copy"])
                if row["is_blueprint_copy"] is not None
                else None
            ),
        )
        for row in rows
    ]


async def get_history(
    repo: Repository,
    character_id: int,
    type_id: int | None = None,
    limit: int = 100,
) -> list[AssetChange]:
    """Get asset change history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        type_id: Optional type ID to filter by
        limit: Maximum number of changes to return

    Returns:
        List of AssetChange models with snapshot information
    """
    if type_id is not None:
        rows = await repo.fetchall(
            """
            SELECT
                ac.change_id, ac.snapshot_id, ac.item_id, ac.type_id,
                ac.change_type, ac.old_quantity, ac.new_quantity,
                ac.old_location_id, ac.new_location_id,
                ac.old_location_flag, ac.new_location_flag,
                ac.change_time, asn.snapshot_time
            FROM asset_changes ac
            JOIN asset_snapshots asn ON ac.snapshot_id = asn.snapshot_id
            WHERE ac.character_id = ? AND ac.type_id = ?
            ORDER BY ac.change_time DESC
            LIMIT ?
            """,
            (character_id, type_id, limit),
        )
    else:
        rows = await repo.fetchall(
            """
            SELECT
                ac.change_id, ac.snapshot_id, ac.item_id, ac.type_id,
                ac.change_type, ac.old_quantity, ac.new_quantity,
                ac.old_location_id, ac.new_location_id,
                ac.old_location_flag, ac.new_location_flag,
                ac.change_time, asn.snapshot_time
            FROM asset_changes ac
            JOIN asset_snapshots asn ON ac.snapshot_id = asn.snapshot_id
            WHERE ac.character_id = ?
            ORDER BY ac.change_time DESC
            LIMIT ?
            """,
            (character_id, limit),
        )

    return [AssetChange(**dict(row)) for row in rows]


async def get_snapshots(
    repo: Repository, character_id: int, limit: int = 50
) -> list[AssetSnapshot]:
    """Get snapshot history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        limit: Maximum number of snapshots to return

    Returns:
        List of AssetSnapshot models with metadata
    """
    rows = await repo.fetchall(
        """
        SELECT snapshot_id, character_id, snapshot_time, total_items, notes
        FROM asset_snapshots
        WHERE character_id = ?
        ORDER BY snapshot_time DESC
        LIMIT ?
        """,
        (character_id, limit),
    )

    return [AssetSnapshot(**dict(row)) for row in rows]


async def update_current_assets(
    repo: Repository, character_id: int, assets: list[EveAsset]
) -> None:
    """Update current assets without creating a snapshot.

    This function updates the current_assets table with fresh data
    from ESI during refresh operations. Unlike save_snapshot(), this
    does NOT create a snapshot or track changes - it just updates
    the current state.

    Args:
        repo: Repository instance
        character_id: Character ID
        assets: List of current assets
    """
    timestamp = datetime.now(UTC)
    await _update_current_assets(repo, character_id, assets, timestamp)
    logger.info(
        "Updated current_assets for character %d with %d assets",
        character_id,
        len(assets),
    )


async def _get_current_assets_dict(
    repo: Repository, character_id: int
) -> dict[int, dict[str, Any]]:
    """Get current assets for a character as a dictionary.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Dict mapping item_id to asset data
    """
    rows = await repo.fetchall(
        """
        SELECT item_id, type_id, quantity, location_id, location_type,
               location_flag, is_singleton, is_blueprint_copy
        FROM current_assets
        WHERE character_id = ?
        """,
        (character_id,),
    )

    return {
        row["item_id"]: {
            "type_id": row["type_id"],
            "quantity": row["quantity"],
            "location_id": row["location_id"],
            "location_type": row["location_type"],
            "location_flag": row["location_flag"],
            "is_singleton": bool(row["is_singleton"]),
            "is_blueprint_copy": (
                bool(row["is_blueprint_copy"])
                if row["is_blueprint_copy"] is not None
                else None
            ),
        }
        for row in rows
    }


def _compute_changes(
    current: dict[int, dict[str, Any]], new_assets: list[EveAsset]
) -> list[_AssetChangeDelta]:
    """Compute changes between current and new assets.

    Args:
        current: Current assets dict (item_id -> asset data)
        new_assets: New asset list

    Returns:
        List of changes detected
    """
    changes: list[_AssetChangeDelta] = []
    new_assets_dict = {asset.item_id: asset for asset in new_assets}

    # If current is empty (first snapshot), all new assets are 'added'
    if not current:
        for asset in new_assets:
            changes.append(
                _AssetChangeDelta(
                    item_id=asset.item_id,
                    type_id=asset.type_id,
                    change_type="added",
                    new_quantity=asset.quantity,
                    new_location_id=asset.location_id,
                    new_location_flag=asset.location_flag,
                )
            )
        return changes

    # Find removed and modified assets
    for item_id, old_data in current.items():
        if item_id not in new_assets_dict:
            # Asset removed
            changes.append(
                _AssetChangeDelta(
                    item_id=item_id,
                    type_id=old_data["type_id"],
                    change_type="removed",
                    old_quantity=old_data["quantity"],
                    old_location_id=old_data["location_id"],
                    old_location_flag=old_data["location_flag"],
                )
            )
        else:
            # Check for modifications
            new_asset = new_assets_dict[item_id]
            quantity_changed = old_data["quantity"] != new_asset.quantity
            location_changed = (
                old_data["location_id"] != new_asset.location_id
                or old_data["location_flag"] != new_asset.location_flag
            )

            if quantity_changed or location_changed:
                changes.append(
                    _AssetChangeDelta(
                        item_id=item_id,
                        type_id=new_asset.type_id,
                        change_type="modified",
                        old_quantity=old_data["quantity"] if quantity_changed else None,
                        new_quantity=new_asset.quantity if quantity_changed else None,
                        old_location_id=(
                            old_data["location_id"] if location_changed else None
                        ),
                        new_location_id=(
                            new_asset.location_id if location_changed else None
                        ),
                        old_location_flag=(
                            old_data["location_flag"] if location_changed else None
                        ),
                        new_location_flag=(
                            new_asset.location_flag if location_changed else None
                        ),
                    )
                )

    # Find added assets
    for asset in new_assets:
        if asset.item_id not in current:
            changes.append(
                _AssetChangeDelta(
                    item_id=asset.item_id,
                    type_id=asset.type_id,
                    change_type="added",
                    new_quantity=asset.quantity,
                    new_location_id=asset.location_id,
                    new_location_flag=asset.location_flag,
                )
            )

    return changes


async def _save_changes(
    repo: Repository,
    snapshot_id: int,
    character_id: int,
    changes: list[_AssetChangeDelta],
) -> None:
    """Save asset changes to the database.

    Args:
        repo: Repository instance
        snapshot_id: Snapshot ID these changes belong to
        character_id: Character ID
        changes: List of changes to save
    """
    change_data = [
        (
            snapshot_id,
            character_id,
            change.item_id,
            change.type_id,
            change.change_type,
            change.old_quantity,
            change.new_quantity,
            change.old_location_id,
            change.new_location_id,
            change.old_location_flag,
            change.new_location_flag,
            datetime.now(UTC).isoformat(),
        )
        for change in changes
    ]

    await repo.executemany(
        """
        INSERT INTO asset_changes (
            snapshot_id, character_id, item_id, type_id, change_type,
            old_quantity, new_quantity, old_location_id, new_location_id,
            old_location_flag, new_location_flag, change_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        change_data,
    )


async def _update_current_assets(
    repo: Repository, character_id: int, assets: list[EveAsset], timestamp: datetime
) -> None:
    """Update current assets table with new snapshot.

    Args:
        repo: Repository instance
        character_id: Character ID
        assets: New asset list
        timestamp: Snapshot timestamp
    """
    # Delete old assets for this character
    await repo.execute(
        "DELETE FROM current_assets WHERE character_id = ?", (character_id,)
    )

    # Insert new assets
    asset_data = [
        (
            character_id,
            asset.item_id,
            asset.type_id,
            asset.quantity,
            asset.location_id,
            asset.location_type,
            asset.location_flag,
            1 if asset.is_singleton else 0,
            (
                (1 if asset.is_blueprint_copy else 0)
                if asset.is_blueprint_copy is not None
                else None
            ),
            timestamp.isoformat(),
        )
        for asset in assets
    ]

    await repo.executemany(
        """
        INSERT INTO current_assets (
            character_id, item_id, type_id, quantity, location_id,
            location_type, location_flag, is_singleton, is_blueprint_copy,
            last_updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        asset_data,
    )


__all__ = [
    "get_current_assets",
    "get_history",
    "get_snapshots",
    "save_snapshot",
]
