"""Tests for Phase 1: Blueprint Display Enhancement.

Tests verify that blueprints display with (Copy) or (Original) suffixes
in the category name field for immediate visual identification.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from models.eve.asset import EveAsset
from services.asset_service import AssetService


@pytest.fixture
def mock_sde_provider():
    """Create mock SDE provider with blueprint type data."""
    sde = Mock()

    # Define which types are blueprints
    blueprint_types = {123, 124, 126}

    def get_type_for_id(type_id):
        mock_type = Mock()
        mock_type.name = (
            "Test Blueprint" if type_id in blueprint_types else "Regular Item"
        )
        mock_type.group_id = 10 if type_id in blueprint_types else 11
        mock_type.volume = 0.01
        mock_type.base_price = 1000000.0
        return mock_type

    def get_group_for_id(group_id):
        if group_id == 10:  # Blueprint group
            mock_group = Mock()
            mock_group.name = "Blueprint"
            mock_group.category_id = 1
            return mock_group
        # Regular group
        mock_group = Mock()
        mock_group.name = "Ship"
        mock_group.category_id = 2
        return mock_group

    def get_category_for_id(category_id):
        if category_id == 1:  # Blueprint category
            mock_category = Mock()
            mock_category.name = "Blueprint"
        else:  # Regular category
            mock_category = Mock()
            mock_category.name = "Ship"
        return mock_category

    sde.get_type_by_id = Mock(side_effect=get_type_for_id)
    sde.get_group_by_id = Mock(side_effect=get_group_for_id)
    sde.get_category_by_id = Mock(side_effect=get_category_for_id)
    # Mock blueprint type checking - type 123/124/126 are blueprints, 125 is not
    sde.is_blueprint = Mock(side_effect=lambda type_id: type_id in blueprint_types)

    return sde


@pytest.fixture
def asset_service(mock_sde_provider):
    """Create AssetService with mocked SDE."""
    service = AssetService(
        sde_provider=mock_sde_provider,
        location_service=Mock(),
        repository=Mock(),
        esi_client=None,
    )
    return service


class TestBlueprintDisplayEnhancement:
    """Test blueprint category name display enhancements."""

    def test_blueprint_copy_shows_copy_suffix(self, asset_service):
        """TEST-001: Blueprint copy displays '(Copy)' suffix in category name.

        REQ-001: Blueprint items must display their type (Copy/Original)
        in the category name field in the assets list UI
        """
        # Arrange
        asset = EveAsset(
            item_id=1001,
            type_id=123,
            quantity=1,
            location_id=60003760,
            location_type="station",
            location_flag="Hangar",
            is_singleton=False,
            is_blueprint_copy=True,  # This is a blueprint copy
        )

        # Act
        enriched = asset_service._enrich_asset(
            asset, character_id=1, character_name="TestChar"
        )

        # Assert
        # The category_name should be "Blueprint (Copy)" if mock returns "Blueprint"
        assert "(Copy)" in enriched.category_name
        assert enriched.category_name.endswith("(Copy)")
        assert enriched.is_blueprint_copy is True

    def test_blueprint_original_shows_original_suffix(self, asset_service):
        """TEST-002: Blueprint original displays '(Original)' suffix.

        REQ-001: Blueprint items must display their type (Copy/Original)
        in the category name field in the assets list UI
        """
        # Arrange
        asset = EveAsset(
            item_id=1002,
            type_id=124,
            quantity=1,
            location_id=60003760,
            location_type="station",
            location_flag="Hangar",
            is_singleton=True,  # Originals are singletons
            is_blueprint_copy=False,  # This is a blueprint original
        )

        # Act
        enriched = asset_service._enrich_asset(
            asset, character_id=1, character_name="TestChar"
        )

        # Assert
        assert "(Original)" in enriched.category_name
        assert enriched.category_name.endswith("(Original)")
        assert enriched.is_blueprint_copy is False

    def test_non_blueprint_unaffected(self, asset_service):
        """TEST-003: Non-blueprint items are NOT affected by this logic.

        REQ-001: Only blueprint items should have suffixes appended.
        Regular items should display their category name unchanged.
        """
        # Arrange
        asset = EveAsset(
            item_id=1003,
            type_id=125,
            quantity=100,
            location_id=60003760,
            location_type="station",
            location_flag="Hangar",
            is_singleton=False,
            is_blueprint_copy=None,  # Not a blueprint
        )

        # Act
        enriched = asset_service._enrich_asset(
            asset, character_id=1, character_name="TestChar"
        )

        # Assert
        # Should not have (Copy) or (Original) suffix
        assert "(Copy)" not in enriched.category_name
        assert "(Original)" not in enriched.category_name
        assert enriched.category_name == "Ship"  # Regular item category, no suffix
        assert enriched.is_blueprint_copy is None

    def test_category_name_format(self, asset_service):
        """TEST-004: Verify category name format consistency.

        Ensures the suffix is appended correctly with proper spacing.
        """
        # Arrange - blueprint copy
        asset_copy = EveAsset(
            item_id=1004,
            type_id=126,
            quantity=1,
            location_id=60003760,
            location_type="station",
            location_flag="Hangar",
            is_singleton=False,
            is_blueprint_copy=True,
        )

        # Act
        enriched_copy = asset_service._enrich_asset(
            asset_copy, character_id=1, character_name="TestChar"
        )

        # Assert - verify format: "BaseCategory (Copy)"
        parts = enriched_copy.category_name.rsplit(" (", 1)
        assert len(parts) == 2
        base_cat, suffix = parts
        assert suffix == "Copy)"
        assert base_cat == "Blueprint"

    def test_blueprint_copy_with_missing_sde_data(self):
        """TEST-005: Blueprint suffix handling when SDE data is missing.

        Edge case: SDE might not return complete data. Ensure graceful handling.
        """
        # Arrange
        sde = Mock()
        sde.get_type_by_id = Mock(return_value=None)  # No SDE data

        service = AssetService(
            sde_provider=sde,
            location_service=Mock(),
            repository=Mock(),
            esi_client=None,
        )

        asset = EveAsset(
            item_id=1005,
            type_id=127,
            quantity=1,
            location_id=60003760,
            location_type="station",
            location_flag="Hangar",
            is_singleton=False,
            is_blueprint_copy=True,
        )

        # Act - should not crash when SDE data missing
        enriched = service._enrich_asset(
            asset, character_id=1, character_name="TestChar"
        )

        # Assert
        # Even with no SDE data, the basic enrichment should work
        assert enriched.item_id == asset.item_id
        assert enriched.is_blueprint_copy is True
        # category_name might be empty if SDE failed, but enrichment should complete
        assert enriched.category_name == ""  # SDE returned None, so defaults to ""
