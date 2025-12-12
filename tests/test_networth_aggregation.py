import asyncio
from datetime import UTC, datetime, timedelta

from data.repositories import networth
from data.repositories.repository import Repository


async def _setup_repo_with_samples(repo: Repository):
    await repo.initialize()
    now = datetime.now(UTC)
    # Insert sample snapshots for two characters across groups 1,2,3
    rows = [
        # character 1: group 1 -> 100, group 2 -> 150
        (1, None, 1, (now - timedelta(days=3)).isoformat(), 100.0, 0, 0, 0, 0, 0, 0, 0),
        (1, None, 2, (now - timedelta(days=2)).isoformat(), 150.0, 0, 0, 0, 0, 0, 0, 0),
        # character 2: group 1 -> 200, group 3 -> 300
        (2, None, 1, (now - timedelta(days=3)).isoformat(), 200.0, 0, 0, 0, 0, 0, 0, 0),
        (2, None, 3, (now - timedelta(days=1)).isoformat(), 300.0, 0, 0, 0, 0, 0, 0, 0),
    ]

    for r in rows:
        await repo.execute(
            """
            INSERT INTO networth_snapshots (
                character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value, wallet_balance,
                market_escrow, market_sell_value, contract_collateral, contract_value, industry_job_value, plex_vault
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            r,
        )
    await repo.commit()


def test_get_snapshots_for_group_returns_latest_per_character():
    async def _run():
        repo = Repository(db_path=":memory:")
        await _setup_repo_with_samples(repo)

        # group 1 should pick character1->100, character2->200
        snaps = await networth.get_snapshots_for_group(repo, 1)
        assert len(snaps) == 2
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 100.0
        assert d[2] == 200.0

        # group 2 should pick character1->150 (latest<=2), character2->200 (latest<=2 is group1)
        snaps = await networth.get_snapshots_for_group(repo, 2)
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 150.0
        assert d[2] == 200.0

        # group 3 should pick character1->150, character2->300
        snaps = await networth.get_snapshots_for_group(repo, 3)
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 150.0
        assert d[2] == 300.0

        await repo.close()

    asyncio.run(_run())


async def _setup_repo_with_mixed_samples(repo: Repository):
    """Setup repo with both grouped and ungrouped (legacy) snapshots."""
    await repo.initialize()
    now = datetime.now(UTC)
    # Insert sample snapshots: some with group_id, some without (legacy)
    rows = [
        # character 1: legacy snapshot 3 days ago, grouped snapshot 1 day ago
        (
            1,
            None,
            None,
            (now - timedelta(days=3)).isoformat(),
            100.0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
        (1, None, 1, (now - timedelta(days=1)).isoformat(), 150.0, 0, 0, 0, 0, 0, 0, 0),
        # character 2: legacy snapshot 2 days ago only
        (
            2,
            None,
            None,
            (now - timedelta(days=2)).isoformat(),
            200.0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
        # character 3: grouped snapshots only
        (3, None, 1, (now - timedelta(days=1)).isoformat(), 300.0, 0, 0, 0, 0, 0, 0, 0),
    ]

    for r in rows:
        await repo.execute(
            """
            INSERT INTO networth_snapshots (
                character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value, wallet_balance,
                market_escrow, market_sell_value, contract_collateral, contract_value, industry_job_value, plex_vault
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            r,
        )
    await repo.commit()
    return now


def test_get_snapshots_up_to_time_returns_latest_per_character():
    """Test that get_snapshots_up_to_time picks the latest snapshot per character."""

    async def _run():
        repo = Repository(db_path=":memory:")
        now = await _setup_repo_with_mixed_samples(repo)

        # Query at 1.5 days ago: should get char1->100 (legacy), char2->200 (legacy)
        # char3 has no snapshot before 1.5 days ago
        target_time = now - timedelta(days=1, hours=12)
        snaps = await networth.get_snapshots_up_to_time(repo, target_time)
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert len(snaps) == 2
        assert d[1] == 100.0  # Legacy snapshot from 3 days ago
        assert d[2] == 200.0  # Legacy snapshot from 2 days ago

        # Query at now: should get all 3 characters with their latest
        target_time = now
        snaps = await networth.get_snapshots_up_to_time(repo, target_time)
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert len(snaps) == 3
        assert d[1] == 150.0  # Grouped snapshot from 1 day ago (newest)
        assert d[2] == 200.0  # Legacy snapshot from 2 days ago (only one)
        assert d[3] == 300.0  # Grouped snapshot from 1 day ago

        # Filter by character_ids
        snaps = await networth.get_snapshots_up_to_time(repo, now, character_ids=[1, 3])
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert len(snaps) == 2
        assert d[1] == 150.0
        assert d[3] == 300.0

        await repo.close()

    asyncio.run(_run())


def test_aggregation_stability_across_time():
    """Test that Total aggregation is stable when querying different time points."""

    async def _run():
        repo = Repository(db_path=":memory:")
        now = await _setup_repo_with_mixed_samples(repo)

        # Query at different time points and verify aggregation is consistent
        # At 2.5 days ago: only char1 has snapshot (100)
        snaps = await networth.get_snapshots_up_to_time(
            repo, now - timedelta(days=2, hours=12)
        )
        total = sum(s.total_asset_value for s in snaps)
        assert total == 100.0

        # At 1.5 days ago: char1 (100) + char2 (200) = 300
        snaps = await networth.get_snapshots_up_to_time(
            repo, now - timedelta(days=1, hours=12)
        )
        total = sum(s.total_asset_value for s in snaps)
        assert total == 300.0

        # At now: char1 (150) + char2 (200) + char3 (300) = 650
        snaps = await networth.get_snapshots_up_to_time(repo, now)
        total = sum(s.total_asset_value for s in snaps)
        assert total == 650.0

        await repo.close()

    asyncio.run(_run())


def test_get_snapshots_for_group_returns_correct_snapshots():
    """Test get_snapshots_for_group returns latest snapshot per character within group."""

    async def _run():
        repo = Repository(db_path=":memory:")
        await repo.initialize()
        now = datetime.now(UTC)

        # Create snapshots with different group IDs
        rows = [
            # char 1: group 1 -> 100, group 2 -> 200
            (
                1,
                None,
                1,
                (now - timedelta(days=3)).isoformat(),
                100.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            (
                1,
                None,
                2,
                (now - timedelta(days=2)).isoformat(),
                200.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            # char 2: group 1 -> 150
            (
                2,
                None,
                1,
                (now - timedelta(days=3)).isoformat(),
                150.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            # char 3: group 2 -> 300
            (
                3,
                None,
                2,
                (now - timedelta(days=2)).isoformat(),
                300.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
        ]

        for r in rows:
            await repo.execute(
                """
                INSERT INTO networth_snapshots (
                    character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value,
                    wallet_balance, market_escrow, market_sell_value, contract_collateral,
                    contract_value, industry_job_value, plex_vault
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                r,
            )
        await repo.commit()

        # Group 1: char1->100, char2->150
        snaps = await networth.get_snapshots_for_group(repo, 1)
        assert len(snaps) == 2
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 100.0
        assert d[2] == 150.0

        # Group 2: char1->200 (latest), char2->150 (from group 1), char3->300
        snaps = await networth.get_snapshots_for_group(repo, 2)
        assert len(snaps) == 3
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 200.0
        assert d[2] == 150.0
        assert d[3] == 300.0

        await repo.close()

    asyncio.run(_run())


def test_aggregation_produces_stable_totals():
    """Test that aggregation produces consistent totals regardless of query order."""

    async def _run():
        repo = Repository(db_path=":memory:")
        await repo.initialize()
        now = datetime.now(UTC)

        # Create multiple snapshots per character
        rows = [
            (
                1,
                None,
                1,
                (now - timedelta(hours=5)).isoformat(),
                100.0,
                50.0,
                10.0,
                20.0,
                5.0,
                10.0,
                5.0,
                0,
            ),
            (
                1,
                None,
                2,
                (now - timedelta(hours=3)).isoformat(),
                110.0,
                55.0,
                11.0,
                22.0,
                5.5,
                11.0,
                5.5,
                0,
            ),
            (
                1,
                None,
                3,
                (now - timedelta(hours=1)).isoformat(),
                120.0,
                60.0,
                12.0,
                24.0,
                6.0,
                12.0,
                6.0,
                0,
            ),
            (
                2,
                None,
                1,
                (now - timedelta(hours=5)).isoformat(),
                200.0,
                100.0,
                20.0,
                40.0,
                10.0,
                20.0,
                10.0,
                0,
            ),
            (
                2,
                None,
                2,
                (now - timedelta(hours=3)).isoformat(),
                220.0,
                110.0,
                22.0,
                44.0,
                11.0,
                22.0,
                11.0,
                0,
            ),
        ]

        for r in rows:
            await repo.execute(
                """
                INSERT INTO networth_snapshots (
                    character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value,
                    wallet_balance, market_escrow, market_sell_value, contract_collateral,
                    contract_value, industry_job_value, plex_vault
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                r,
            )
        await repo.commit()

        # Query multiple times - totals should be stable
        totals = []
        for _ in range(3):
            snaps = await networth.get_snapshots_for_group(repo, 3)
            total = sum(s.total_asset_value for s in snaps)
            totals.append(total)

        # All totals should be identical
        assert totals[0] == totals[1] == totals[2]

        # For group 3: char1->120 (latest), char2->220 (from group 2, latest <= 3)
        expected_total = 120.0 + 220.0  # 340.0
        assert totals[0] == expected_total

        await repo.close()

    asyncio.run(_run())


def test_mixed_grouped_and_legacy_snapshots():
    """Test aggregation with mix of grouped (snapshot_group_id) and legacy (NULL) snapshots."""

    async def _run():
        repo = Repository(db_path=":memory:")
        await repo.initialize()
        now = datetime.now(UTC)

        # Mixed snapshots: some with group_id, some without (legacy)
        rows = [
            # char 1: legacy snapshot, then grouped
            (
                1,
                None,
                None,
                (now - timedelta(days=5)).isoformat(),
                50.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            (
                1,
                None,
                1,
                (now - timedelta(days=2)).isoformat(),
                100.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            # char 2: only legacy snapshots
            (
                2,
                None,
                None,
                (now - timedelta(days=4)).isoformat(),
                200.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            (
                2,
                None,
                None,
                (now - timedelta(days=1)).isoformat(),
                250.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            # char 3: only grouped snapshots
            (
                3,
                None,
                1,
                (now - timedelta(days=2)).isoformat(),
                300.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
        ]

        for r in rows:
            await repo.execute(
                """
                INSERT INTO networth_snapshots (
                    character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value,
                    wallet_balance, market_escrow, market_sell_value, contract_collateral,
                    contract_value, industry_job_value, plex_vault
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                r,
            )
        await repo.commit()

        # get_snapshots_for_group only considers grouped snapshots
        snaps = await networth.get_snapshots_for_group(repo, 1)
        assert len(snaps) == 2  # Only char 1 and char 3 have grouped snapshots
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 100.0
        assert d[3] == 300.0
        assert 2 not in d  # char 2 has no grouped snapshots

        # get_snapshots_up_to_time considers all snapshots (grouped + legacy)
        snaps = await networth.get_snapshots_up_to_time(repo, now)
        assert len(snaps) == 3  # All 3 characters
        d = {s.character_id: s.total_asset_value for s in snaps}
        assert d[1] == 100.0  # Latest is grouped
        assert d[2] == 250.0  # Latest legacy
        assert d[3] == 300.0  # Grouped

        await repo.close()

    asyncio.run(_run())


def test_empty_group_returns_empty_list():
    """Test that querying a group with no snapshots returns empty list."""

    async def _run():
        repo = Repository(db_path=":memory:")
        await repo.initialize()

        # No snapshots inserted
        snaps = await networth.get_snapshots_for_group(repo, 999)
        assert snaps == []

        await repo.close()

    asyncio.run(_run())


def test_character_filter_in_aggregation():
    """Test that character_ids filter works correctly in aggregation."""

    async def _run():
        repo = Repository(db_path=":memory:")
        await repo.initialize()
        now = datetime.now(UTC)

        rows = [
            (
                1,
                None,
                1,
                (now - timedelta(days=1)).isoformat(),
                100.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            (
                2,
                None,
                1,
                (now - timedelta(days=1)).isoformat(),
                200.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
            (
                3,
                None,
                1,
                (now - timedelta(days=1)).isoformat(),
                300.0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            ),
        ]

        for r in rows:
            await repo.execute(
                """
                INSERT INTO networth_snapshots (
                    character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value,
                    wallet_balance, market_escrow, market_sell_value, contract_collateral,
                    contract_value, industry_job_value, plex_vault
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                r,
            )
        await repo.commit()

        # Filter to only chars 1 and 3
        snaps = await networth.get_snapshots_for_group(repo, 1, character_ids=[1, 3])
        assert len(snaps) == 2
        total = sum(s.total_asset_value for s in snaps)
        assert total == 400.0  # 100 + 300

        # Filter to single character
        snaps = await networth.get_snapshots_for_group(repo, 1, character_ids=[2])
        assert len(snaps) == 1
        assert snaps[0].total_asset_value == 200.0

        await repo.close()

    asyncio.run(_run())


def test_aggregation_includes_all_components():
    """Test that aggregation includes all net worth components."""

    async def _run():
        repo = Repository(db_path=":memory:")
        await repo.initialize()
        now = datetime.now(UTC)

        # Snapshot with all components
        await repo.execute(
            """
            INSERT INTO networth_snapshots (
                character_id, account_id, snapshot_group_id, snapshot_time, total_asset_value,
                wallet_balance, market_escrow, market_sell_value, contract_collateral,
                contract_value, industry_job_value, plex_vault
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                None,
                1,
                now.isoformat(),
                1000.0,
                100.0,
                50.0,
                200.0,
                25.0,
                75.0,
                150.0,
                400.0,
            ),
        )
        await repo.commit()

        snaps = await networth.get_snapshots_for_group(repo, 1)
        assert len(snaps) == 1
        snap = snaps[0]

        assert snap.total_asset_value == 1000.0
        assert snap.wallet_balance == 100.0
        assert snap.market_escrow == 50.0
        assert snap.market_sell_value == 200.0
        assert snap.contract_collateral == 25.0
        assert snap.contract_value == 75.0
        assert snap.industry_job_value == 150.0
        assert snap.plex_vault == 400.0

        await repo.close()

    asyncio.run(_run())


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
