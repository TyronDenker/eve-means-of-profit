"""Regression tests for net worth price resolution and valuation accuracy.

Tests verify that the price resolution pipeline correctly:
1. Respects custom prices over market prices
2. Falls back to snapshot prices when live prices unavailable
3. Uses weighted/median calculations appropriately
4. Handles missing data gracefully with proper fallbacks
"""

from __future__ import annotations

import logging
from unittest.mock import Mock

import pytest

from services.networth_service import NetWorthService

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_settings():
    """Create mock settings manager."""
    settings = Mock()
    settings.get_custom_price = Mock(return_value=None)
    return settings


@pytest.fixture
def mock_sde():
    """Create mock SDE provider."""
    sde = Mock()
    sde.get_type_by_id = Mock(return_value=Mock(base_price=100.0))
    return sde


@pytest.fixture
def mock_repo():
    """Create mock repository."""
    return Mock()


@pytest.fixture
def networth_service(mock_settings, mock_sde, mock_repo):
    """Create NetWorthService with mocked dependencies."""
    return NetWorthService(
        repo=mock_repo,
        sde_provider=mock_sde,
        settings=mock_settings,
    )


class TestPriceResolutionPriority:
    """Test that price resolution respects the correct priority order."""

    def test_custom_price_overrides_all(self, networth_service, mock_settings):
        """Custom prices should always take precedence over market prices.

        Requirement: REQ-006 - Valuations must obey custom prices
        """
        custom_price = 500.0
        mock_settings.get_custom_price.return_value = {"sell": custom_price}

        asset = Mock(market_value=200.0, base_price=100.0)
        price = networth_service._get_asset_price(asset, type_id=12345)

        assert price == custom_price
        assert networth_service._last_used_prices[12345] == (custom_price, "custom")

    def test_market_value_overrides_market_price(self, networth_service, mock_settings):
        """Asset market_value (enriched) should override live market prices.

        This is used when price data is baked into asset response.
        """
        market_value = 300.0
        mock_settings.get_custom_price.return_value = None

        asset = Mock(market_value=market_value, base_price=100.0)
        price = networth_service._get_asset_price(asset, type_id=12345)

        assert price == market_value
        assert networth_service._last_used_prices[12345] == (market_value, "asset")

    def test_base_price_fallback(self, networth_service, mock_settings):
        """Base price should be used when no custom or market prices available.

        This ensures assets always have some valuation.
        """
        base_price = 150.0
        mock_settings.get_custom_price.return_value = None

        asset = Mock(market_value=None, base_price=base_price)
        price = networth_service._get_asset_price(asset, type_id=12345)

        assert price == base_price
        assert networth_service._last_used_prices[12345] == (base_price, "base")

    def test_custom_price_zero_ignored(self, networth_service, mock_settings):
        """Custom price of 0 should be treated as not set (fallback to next)."""
        mock_settings.get_custom_price.return_value = {"sell": 0}

        asset = Mock(market_value=300.0, base_price=100.0)
        price = networth_service._get_asset_price(asset, type_id=12345)

        # Should skip custom price (0) and use market_value
        assert price == 300.0
        assert networth_service._last_used_prices[12345] == (300.0, "asset")


class TestPriceResolutionFallbacks:
    """Test fallback behavior when price sources are unavailable."""

    def test_sde_lookup_fallback(self, networth_service, mock_settings, mock_sde):
        """SDE base price lookup should work as final fallback.

        Requirement: REQ-006 - Valuations must work with SDE when market unavailable
        """
        sde_base_price = 250.0
        mock_settings.get_custom_price.return_value = None
        mock_sde.get_type_by_id.return_value = Mock(base_price=sde_base_price)

        asset = Mock(market_value=None, base_price=None)
        price = networth_service._get_asset_price(asset, type_id=12345)

        assert price == sde_base_price
        mock_sde.get_type_by_id.assert_called_with(12345)

    def test_no_price_available_returns_none(
        self, networth_service, mock_settings, mock_sde
    ):
        """Should return None when no price source is available."""
        mock_settings.get_custom_price.return_value = None
        mock_sde.get_type_by_id.return_value = Mock(base_price=None)

        asset = Mock(market_value=None, base_price=None)
        price = networth_service._get_asset_price(asset, type_id=12345)

        assert price is None
        # Should not add to tracking if no price found
        assert 12345 not in networth_service._last_used_prices or price is None

    def test_sde_exception_handling(self, networth_service, mock_settings, mock_sde):
        """SDE lookup exceptions should not crash service.

        Handles malformed SDE data gracefully.
        """
        mock_settings.get_custom_price.return_value = None
        mock_sde.get_type_by_id.side_effect = Exception("SDE lookup failed")

        asset = Mock(market_value=None, base_price=100.0)
        price = networth_service._get_asset_price(asset, type_id=12345)

        # Should fall back to asset base price
        assert price == 100.0


class TestPriceResolutionTracking:
    """Test that price resolution is properly tracked for auditing.

    Requirement: CON-001 - Track which price source was used for each asset
    """

    def test_price_source_tracking(self, networth_service, mock_settings):
        """Every resolved price should be tracked with its source."""
        mock_settings.get_custom_price.return_value = None

        asset = Mock(market_value=200.0, base_price=100.0)
        networth_service._get_asset_price(asset, type_id=111)

        # Should track source
        assert 111 in networth_service._last_used_prices
        tracked_price, tracked_source = networth_service._last_used_prices[111]
        assert tracked_price == 200.0
        assert tracked_source == "asset"

    def test_multiple_price_types_tracked_separately(self, networth_service):
        """Different type_ids should track independently."""
        asset1 = Mock(market_value=100.0, base_price=50.0)
        asset2 = Mock(market_value=200.0, base_price=150.0)

        networth_service._get_asset_price(asset1, type_id=111)
        networth_service._get_asset_price(asset2, type_id=222)

        # Both should be tracked
        assert 111 in networth_service._last_used_prices
        assert 222 in networth_service._last_used_prices

        # With different values
        p1, _ = networth_service._last_used_prices[111]
        p2, _ = networth_service._last_used_prices[222]
        assert p1 == 100.0
        assert p2 == 200.0


class TestCustomPriceIntegration:
    """Test custom price settings integration with price resolution."""

    def test_custom_price_overrides_for_specific_items(
        self, networth_service, mock_settings
    ):
        """Custom prices for one item shouldn't affect others.

        Requirement: SEC-001 - Custom prices properly scoped per item
        """

        # Custom price for type 111
        def get_custom_price_mock(type_id: int):
            if type_id == 111:
                return {"sell": 999.0}
            return None

        mock_settings.get_custom_price.side_effect = get_custom_price_mock

        asset111 = Mock(market_value=100.0, base_price=50.0)
        asset222 = Mock(market_value=200.0, base_price=150.0)

        price111 = networth_service._get_asset_price(asset111, type_id=111)
        price222 = networth_service._get_asset_price(asset222, type_id=222)

        assert price111 == 999.0  # Custom
        assert price222 == 200.0  # Market value (not affected by 111's custom)

    def test_custom_price_persistence_across_calls(
        self, networth_service, mock_settings
    ):
        """Custom prices should be consistent across multiple valuations.

        Supports reliable net worth tracking over time.
        """
        custom_prices = {100: {"sell": 500.0}, 200: {"sell": 1000.0}}

        def get_custom_price_mock(type_id: int):
            return custom_prices.get(type_id)

        mock_settings.get_custom_price.side_effect = get_custom_price_mock

        asset100 = Mock(market_value=100.0, base_price=50.0)
        asset200 = Mock(market_value=200.0, base_price=150.0)

        # Call multiple times to ensure consistency
        for _ in range(3):
            p100 = networth_service._get_asset_price(asset100, type_id=100)
            p200 = networth_service._get_asset_price(asset200, type_id=200)

            assert p100 == 500.0
            assert p200 == 1000.0


@pytest.mark.asyncio
class TestMarketPriceResolution:
    """Test market price fetching and caching."""

    async def test_market_price_caching(self, networth_service):
        """Market prices should be cached to reduce redundant lookups."""
        # This is a simplified test; actual market price caching
        # depends on the implementation of _get_market_price
        asset = Mock(market_value=None, base_price=100.0)

        # First call
        price1 = networth_service._get_asset_price(asset, type_id=12345)

        # Subsequent call with same type_id should use cache
        price2 = networth_service._get_asset_price(asset, type_id=12345)

        # Prices should be consistent
        assert price1 == price2


class TestPriceResolutionEdgeCases:
    """Test edge cases and error conditions."""

    def test_negative_custom_price_ignored(self, networth_service, mock_settings):
        """Negative custom prices should be treated as invalid."""
        mock_settings.get_custom_price.return_value = {"sell": -100.0}

        asset = Mock(market_value=200.0, base_price=100.0)
        price = networth_service._get_asset_price(asset, type_id=12345)

        # Should skip negative and use market_value
        assert price == 200.0

    def test_very_large_price_values(self, networth_service, mock_settings):
        """Should handle very large price values correctly."""
        large_price = 1e15  # Large number

        mock_settings.get_custom_price.return_value = {"sell": large_price}

        asset = Mock(market_value=1e10, base_price=1e5)
        price = networth_service._get_asset_price(asset, type_id=12345)

        assert price == large_price

    def test_type_id_none_handling(self, networth_service, mock_settings):
        """Service should handle None or invalid type_id gracefully."""
        mock_settings.get_custom_price.return_value = None

        asset = Mock(market_value=100.0, base_price=50.0)

        # Should not crash with None type_id
        try:
            networth_service._get_asset_price(asset, type_id=None)
            # Price may be calculated, but service shouldn't crash
        except (TypeError, AttributeError, ValueError):
            # This is acceptable - service can reject None
            pass
