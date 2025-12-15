"""Tests for asset tree duplication fix and pricing correctness (TASK-033)."""

import os
import sys
from pathlib import Path

# Ensure src is on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Run Qt in minimal mode to avoid GUI plugin errors
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ui.tabs.asset_tree_tab import AssetTreeTab


@pytest.fixture
def mock_services():
    """Create mock services for AssetTreeTab."""
    character_service = Mock()
    asset_service = Mock()
    location_service = Mock()

    # Setup default returns
    character_service.get_authenticated_characters = AsyncMock(return_value=[])
    asset_service.get_all_enriched_assets = AsyncMock(return_value=[])
    asset_service.build_asset_tree_from_assets = Mock(return_value={"roots": []})
    location_service.resolve_locations_bulk = AsyncMock(return_value={})

    # Mock repo for price lookups
    asset_service._repo = Mock()

    return {
        "character_service": character_service,
        "asset_service": asset_service,
        "location_service": location_service,
    }


@pytest.fixture
def asset_tree_tab(qtbot, mock_services):
    """Create AssetTreeTab instance."""
    tab = AssetTreeTab(
        character_service=mock_services["character_service"],
        asset_service=mock_services["asset_service"],
        location_service=mock_services["location_service"],
    )
    qtbot.addWidget(tab)
    return tab


@pytest.mark.asyncio
async def test_no_duplication_on_concurrent_refresh(
    qtbot, asset_tree_tab, mock_services
):
    """Test that concurrent refresh calls don't create duplicate nodes."""
    # Setup mock character
    mock_char = Mock(
        character_id=123, character_name="Test Character", name="Test Character"
    )

    # Mock enriched assets
    mock_asset = Mock(
        type_id=34,
        type_name="Tritanium",
        quantity=1000,
        market_value=5.0,
        structure_id=None,
        station_id=60003760,
    )

    mock_services["asset_service"].get_all_enriched_assets = AsyncMock(
        return_value=[mock_asset]
    )

    # Mock tree building
    mock_root = Mock()
    mock_root.get_total_value = Mock(return_value=5000.0)
    mock_root.get_item_count = Mock(return_value=1)
    mock_root.location_name = "Jita IV - Moon 4"
    mock_root.children = []

    mock_services["asset_service"].build_asset_tree_from_assets = Mock(
        return_value={"roots": [mock_root]}
    )

    # Set characters
    asset_tree_tab._current_characters = [mock_char]

    # Start first refresh
    task1 = asyncio.create_task(asset_tree_tab._do_refresh())

    # Try to start second refresh immediately (should be blocked)
    task2 = asyncio.create_task(asset_tree_tab._do_refresh())

    # Wait for both to complete
    await task1
    await task2

    # Check that tree has only one character root (not duplicated)
    tree_widget = asset_tree_tab._tree
    root_count = tree_widget.topLevelItemCount()

    # Should only have one root (one character)
    assert root_count == 1


@pytest.mark.asyncio
async def test_refresh_guard_prevents_concurrent_execution(
    qtbot, asset_tree_tab, mock_services
):
    """Test that _is_refreshing guard prevents concurrent refresh execution."""
    # Mock slow enriched assets call
    slow_return = AsyncMock(
        side_effect=lambda *args, **kwargs: asyncio.sleep(0.1)
        or asyncio.Future().set_result([])
    )
    mock_services["asset_service"].get_all_enriched_assets = slow_return

    asset_tree_tab._current_characters = [Mock(character_id=123, name="Test")]

    # Start first refresh
    assert not asset_tree_tab._is_refreshing
    task1 = asyncio.create_task(asset_tree_tab._do_refresh())

    # Wait a bit for first refresh to start
    await asyncio.sleep(0.01)
    assert asset_tree_tab._is_refreshing

    # Try second refresh (should exit early)
    task2 = asyncio.create_task(asset_tree_tab._do_refresh())
    await asyncio.sleep(0.01)

    # Wait for both to complete
    await task1
    await task2

    # Guard should be cleared
    assert not asset_tree_tab._is_refreshing


@pytest.mark.asyncio
async def test_pricing_with_custom_prices(qtbot, asset_tree_tab, mock_services):
    """Test that custom prices override snapshot prices."""
    mock_char = Mock(character_id=123, character_name="Test", name="Test")

    # Mock enriched asset
    mock_asset = Mock(
        type_id=34,
        quantity=1000,
        market_value=None,  # No initial price
        structure_id=None,
        station_id=60003760,
    )

    mock_services["asset_service"].get_all_enriched_assets = AsyncMock(
        return_value=[mock_asset]
    )

    # Mock settings with custom price
    with patch("ui.tabs.asset_tree_tab.get_settings_manager") as mock_get_settings:
        mock_settings = Mock()
        mock_settings.get_market_source_station = Mock(return_value="jita")
        mock_settings.get_market_price_type = Mock(return_value="sell")
        mock_settings.get_market_weighted_buy_ratio = Mock(return_value=0.3)
        mock_settings.get_custom_price = Mock(
            return_value={"sell": 10.0}  # Custom price
        )
        mock_get_settings.return_value = mock_settings

        # Mock snapshot prices
        with patch(
            "ui.tabs.asset_tree_tab.prices.get_latest_snapshot_prices"
        ) as mock_get_prices:
            mock_get_prices.return_value = {
                34: 5.0
            }  # Snapshot price (should be overridden)

            # Mock tree building to capture applied price
            def capture_price(assets):
                # Custom price should be applied
                assert assets[0].market_value == 10.0  # Custom price wins
                mock_root = Mock()
                mock_root.get_total_value = Mock(return_value=10000.0)
                mock_root.get_item_count = Mock(return_value=1)
                mock_root.location_name = "Test Location"
                mock_root.children = []
                return {"roots": [mock_root]}

            mock_services["asset_service"].build_asset_tree_from_assets = Mock(
                side_effect=capture_price
            )

            asset_tree_tab._current_characters = [mock_char]
            await asset_tree_tab._do_refresh()


@pytest.mark.asyncio
async def test_pricing_with_snapshot_prices_no_custom(
    qtbot, asset_tree_tab, mock_services
):
    """Test that snapshot prices are used when no custom price set."""
    mock_char = Mock(character_id=123, character_name="Test", name="Test")

    mock_asset = Mock(
        type_id=34,
        quantity=1000,
        market_value=None,
        structure_id=None,
        station_id=60003760,
    )

    mock_services["asset_service"].get_all_enriched_assets = AsyncMock(
        return_value=[mock_asset]
    )

    with patch("ui.tabs.asset_tree_tab.get_settings_manager") as mock_get_settings:
        mock_settings = Mock()
        mock_settings.get_market_source_station = Mock(return_value="jita")
        mock_settings.get_market_price_type = Mock(return_value="sell")
        mock_settings.get_market_weighted_buy_ratio = Mock(return_value=0.3)
        mock_settings.get_custom_price = Mock(return_value=None)  # No custom price
        mock_get_settings.return_value = mock_settings

        with patch(
            "ui.tabs.asset_tree_tab.prices.get_latest_snapshot_prices"
        ) as mock_get_prices:
            mock_get_prices.return_value = {34: 5.0}  # Snapshot price

            def capture_price(assets):
                # Snapshot price should be applied
                assert assets[0].market_value == 5.0
                mock_root = Mock()
                mock_root.get_total_value = Mock(return_value=5000.0)
                mock_root.get_item_count = Mock(return_value=1)
                mock_root.location_name = "Test Location"
                mock_root.children = []
                return {"roots": [mock_root]}

            mock_services["asset_service"].build_asset_tree_from_assets = Mock(
                side_effect=capture_price
            )

            asset_tree_tab._current_characters = [mock_char]
            await asset_tree_tab._do_refresh()


@pytest.mark.asyncio
async def test_pricing_respects_trade_hub_preference(
    qtbot, asset_tree_tab, mock_services
):
    """Test that trade hub preference is used for pricing."""
    mock_char = Mock(character_id=123, character_name="Test", name="Test")
    mock_asset = Mock(type_id=34, quantity=1000, market_value=None)

    mock_services["asset_service"].get_all_enriched_assets = AsyncMock(
        return_value=[mock_asset]
    )

    with patch("ui.tabs.asset_tree_tab.get_settings_manager") as mock_get_settings:
        mock_settings = Mock()
        mock_settings.get_market_source_station = Mock(return_value="amarr")
        mock_settings.get_market_price_type = Mock(return_value="buy")
        mock_settings.get_market_weighted_buy_ratio = Mock(return_value=0.5)
        mock_settings.get_custom_price = Mock(return_value=None)
        mock_get_settings.return_value = mock_settings

        with patch(
            "ui.tabs.asset_tree_tab.prices.get_latest_snapshot_prices"
        ) as mock_get_prices:
            mock_get_prices.return_value = {}

            mock_services["asset_service"].build_asset_tree_from_assets = Mock(
                return_value={"roots": []}
            )

            asset_tree_tab._current_characters = [mock_char]
            await asset_tree_tab._do_refresh()

            # Verify correct region_id for Amarr (10000043)
            mock_get_prices.assert_called_once()
            call_kwargs = mock_get_prices.call_args[1]
            assert call_kwargs["region_id"] == 10000043
            assert call_kwargs["price_type"] == "buy"
            assert call_kwargs["weighted_buy_ratio"] == 0.5


@pytest.mark.asyncio
async def test_refresh_guard_cleared_on_exception(qtbot, asset_tree_tab, mock_services):
    """Test that refresh guard is cleared even if exception occurs."""
    # Mock exception during refresh
    mock_services["asset_service"].get_all_enriched_assets = AsyncMock(
        side_effect=Exception("Test error")
    )

    asset_tree_tab._current_characters = [Mock(character_id=123, name="Test")]

    # Trigger refresh (should raise exception but clear guard)
    await asset_tree_tab._do_refresh()

    # Guard should be cleared even after exception
    assert not asset_tree_tab._is_refreshing


@pytest.mark.asyncio
async def test_character_deduplication(qtbot, asset_tree_tab):
    """Test that duplicate characters are filtered out."""
    # Create duplicate characters with same ID
    char1 = Mock(character_id=123, name="Test 1")
    char2 = Mock(character_id=123, name="Test 2")  # Duplicate ID
    char3 = Mock(character_id=456, name="Test 3")

    deduped = asset_tree_tab._dedupe_characters([char1, char2, char3])

    # Should only have 2 unique characters
    assert len(deduped) == 2
    assert deduped[0].character_id == 123
    assert deduped[1].character_id == 456


def test_initial_refresh_guard_state(qtbot, asset_tree_tab):
    """Test that refresh guard starts as False."""
    assert not asset_tree_tab._is_refreshing
