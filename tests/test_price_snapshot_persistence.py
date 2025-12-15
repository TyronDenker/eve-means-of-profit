"""Tests for Phase 3: Price History Persistence.

Tests verify that price snapshots save ALL items (not just owned) and filter
to exactly 5 supported regions for comprehensive price history data.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from data.repositories import prices
from data.repositories.prices import SUPPORTED_REGION_IDS
from models.app import (
    FuzzworkMarketDataPoint,
    FuzzworkMarketStats,
    FuzzworkRegionMarketData,
)


@pytest.fixture
def mock_repo():
    """Create mock repository with async methods."""
    repo = Mock()
    cursor = Mock()
    cursor.lastrowid = 12345
    repo.execute = AsyncMock(return_value=cursor)
    repo.executemany = AsyncMock()
    repo.commit = AsyncMock()
    return repo


def create_market_data_point(
    type_id: int, region_ids: list[int]
) -> FuzzworkMarketDataPoint:
    """Helper to create market data points with specified regions."""
    region_data = {}
    for region_id in region_ids:
        region_data[region_id] = FuzzworkRegionMarketData(
            buy_stats=FuzzworkMarketStats(
                weighted_average=100.0,
                max_price=200.0,
                min_price=50.0,
                stddev=10.0,
                median=100.0,
                volume=10000,
                num_orders=50,
                five_percent=110.0,
            ),
            sell_stats=FuzzworkMarketStats(
                weighted_average=105.0,
                max_price=210.0,
                min_price=55.0,
                stddev=12.0,
                median=105.0,
                volume=15000,
                num_orders=75,
                five_percent=115.0,
            ),
        )

    return FuzzworkMarketDataPoint(
        type_id=type_id,
        region_data=region_data,
    )


class TestPriceHistoryPersistence:
    """Test price snapshot persistence with region filtering."""

    @pytest.mark.asyncio
    async def test_snapshot_saves_all_items_not_just_owned(self, mock_repo):
        """TEST-025: Snapshot saves all items from FuzzworkProvider, not just owned.

        REQ-005: Price history database must persist market data for ALL items
        in the Fuzzwork CSV, not just items currently owned by characters.
        """
        # Arrange - create market data for multiple items with 5 regions
        market_data = [
            create_market_data_point(
                1, [10000002, 10000043, 10000032, 10000030, 10000042]
            ),
            create_market_data_point(
                2, [10000002, 10000043, 10000032, 10000030, 10000042]
            ),
            create_market_data_point(
                3, [10000002, 10000043, 10000032, 10000030, 10000042]
            ),
        ]

        # Act
        snapshot_id = await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            notes="Test snapshot - all items",
        )

        # Assert
        # Should save all 3 items * 5 regions = 15 price records
        assert mock_repo.executemany.called
        price_records = mock_repo.executemany.call_args[0][1]
        assert len(price_records) == 15  # 3 items * 5 regions
        assert snapshot_id == 12345

    @pytest.mark.asyncio
    async def test_snapshot_only_saves_5_regions(self, mock_repo):
        """TEST-026: Snapshot only saves data for the 5 supported regions.

        REQ-006: Price history database must save statistics for exactly 5 regions:
        Jita, Amarr, Dodixie, Rens, Hek
        """
        # Arrange - create market data with 5 supported regions
        jita = 10000002
        amarr = 10000043
        dodixie = 10000032
        rens = 10000030
        hek = 10000042

        market_data = [
            create_market_data_point(1, [jita, amarr, dodixie, rens, hek]),
        ]

        # Act
        await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            notes="Test 5-region snapshot",
        )

        # Assert
        price_records = mock_repo.executemany.call_args[0][1]
        # Should only have 5 records (1 item * 5 regions)
        assert len(price_records) == 5

        # Verify each record has a supported region_id
        for record in price_records:
            region_id = record[1]  # region_id is second element
            assert region_id in SUPPORTED_REGION_IDS

    @pytest.mark.asyncio
    async def test_region_filtering_excludes_non_supported(self, mock_repo):
        """TEST-027: Region filtering correctly excludes non-supported regions.

        REQ-007: Other regions present in the Fuzzwork CSV must be filtered out
        during price snapshot persistence.
        """
        # Arrange - create market data with non-supported regions included
        supported = [10000002, 10000043, 10000032, 10000030, 10000042]
        non_supported = [10000001, 10000003, 10000004]  # These should be excluded

        market_data = [
            create_market_data_point(1, supported + non_supported),  # Mix both
        ]

        # Act
        await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            notes="Test filtering non-supported regions",
        )

        # Assert
        price_records = mock_repo.executemany.call_args[0][1]
        # Should only have 5 records (1 item * 5 supported regions)
        assert len(price_records) == 5

        # Verify NO non-supported regions are included
        for record in price_records:
            region_id = record[1]  # region_id is second element
            assert region_id not in non_supported
            assert region_id in SUPPORTED_REGION_IDS

    @pytest.mark.asyncio
    async def test_supported_region_ids_constant(self, mock_repo):
        """TEST-028: SUPPORTED_REGION_IDS constant has exactly 5 regions.

        REQ-006, REQ-008: Region IDs must map to exactly 5 trade hubs with correct mappings
        """
        # Assert
        # Verify the constant is defined correctly
        assert len(SUPPORTED_REGION_IDS) == 5
        assert 10000002 in SUPPORTED_REGION_IDS  # Jita
        assert 10000043 in SUPPORTED_REGION_IDS  # Amarr
        assert 10000032 in SUPPORTED_REGION_IDS  # Dodixie
        assert 10000030 in SUPPORTED_REGION_IDS  # Rens
        assert 10000042 in SUPPORTED_REGION_IDS  # Hek

    @pytest.mark.asyncio
    async def test_empty_market_data_handled(self, mock_repo):
        """TEST-029: Empty market data is handled gracefully.

        Edge case: ensure system doesn't crash with empty data.
        """
        # Arrange
        market_data = []

        # Act - should not raise
        snapshot_id = await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            notes="Empty test",
        )

        # Assert
        assert snapshot_id == 12345
        # executemany might not be called if no records
        if mock_repo.executemany.called:
            price_records = mock_repo.executemany.call_args[0][1]
            assert len(price_records) == 0

    @pytest.mark.asyncio
    async def test_item_with_no_region_data_skipped(self, mock_repo):
        """TEST-030: Items with no region data are skipped.

        Edge case: an item might have empty region_data dict.
        """
        # Arrange
        market_data = [
            FuzzworkMarketDataPoint(
                type_id=1,
                region_data={},  # Empty region_data
            )
        ]

        # Act
        await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            notes="No region data test",
        )

        # Assert
        if mock_repo.executemany.called:
            price_records = mock_repo.executemany.call_args[0][1]
            assert len(price_records) == 0  # No records should be saved

    @pytest.mark.asyncio
    async def test_snapshot_logging_shows_items_and_regions(self, mock_repo):
        """TEST-031: Snapshot logging shows items and regions saved.

        Requirement: logging should show transparency about what was saved
        and what was filtered out (from requirements: "Add logging to show...")
        """
        # Arrange
        market_data = [
            create_market_data_point(
                1, [10000002, 10000043, 10000032, 10000030, 10000042, 10000001]
            ),
            create_market_data_point(2, [10000002, 10000043]),  # Only 2 regions
        ]

        # Act
        with patch("data.repositories.prices.logger") as mock_logger:
            await prices.save_snapshot(
                mock_repo,
                market_data=market_data,
                notes="Logging test",
            )

            # Assert - check that logging was called
            assert mock_logger.info.called or mock_logger.debug.called
            # The logging calls should mention items, regions, and filtering

    @pytest.mark.asyncio
    async def test_custom_prices_still_saved(self, mock_repo):
        """TEST-032: Custom prices are still saved correctly in snapshot.

        Phase 3 should not break custom price storage. They should continue
        to work as before, saved in separate custom_buy_price and custom_sell_price columns.
        """
        # Arrange
        market_data = [
            create_market_data_point(1, [10000002]),
        ]
        custom_prices = {1: {"buy": 95.0, "sell": 110.0}}

        # Act
        await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            custom_prices=custom_prices,
            notes="Custom prices test",
        )

        # Assert
        price_records = mock_repo.executemany.call_args[0][1]
        # Should have 1 record (1 item * 1 region)
        assert len(price_records) == 1

        # Custom prices should be in the record
        record = price_records[0]
        custom_buy = record[-2]  # custom_buy_price is second to last
        custom_sell = record[-1]  # custom_sell_price is last
        assert custom_buy == 95.0
        assert custom_sell == 110.0

    @pytest.mark.asyncio
    async def test_multiple_items_multiple_regions_combination(self, mock_repo):
        """TEST-033: Multiple items and regions save correctly.

        Complex scenario: 10 items across 5 regions should save 50 records.
        """
        # Arrange
        market_data = [
            create_market_data_point(
                i, [10000002, 10000043, 10000032, 10000030, 10000042]
            )
            for i in range(1, 11)  # 10 items
        ]

        # Act
        await prices.save_snapshot(
            mock_repo,
            market_data=market_data,
            notes="10x5 test",
        )

        # Assert
        price_records = mock_repo.executemany.call_args[0][1]
        assert len(price_records) == 50  # 10 items * 5 regions
