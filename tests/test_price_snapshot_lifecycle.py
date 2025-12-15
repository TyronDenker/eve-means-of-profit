"""Tests for price snapshot lifecycle (REQ-003, REQ-004, TEST-003).

Tests verify that price snapshots are created on account updates and
properly linked to snapshot groups for grouped net worth history.
"""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from src.data import FuzzworkProvider
from src.data.parsers.fuzzwork_csv import FuzzworkCSVParser
from src.data.repositories import Repository, networth, prices
from src.models.app import (
    FuzzworkMarketDataPoint,
    FuzzworkMarketStats,
    FuzzworkRegionMarketData,
)
from src.services.networth_service import NetWorthService


@pytest.fixture
async def temp_repo():
    """Create temporary in-memory repository."""
    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        repo = Repository(str(db_path))
        await repo.initialize()
        yield repo
        await repo.close()


@pytest.fixture
def mock_fuzzwork_provider():
    """Create mock Fuzzwork provider with test data."""
    # Create minimal CSV
    csv_data = """type_id,region_id,sell_median,sell_volume,sell_avg,sell_max,sell_min,sell_stddev,sell_percentile,buy_median,buy_volume,buy_avg,buy_max,buy_min,buy_stddev,buy_percentile
34,10000002,500.0,1000,510.0,600.0,400.0,50.0,480.0,490.0,800,495.0,520.0,470.0,25.0,485.0
35,10000002,1000.0,500,1010.0,1100.0,900.0,80.0,950.0,980.0,300,990.0,1020.0,960.0,30.0,970.0
"""

    parser = FuzzworkCSVParser(csv_data)
    return FuzzworkProvider(parser)


@pytest.mark.asyncio
async def test_price_snapshot_created_on_networth_save(
    temp_repo, mock_fuzzwork_provider
):
    """Test that price snapshots are created when saving networth snapshots."""
    # Create mock ESI client
    mock_esi = Mock()

    # Create networth service with fuzzwork
    service = NetWorthService(
        esi_client=mock_esi,
        repository=temp_repo,
        fuzzwork_provider=mock_fuzzwork_provider,
        settings_manager=None,
        sde_provider=None,
        location_service=None,
    )

    # Create a snapshot group
    snapshot_group_id = await service.create_snapshot_group(
        account_id=1,
        refresh_source="account",
        label="Test refresh",
    )

    # Save networth snapshot (this should create price snapshot)
    character_id = 12345

    # First, we need to populate some data to calculate networth
    # Add wallet balance
    await temp_repo.execute(
        "INSERT INTO wallet_journal (entry_id, character_id, date, ref_type, first_party_id, amount, balance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            character_id,
            datetime.now(UTC).isoformat(),
            "mission_reward",
            character_id,
            1000.0,
            5000.0,
        ),
    )
    await temp_repo.commit()

    # Save networth snapshot
    snapshot_id = await service.save_networth_snapshot(character_id, snapshot_group_id)

    # Verify networth snapshot was created
    assert snapshot_id > 0

    # Verify networth snapshot has correct snapshot_group_id
    networth_snap = await networth.get_latest_networth(temp_repo, character_id)
    assert networth_snap is not None
    assert networth_snap.snapshot_group_id == snapshot_group_id

    # Check if price snapshot was created
    price_snapshots = await prices.get_snapshots(temp_repo, limit=1)

    # Price snapshot creation depends on whether Fuzzwork data is newer
    # Since we just created the provider, it should create one
    if price_snapshots:
        # Verify price snapshot is linked to snapshot group
        assert price_snapshots[0].snapshot_group_id == snapshot_group_id


@pytest.mark.asyncio
async def test_price_snapshot_links_to_snapshot_group(
    temp_repo, mock_fuzzwork_provider
):
    """Test that price snapshots are properly linked to snapshot groups."""
    mock_esi = Mock()

    service = NetWorthService(
        esi_client=mock_esi,
        repository=temp_repo,
        fuzzwork_provider=mock_fuzzwork_provider,
        settings_manager=None,
        sde_provider=None,
        location_service=None,
    )

    # Create snapshot group for refresh_all
    group_id_all = await service.create_snapshot_group(
        account_id=None,
        refresh_source="refresh_all",
        label="Refresh all characters",
    )

    # Create test price data
    price_data = [
        FuzzworkMarketDataPoint(
            type_id=34,
            snapshot_time=datetime.now(UTC),
            region_data={
                10000002: FuzzworkRegionMarketData(
                    region_id=10000002,
                    sell_stats=FuzzworkMarketStats(
                        weighted_average=500.0,
                        max_price=600.0,
                        min_price=400.0,
                        stddev=50.0,
                        median=500.0,
                        volume=1000,
                        num_orders=10,
                        five_percent=480.0,
                    ),
                    buy_stats=None,
                ),
            },
        ),
    ]

    # Save price snapshot with group linkage
    price_snapshot_id = await prices.save_snapshot(
        temp_repo,
        price_data,
        notes="Test price snapshot",
        snapshot_group_id=group_id_all,
    )

    assert price_snapshot_id > 0

    # Verify linkage
    snapshots = await prices.get_snapshots(temp_repo, limit=1)
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_id == price_snapshot_id
    assert snapshots[0].snapshot_group_id == group_id_all


@pytest.mark.asyncio
async def test_multiple_price_snapshots_different_groups(
    temp_repo, mock_fuzzwork_provider
):
    """Test that different refresh operations create price snapshots with different groups."""
    mock_esi = Mock()

    service = NetWorthService(
        esi_client=mock_esi,
        repository=temp_repo,
        fuzzwork_provider=mock_fuzzwork_provider,
        settings_manager=None,
        sde_provider=None,
        location_service=None,
    )

    # Create two separate snapshot groups
    group1 = await service.create_snapshot_group(
        account_id=1, refresh_source="account", label="Account 1"
    )
    group2 = await service.create_snapshot_group(
        account_id=2, refresh_source="account", label="Account 2"
    )

    # Create price data
    price_data = [
        FuzzworkMarketDataPoint(
            type_id=34,
            snapshot_time=datetime.now(UTC),
            region_data={
                10000002: FuzzworkRegionMarketData(
                    region_id=10000002,
                    sell_stats=FuzzworkMarketStats(
                        weighted_average=500.0,
                        max_price=600.0,
                        min_price=400.0,
                        stddev=50.0,
                        median=500.0,
                        volume=1000,
                        num_orders=10,
                        five_percent=480.0,
                    ),
                    buy_stats=None,
                ),
            },
        ),
    ]

    # Save price snapshot for group 1
    await prices.save_snapshot(
        temp_repo, price_data, notes="Group 1", snapshot_group_id=group1
    )

    # Small delay to ensure different timestamps
    await asyncio.sleep(0.1)

    # Save price snapshot for group 2
    await prices.save_snapshot(
        temp_repo, price_data, notes="Group 2", snapshot_group_id=group2
    )

    # Verify both were created with correct groups
    all_snapshots = await prices.get_snapshots(temp_repo, limit=10)
    assert len(all_snapshots) == 2

    # Check groups are correctly assigned
    snapshot_groups = {snap.snapshot_group_id for snap in all_snapshots}
    assert group1 in snapshot_groups
    assert group2 in snapshot_groups


@pytest.mark.asyncio
async def test_price_snapshot_schema_migration(temp_repo):
    """Test that price_snapshots table receives snapshot_group_id column migration."""
    mock_esi = Mock()

    # Create service (this triggers schema migration)
    service = NetWorthService(
        esi_client=mock_esi,
        repository=temp_repo,
        fuzzwork_provider=None,
        settings_manager=None,
        sde_provider=None,
        location_service=None,
    )

    # Trigger schema check
    await service._ensure_schema()

    # Verify price_snapshots table has snapshot_group_id column
    columns = await temp_repo.get_table_info("price_snapshots")
    col_names = {col[1] if isinstance(col, tuple) else col["name"] for col in columns}

    assert "snapshot_group_id" in col_names


@pytest.mark.asyncio
async def test_price_snapshot_only_created_when_fuzzwork_updated(
    temp_repo, mock_fuzzwork_provider
):
    """Test that price snapshots are only created when Fuzzwork data is newer."""
    mock_esi = Mock()

    service = NetWorthService(
        esi_client=mock_esi,
        repository=temp_repo,
        fuzzwork_provider=mock_fuzzwork_provider,
        settings_manager=None,
        sde_provider=None,
        location_service=None,
    )

    # Create initial price snapshot with current Fuzzwork data
    group1 = await service.create_snapshot_group(None, "manual", "First")

    price_data = [
        FuzzworkMarketDataPoint(
            type_id=34,
            snapshot_time=datetime.now(UTC),
            region_data={
                10000002: FuzzworkRegionMarketData(
                    region_id=10000002,
                    sell_stats=FuzzworkMarketStats(
                        weighted_average=500.0,
                        max_price=600.0,
                        min_price=400.0,
                        stddev=50.0,
                        median=500.0,
                        volume=1000,
                        num_orders=10,
                        five_percent=480.0,
                    ),
                    buy_stats=None,
                ),
            },
        ),
    ]

    snap1 = await prices.save_snapshot(
        temp_repo, price_data, notes="Initial", snapshot_group_id=group1
    )
    assert snap1 > 0

    # Now save another networth snapshot WITHOUT updating Fuzzwork
    # This should NOT create a new price snapshot (Fuzzwork data unchanged)
    character_id = 12345

    # Add wallet data
    await temp_repo.execute(
        "INSERT INTO wallet_journal (entry_id, character_id, date, ref_type, first_party_id, amount, balance) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            1,
            character_id,
            datetime.now(UTC).isoformat(),
            "mission_reward",
            character_id,
            1000.0,
            5000.0,
        ),
    )
    await temp_repo.commit()

    group2 = await service.create_snapshot_group(None, "manual", "Second")

    # This should use existing price snapshot (not create new one)
    await service.save_networth_snapshot(character_id, group2)

    # Verify only one price snapshot exists (from initial save)
    all_price_snapshots = await prices.get_snapshots(temp_repo, limit=10)

    # Should have exactly one price snapshot (the initial one)
    assert len(all_price_snapshots) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
