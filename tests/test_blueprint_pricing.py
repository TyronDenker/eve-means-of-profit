"""Tests for Phase 2: Blueprint Copy Pricing.

Tests verify that blueprint copies are priced at 0.0 ISK across all pricing contexts
unless a custom price is set to override this default.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from services.networth_service import NetWorthService


@pytest.fixture
def mock_settings():
    """Create mock settings manager."""
    settings = Mock()
    settings.get_custom_price = Mock(return_value=None)
    settings.get_market_source_station = Mock(return_value="jita")
    settings.get_market_price_type = Mock(return_value="sell")
    settings.get_market_weighted_buy_ratio = Mock(return_value=0.3)
    return settings


@pytest.fixture
def mock_sde():
    """Create mock SDE provider."""
    sde = Mock()
    sde.get_type_by_id = Mock(return_value=Mock(base_price=100.0))
    return sde


@pytest.fixture
def mock_fuzzwork():
    """Create mock Fuzzwork provider."""
    fuzzwork = Mock()
    fuzzwork.is_loaded = True
    fuzzwork.get_market_data = Mock(
        return_value=Mock(
            region_data={
                10000002: Mock(
                    sell_stats=Mock(median=500.0), buy_stats=Mock(median=400.0)
                )
            }
        )
    )
    return fuzzwork


@pytest.fixture
def mock_repo():
    """Create mock repository."""
    return Mock()


@pytest.fixture
def networth_service(mock_settings, mock_sde, mock_fuzzwork, mock_repo):
    """Create NetWorthService with mocked dependencies."""
    return NetWorthService(
        esi_client=Mock(),
        repository=mock_repo,
        fuzzwork_provider=mock_fuzzwork,
        settings_manager=mock_settings,
        sde_provider=mock_sde,
        location_service=Mock(),
    )


class TestBlueprintCopyPricing:
    """Test blueprint copy 0-pricing in all contexts."""

    def test_blueprint_copy_returns_zero(self, networth_service):
        """TEST-004: Blueprint copies return 0.0 price when no custom price exists.

        REQ-003: Blueprint copies must have market_value set to 0.0
        REQ-004: Custom prices override the 0.0 default
        """
        # Arrange
        blueprint_copy = Mock(
            is_blueprint_copy=True, market_value=None, base_price=1000000.0
        )

        # Act
        price = networth_service._get_asset_price(blueprint_copy, type_id=12345)

        # Assert
        assert price == 0.0
        assert networth_service._last_used_prices[12345] == (0.0, "blueprint-copy")

    def test_blueprint_copy_with_custom_price_uses_custom(
        self, networth_service, mock_settings
    ):
        """TEST-005: Blueprint copies with custom prices use the custom price.

        REQ-004: Custom prices must override the 0.0 default for blueprint copies
        """
        # Arrange
        custom_price = 2500000.0
        mock_settings.get_custom_price = Mock(return_value={"sell": custom_price})

        blueprint_copy = Mock(
            is_blueprint_copy=True, market_value=None, base_price=1000000.0
        )

        # Act
        price = networth_service._get_asset_price(blueprint_copy, type_id=12345)

        # Assert
        assert price == custom_price
        # Custom price should be preferred
        assert networth_service._last_used_prices[12345] == (custom_price, "custom")

    def test_blueprint_original_uses_normal_pricing(self, networth_service):
        """TEST-006: Blueprint originals are priced normally.

        REQ-001: Only blueprint COPIES should be priced at 0.0
        Blueprint originals should use the standard price priority:
        Custom > Asset market_value > Market price > Base price
        """
        # Arrange
        blueprint_original = Mock(
            is_blueprint_copy=False,  # This is a blueprint ORIGINAL, not copy
            market_value=500000.0,  # Should use this
            base_price=1000000.0,
        )

        # Act
        price = networth_service._get_asset_price(blueprint_original, type_id=12345)

        # Assert
        # Should use market_value, not 0.0
        assert price == 500000.0
        assert networth_service._last_used_prices[12345] == (500000.0, "asset")

    def test_blueprint_copy_zero_not_affected_by_base_price(self, networth_service):
        """TEST-007: Blueprint copy 0-pricing doesn't get overridden by base price.

        REQ-003: Blueprint copy pricing must be 0.0, not influenced by base price.
        """
        # Arrange
        blueprint_copy = Mock(
            is_blueprint_copy=True,
            market_value=None,
            base_price=10000000.0,  # Very high base price
        )

        # Act
        price = networth_service._get_asset_price(blueprint_copy, type_id=12345)

        # Assert
        # Should still return 0.0, not the base price
        assert price == 0.0
        assert networth_service._last_used_prices[12345] == (0.0, "blueprint-copy")

    def test_blueprint_copy_zero_not_affected_by_market_price(self, networth_service):
        """TEST-008: Blueprint copy 0-pricing doesn't get overridden by market data.

        REQ-003: Blueprint copy pricing must be 0.0, even when market data exists.
        """
        # Arrange - market data exists but should be ignored for blueprint copies
        blueprint_copy = Mock(
            is_blueprint_copy=True, market_value=None, base_price=100.0
        )

        # Act
        price = networth_service._get_asset_price(blueprint_copy, type_id=12345)

        # Assert
        # Should be 0.0, not the market price (500.0 from mock)
        assert price == 0.0
        assert networth_service._last_used_prices[12345] == (0.0, "blueprint-copy")

    def test_blueprint_copy_custom_zero_treated_as_override(
        self, networth_service, mock_settings
    ):
        """TEST-009: Custom price of 0.0 is treated as explicit override.

        If a user explicitly sets a custom price to 0.0, it should be honored
        as the highest priority override.
        """
        # Arrange
        mock_settings.get_custom_price = Mock(return_value={"sell": 0.0})

        blueprint_copy = Mock(
            is_blueprint_copy=True, market_value=None, base_price=100.0
        )

        # Act
        price = networth_service._get_asset_price(blueprint_copy, type_id=12345)

        # Assert - 0.0 custom price is now honored as custom override
        # Fixed implementation: "if custom_price is not None" (removed "> 0" check)
        # Custom price always takes precedence over blueprint logic
        assert price == 0.0
        assert networth_service._last_used_prices[12345] == (0.0, "custom")

    def test_regular_item_unaffected_by_blueprint_logic(self, networth_service):
        """TEST-010: Regular items are not affected by blueprint pricing.

        REQ-003: Blueprint copy pricing should only apply to items with is_blueprint_copy=True
        """
        # Arrange - regular item with is_blueprint_copy not set or False
        regular_item = Mock(
            is_blueprint_copy=None,  # Not a blueprint
            market_value=None,
            base_price=1000.0,
        )

        # Act
        price = networth_service._get_asset_price(regular_item, type_id=12345)

        # Assert
        # Should use market price from fuzzwork (500.0 from mock), not 0.0
        assert price == 500.0
        assert networth_service._last_used_prices[12345] == (500.0, "market")
