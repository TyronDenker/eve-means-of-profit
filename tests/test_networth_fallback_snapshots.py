"""Test that graph snapshots use fallback for missing characters in groups.

When refreshing a single account (creating a group with only one character's
snapshot), the graph should still show data from other characters using their
latest available snapshots up to the group's timestamp.
"""

from datetime import UTC, datetime

import pytest

from data.repositories import Repository


@pytest.mark.asyncio
async def test_graph_includes_fallback_snapshots_for_missing_characters(
    repository: Repository,
):
    """Verify that characters missing from a group use latest prior snapshots.

    Scenario:
    - Create snapshot group for all characters at T0
    - Create snapshot group for only ax2 at T1
    - When plotting group at T1, ax2 should come from T1 group
    - Other characters should fallback to their T0 (or earlier) snapshots
    """
    # Create initial snapshots at T0 for multiple characters
    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    t1 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)

    char_1 = 111
    char_2 = 222
    char_3 = 333

    # T0: All characters snapshot
    group_id_t0 = 1
    await repository.execute(
        "INSERT INTO networth_snapshot_groups (snapshot_group_id, created_at) VALUES (?, ?)",
        (group_id_t0, t0.isoformat()),
    )

    # Create snapshots for all three at T0
    for char_id, value in [
        (char_1, 10_000_000),
        (char_2, 20_000_000),
        (char_3, 30_000_000),
    ]:
        await repository.execute(
            """INSERT INTO networth_snapshots 
               (character_id, snapshot_group_id, snapshot_time, total_asset_value, wallet_balance)
               VALUES (?, ?, ?, ?, ?)""",
            (char_id, group_id_t0, t0.isoformat(), value, 1000),
        )

    await repository.commit()

    # T1: Only ax2 (char_1) snapshot
    group_id_t1 = 2
    await repository.execute(
        "INSERT INTO networth_snapshot_groups (snapshot_group_id, created_at) VALUES (?, ?)",
        (group_id_t1, t1.isoformat()),
    )

    # Create snapshot for only char_1 at T1
    await repository.execute(
        """INSERT INTO networth_snapshots 
           (character_id, snapshot_group_id, snapshot_time, total_asset_value, wallet_balance)
           VALUES (?, ?, ?, ?, ?)""",
        (char_1, group_id_t1, t1.isoformat(), 11_000_000, 1100),
    )

    await repository.commit()

    # Verify that char_2 and char_3 should be findable using fallback query
    # This simulates what the graph plotting code does
    all_char_ids = [char_1, char_2, char_3]

    # Get snapshots for the T1 group
    char_snaps_t1 = await repository.fetchall(
        """SELECT character_id, snapshot_group_id, snapshot_time, total_asset_value
           FROM networth_snapshots
           WHERE snapshot_group_id = ?
           ORDER BY character_id""",
        (group_id_t1,),
    )

    char_snaps_t1_ids = {row[0] for row in char_snaps_t1}
    assert char_snaps_t1_ids == {char_1}, "Only char_1 should be in T1 group"

    # Find missing characters
    chars_with_missing_snaps = [
        cid for cid in all_char_ids if cid not in char_snaps_t1_ids
    ]
    assert chars_with_missing_snaps == [char_2, char_3]

    # Get fallback snapshots
    fallback_snaps = await repository.fetchall(
        f"""
        SELECT character_id, snapshot_time, total_asset_value
        FROM (
            SELECT ns.character_id, ns.snapshot_time, ns.total_asset_value,
                   ROW_NUMBER() OVER (
                       PARTITION BY ns.character_id
                       ORDER BY ns.snapshot_time DESC
                   ) as rn
            FROM networth_snapshots ns
            WHERE ns.character_id IN ({",".join("?" for _ in chars_with_missing_snaps)})
              AND ns.snapshot_time <= ?
        ) t
        WHERE rn = 1
        """,
        tuple(chars_with_missing_snaps + [t1.isoformat()]),
    )

    # Verify fallback snapshots were found
    fallback_snaps_dict = {row[0]: row for row in fallback_snaps}
    assert char_2 in fallback_snaps_dict, "char_2 should have fallback snapshot"
    assert char_3 in fallback_snaps_dict, "char_3 should have fallback snapshot"

    # Verify correct values
    assert fallback_snaps_dict[char_2][2] == 20_000_000  # T0 value for char_2
    assert fallback_snaps_dict[char_3][2] == 30_000_000  # T0 value for char_3


@pytest.mark.asyncio
async def test_fallback_respects_timestamp_boundary(repository: Repository):
    """Verify fallback snapshots respect the group_time boundary."""
    char_1 = 111

    t0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
    t1 = datetime(2025, 1, 1, 13, 0, 0, tzinfo=UTC)
    t2 = datetime(2025, 1, 1, 14, 0, 0, tzinfo=UTC)

    # Create snapshots at T0, T1, T2
    for group_id, t, value in [
        (1, t0, 10_000_000),
        (2, t1, 15_000_000),
        (3, t2, 20_000_000),
    ]:
        await repository.execute(
            "INSERT INTO networth_snapshot_groups (snapshot_group_id, created_at) VALUES (?, ?)",
            (group_id, t.isoformat()),
        )
        await repository.execute(
            """INSERT INTO networth_snapshots 
               (character_id, snapshot_group_id, snapshot_time, total_asset_value, wallet_balance)
               VALUES (?, ?, ?, ?, ?)""",
            (char_1, group_id, t.isoformat(), value, 100),
        )

    await repository.commit()

    # Query for snapshots up to T1
    fallback_snaps = await repository.fetchall(
        """
        SELECT character_id, snapshot_time, total_asset_value
        FROM (
            SELECT ns.character_id, ns.snapshot_time, ns.total_asset_value,
                   ROW_NUMBER() OVER (
                       PARTITION BY ns.character_id
                       ORDER BY ns.snapshot_time DESC
                   ) as rn
            FROM networth_snapshots ns
            WHERE ns.character_id = ?
              AND ns.snapshot_time <= ?
        ) t
        WHERE rn = 1
        """,
        (char_1, t1.isoformat()),
    )

    # Should get T1 snapshot, not T2
    assert len(fallback_snaps) == 1
    assert fallback_snaps[0][2] == 15_000_000, "Should get T1 value (15M), not T2 (20M)"
