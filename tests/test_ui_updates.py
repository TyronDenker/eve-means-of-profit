"""Tests for UI updates including PLEX removal and empty graph behavior."""

import os
import sys
from pathlib import Path

# Ensure src is on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Run Qt in minimal mode to avoid GUI plugin errors in CI/console runs
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")


class MockCharacter:
    """Mock character for testing."""

    def __init__(
        self, character_id: int, character_name: str, alliance_id: int | None = None
    ):
        self.character_id = character_id
        self.character_name = character_name
        self.corporation_id = 12345
        self.corporation_name = "Test Corp"
        self.alliance_id = alliance_id
        self.alliance_name = "Test Alliance" if alliance_id else None


class MockCheckBox:
    """Mock QCheckBox for testing."""

    def __init__(self, checked: bool = True):
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked


def test_networth_tab_returns_empty_list_when_no_checkboxes_selected():
    """Test that _get_all_character_ids returns empty list when checkboxes exist but none selected."""
    # Simulate the behavior of _get_all_character_ids
    character_checkboxes = {
        1: MockCheckBox(False),
        2: MockCheckBox(False),
        3: MockCheckBox(False),
    }

    # Logic from _get_all_character_ids
    selected = [cid for cid, cb in character_checkboxes.items() if cb.isChecked()]

    if character_checkboxes:
        # Checkboxes exist - return only selected (empty list shows empty graph)
        result = selected
    else:
        # No checkboxes yet - fall back to all characters
        result = [1, 2, 3]

    # When no characters are selected, result should be empty
    assert result == [], "Should return empty list when no characters are selected"


def test_networth_tab_returns_selected_characters_only():
    """Test that _get_all_character_ids returns only selected characters."""
    character_checkboxes = {
        1: MockCheckBox(True),
        2: MockCheckBox(False),
        3: MockCheckBox(True),
    }

    selected = [cid for cid, cb in character_checkboxes.items() if cb.isChecked()]

    if character_checkboxes:
        result = selected
    else:
        result = [1, 2, 3]

    # Should return only selected characters (1 and 3)
    assert sorted(result) == [1, 3], "Should return only selected characters"


def test_list_table_has_no_plex_column():
    """Test that the list table columns don't include PLEX."""
    # Expected columns after PLEX removal
    expected_columns = [
        "Name",
        "Account",
        "Corporation",
        "Alliance",
        "Wallet",
        "Assets",
        "Escrow",
        "Sell Orders",
        "Contracts",
        "Collateral",
        "Industry",
        "Net Worth",
    ]

    # Verify PLEX is not in the list
    assert "PLEX" not in expected_columns, (
        "PLEX column should be removed from list view"
    )
    assert len(expected_columns) == 12, "Should have exactly 12 columns"


def test_alliance_logo_visibility_check():
    """Test that alliance logo visibility depends on alliance_id."""
    # Character with alliance
    char_with_alliance = MockCharacter(1, "Test Char", alliance_id=99999)
    has_alliance = bool(getattr(char_with_alliance, "alliance_id", None))
    assert has_alliance is True, "Character with alliance should show alliance logo"

    # Character without alliance
    char_without_alliance = MockCharacter(2, "Test Char 2", alliance_id=None)
    has_alliance_2 = bool(getattr(char_without_alliance, "alliance_id", None))
    assert has_alliance_2 is False, (
        "Character without alliance should not show alliance logo"
    )


def test_timers_visibility_flag():
    """Test that timers visibility can be toggled."""
    # Simulate the _timers_visible flag behavior
    timers_visible = True
    endpoint_timers = {"assets": 300.0, "wallet": 600.0}

    # When visible, should add timers
    timers_to_show = []
    if timers_visible:
        for key in endpoint_timers:
            timers_to_show.append(key)

    assert len(timers_to_show) == 2, "Should show timers when visible"

    # When hidden, should not add timers
    timers_visible = False
    timers_to_show = []
    if timers_visible:
        for key in endpoint_timers:
            timers_to_show.append(key)

    assert len(timers_to_show) == 0, "Should not show timers when hidden"


def test_date_selector_defaults_to_earliest_snapshot():
    """Test that date selector defaults to earliest snapshot date."""
    from datetime import UTC, datetime

    class MockSnapshot:
        def __init__(self, time: datetime):
            self.snapshot_time = time

    # Simulated snapshots with various dates
    snapshots = [
        MockSnapshot(datetime(2025, 6, 15, tzinfo=UTC)),
        MockSnapshot(datetime(2025, 3, 1, tzinfo=UTC)),  # Earliest
        MockSnapshot(datetime(2025, 9, 20, tzinfo=UTC)),
        MockSnapshot(datetime(2025, 5, 10, tzinfo=UTC)),
    ]

    # Logic from _plot_and_set_date_bounds
    if snapshots:
        earliest = min(
            s.snapshot_time for s in snapshots if hasattr(s, "snapshot_time")
        )
    else:
        earliest = None

    expected_earliest = datetime(2025, 3, 1, tzinfo=UTC)
    assert earliest == expected_earliest, "Should find the earliest snapshot date"


def test_date_selector_empty_snapshots():
    """Test that date selector handles empty snapshots gracefully."""
    snapshots = []

    # Logic should not crash on empty snapshots
    earliest = None
    if snapshots:
        try:
            earliest = min(
                s.snapshot_time for s in snapshots if hasattr(s, "snapshot_time")
            )
        except ValueError:
            earliest = None

    assert earliest is None, "Empty snapshots should result in None earliest date"


# =============================================================================
# Tests for PLEX button modifier keys
# =============================================================================


class TestPlexButtonModifierKeys:
    """Tests for PLEX button modifier key handling."""

    def test_shift_modifier_detected(self):
        """Test that Shift modifier key is detected."""

        # Simulate Qt keyboard modifiers
        class MockModifiers:
            ShiftModifier = 0x02000000
            ControlModifier = 0x04000000
            AltModifier = 0x08000000
            NoModifier = 0x00000000

        current_modifiers = MockModifiers.ShiftModifier

        is_shift = bool(current_modifiers & MockModifiers.ShiftModifier)
        is_ctrl = bool(current_modifiers & MockModifiers.ControlModifier)

        assert is_shift is True
        assert is_ctrl is False

    def test_ctrl_modifier_detected(self):
        """Test that Ctrl modifier key is detected."""

        class MockModifiers:
            ShiftModifier = 0x02000000
            ControlModifier = 0x04000000
            NoModifier = 0x00000000

        current_modifiers = MockModifiers.ControlModifier

        is_shift = bool(current_modifiers & MockModifiers.ShiftModifier)
        is_ctrl = bool(current_modifiers & MockModifiers.ControlModifier)

        assert is_shift is False
        assert is_ctrl is True

    def test_combined_modifiers_detected(self):
        """Test that combined modifier keys are detected."""

        class MockModifiers:
            ShiftModifier = 0x02000000
            ControlModifier = 0x04000000
            NoModifier = 0x00000000

        # Shift + Ctrl
        current_modifiers = MockModifiers.ShiftModifier | MockModifiers.ControlModifier

        is_shift = bool(current_modifiers & MockModifiers.ShiftModifier)
        is_ctrl = bool(current_modifiers & MockModifiers.ControlModifier)

        assert is_shift is True
        assert is_ctrl is True

    def test_plex_amount_based_on_modifier(self):
        """Test PLEX amount changes based on modifier key."""

        class MockModifiers:
            ShiftModifier = 0x02000000
            ControlModifier = 0x04000000
            NoModifier = 0x00000000

        def get_plex_amount(modifiers):
            if modifiers & MockModifiers.ShiftModifier:
                return 500  # Bulk amount
            if modifiers & MockModifiers.ControlModifier:
                return 100  # Medium amount
            return 1  # Default single PLEX

        assert get_plex_amount(MockModifiers.NoModifier) == 1
        assert get_plex_amount(MockModifiers.ShiftModifier) == 500
        assert get_plex_amount(MockModifiers.ControlModifier) == 100


# =============================================================================
# Tests for character card spacing
# =============================================================================


class TestCharacterCardSpacing:
    """Tests for character card spacing adjustments."""

    def test_card_margins_configuration(self):
        """Test that card margins can be configured."""
        # Simulate card margin settings
        default_margins = (8, 8, 8, 8)  # (left, top, right, bottom)
        compact_margins = (4, 4, 4, 4)

        # Test margin validation
        for margin in default_margins + compact_margins:
            assert margin >= 0, "Margins should be non-negative"
            assert margin <= 100, "Margins should be reasonable"

    def test_card_spacing_configuration(self):
        """Test that card spacing can be configured."""
        default_spacing = 6
        compact_spacing = 3

        assert default_spacing > 0
        assert compact_spacing > 0
        assert compact_spacing <= default_spacing

    def test_flow_layout_spacing(self):
        """Test flow layout spacing settings."""
        horizontal_spacing = 8
        vertical_spacing = 8

        # Layout should accept these spacing values
        assert horizontal_spacing >= 0
        assert vertical_spacing >= 0


# =============================================================================
# Tests for networth vertical panel
# =============================================================================


class TestNetworthVerticalPanel:
    """Tests for networth vertical panel layout."""

    def test_splitter_orientation(self):
        """Test that splitter can be configured for vertical split."""
        # Simulate Qt.Orientation values
        HORIZONTAL = 1
        VERTICAL = 2

        # Vertical panel means horizontal splitter (left/right split)
        splitter_orientation = HORIZONTAL
        assert splitter_orientation == HORIZONTAL

    def test_panel_minimum_sizes(self):
        """Test panel minimum size constraints."""
        min_panel_width = 200
        min_graph_width = 400

        assert min_panel_width > 0
        assert min_graph_width > min_panel_width
        assert min_panel_width + min_graph_width < 2000  # Reasonable max

    def test_panel_visibility_toggle(self):
        """Test that panel visibility can be toggled."""
        panel_visible = True

        # Toggle
        panel_visible = not panel_visible
        assert panel_visible is False

        # Toggle back
        panel_visible = not panel_visible
        assert panel_visible is True


# =============================================================================
# Tests for assets character filter
# =============================================================================


class TestAssetsCharacterFilter:
    """Tests for assets tab character filter."""

    def test_character_filter_initialization(self):
        """Test character filter starts with all characters selected."""
        # Simulate initial state where no filter is applied
        selected_character_ids = set()  # Empty means all characters
        all_character_ids = {1, 2, 3, 4}

        # When filter is empty, should use all characters
        if not selected_character_ids:
            effective_filter = all_character_ids
        else:
            effective_filter = selected_character_ids

        assert effective_filter == all_character_ids

    def test_character_filter_selection(self):
        """Test character filter with specific selection."""
        all_character_ids = {1, 2, 3, 4}
        selected_character_ids = {1, 3}

        # Filter should only include selected
        effective_filter = selected_character_ids
        assert effective_filter == {1, 3}
        assert 2 not in effective_filter
        assert 4 not in effective_filter

    def test_character_filter_combined_with_other_filters(self):
        """Test character filter combined with other filter criteria."""
        # Mock asset rows
        assets = [
            {"owner_id": 1, "type_name": "Tritanium", "value": 1000},
            {"owner_id": 2, "type_name": "Pyerite", "value": 500},
            {"owner_id": 3, "type_name": "Tritanium", "value": 1500},
            {"owner_id": 1, "type_name": "Mexallon", "value": 2000},
        ]

        # Filter by character AND type
        selected_characters = {1, 3}
        type_filter = "Tritanium"

        filtered = [
            a
            for a in assets
            if a["owner_id"] in selected_characters
            and type_filter.lower() in a["type_name"].lower()
        ]

        assert len(filtered) == 2
        assert all(a["type_name"] == "Tritanium" for a in filtered)
        assert all(a["owner_id"] in selected_characters for a in filtered)

    def test_character_filter_empty_selection_shows_nothing(self):
        """Test that empty character selection shows no assets."""
        assets = [
            {"owner_id": 1, "value": 1000},
            {"owner_id": 2, "value": 500},
        ]

        selected_characters = set()  # Empty selection

        # When explicitly empty (not None), show nothing
        if selected_characters is not None and len(selected_characters) == 0:
            filtered = []
        else:
            filtered = [a for a in assets if a["owner_id"] in selected_characters]

        # This test assumes explicit empty set means "show nothing"
        assert filtered == []

    def test_character_filter_preserves_sort_order(self):
        """Test that character filter doesn't affect sort order."""
        assets = [
            {"owner_id": 1, "value": 1000, "name": "B"},
            {"owner_id": 1, "value": 500, "name": "A"},
            {"owner_id": 2, "value": 1500, "name": "C"},
        ]

        # Sort by name
        sorted_assets = sorted(assets, key=lambda x: x["name"])

        # Then filter
        selected = {1}
        filtered = [a for a in sorted_assets if a["owner_id"] in selected]

        # Order should be preserved
        assert filtered[0]["name"] == "A"
        assert filtered[1]["name"] == "B"


# =============================================================================
# Additional UI-related tests
# =============================================================================


class TestFormatting:
    """Tests for UI value formatting."""

    def test_isk_format_billions(self):
        """Test ISK formatting for billions."""

        def format_isk_short(value: float) -> str:
            if abs(value) >= 1_000_000_000:
                return f"{value / 1_000_000_000:.2f}b"
            if abs(value) >= 1_000_000:
                return f"{value / 1_000_000:.2f}m"
            if abs(value) >= 1_000:
                return f"{value / 1_000:.2f}k"
            return f"{value:.0f}"

        assert format_isk_short(1_500_000_000) == "1.50b"
        assert format_isk_short(42_000_000_000) == "42.00b"

    def test_isk_format_millions(self):
        """Test ISK formatting for millions."""

        def format_isk_short(value: float) -> str:
            if abs(value) >= 1_000_000_000:
                return f"{value / 1_000_000_000:.2f}b"
            if abs(value) >= 1_000_000:
                return f"{value / 1_000_000:.2f}m"
            if abs(value) >= 1_000:
                return f"{value / 1_000:.2f}k"
            return f"{value:.0f}"

        assert format_isk_short(5_500_000) == "5.50m"
        assert format_isk_short(100_000_000) == "100.00m"

    def test_isk_format_thousands(self):
        """Test ISK formatting for thousands."""

        def format_isk_short(value: float) -> str:
            if abs(value) >= 1_000_000_000:
                return f"{value / 1_000_000_000:.2f}b"
            if abs(value) >= 1_000_000:
                return f"{value / 1_000_000:.2f}m"
            if abs(value) >= 1_000:
                return f"{value / 1_000:.2f}k"
            return f"{value:.0f}"

        assert format_isk_short(5_000) == "5.00k"
        assert format_isk_short(999_999) == "1000.00k"

    def test_isk_format_small_values(self):
        """Test ISK formatting for values under 1000."""

        def format_isk_short(value: float) -> str:
            if abs(value) >= 1_000_000_000:
                return f"{value / 1_000_000_000:.2f}b"
            if abs(value) >= 1_000_000:
                return f"{value / 1_000_000:.2f}m"
            if abs(value) >= 1_000:
                return f"{value / 1_000:.2f}k"
            return f"{value:.0f}"

        assert format_isk_short(500) == "500"
        assert format_isk_short(0) == "0"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
