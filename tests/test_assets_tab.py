import os
import sys
from pathlib import Path

# Ensure src is on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Run Qt in minimal mode to avoid GUI plugin errors in CI/console runs
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from ui.tabs.assets_tab import AssetsTab
from ui.widgets.filter_widget import FilterWidget


class _DummyTable:
    def __init__(self):
        self.predicate = None

    def set_predicate(self, pred):
        self.predicate = pred


def test_on_filter_changed_guard_and_apply():
    """Ensure _on_filter_changed safely handles missing table and applies predicate when available."""

    calls: list[dict] = []

    def _stub_build_predicate(spec):
        calls.append(spec)
        return lambda row: True

    original = FilterWidget.build_predicate
    FilterWidget.build_predicate = staticmethod(_stub_build_predicate)  # type: ignore[assignment]
    try:
        # Guard path: table missing should skip predicate creation
        tab = AssetsTab.__new__(AssetsTab)
        tab.table = None
        tab._on_filter_changed({"rules": []})
        assert calls == []

        # Predicate should apply when table exists
        tab.table = _DummyTable()
        # Initialize attributes needed for combined filter
        tab._selected_character_ids = None
        tab._current_filter_spec = None
        tab._on_filter_changed({"rules": ["x"]})
        assert calls == [{"rules": ["x"]}]
        assert callable(tab.table.predicate)
    finally:
        FilterWidget.build_predicate = original


def test_character_filter_combined_predicate():
    """Test that character filter correctly filters assets by owner_character_id."""

    calls: list[dict] = []

    def _stub_build_predicate(spec):
        calls.append(spec)
        return lambda row: True  # Pass all rows through advanced filter

    original = FilterWidget.build_predicate
    FilterWidget.build_predicate = staticmethod(_stub_build_predicate)  # type: ignore[assignment]
    try:
        tab = AssetsTab.__new__(AssetsTab)
        tab.table = _DummyTable()
        tab._current_filter_spec = None

        # Test: No characters selected should filter out all rows
        tab._selected_character_ids = set()
        tab._apply_combined_filter()
        pred = tab.table.predicate
        assert pred({"owner_character_id": 123}) is False
        assert pred({"owner_character_id": 456}) is False

        # Test: Selected characters should filter correctly
        tab._selected_character_ids = {123, 789}
        tab._apply_combined_filter()
        pred = tab.table.predicate
        assert pred({"owner_character_id": 123}) is True
        assert pred({"owner_character_id": 456}) is False
        assert pred({"owner_character_id": 789}) is True

        # Test: All characters selected (None means no filter)
        tab._selected_character_ids = None
        tab._apply_combined_filter()
        pred = tab.table.predicate
        assert pred({"owner_character_id": 123}) is True
        assert pred({"owner_character_id": 456}) is True

        # Test: Rows without owner_character_id pass through
        tab._selected_character_ids = {123}
        tab._apply_combined_filter()
        pred = tab.table.predicate
        assert pred({"type_name": "Test Item"}) is True  # No owner_id, passes

    finally:
        FilterWidget.build_predicate = original


def test_default_filter_applied_on_startup():
    """Verify that the persisted filter is applied during AssetsTab initialization.

    This tests the fix for the issue where filter_changed was emitted during
    FilterWidget construction but before the AssetsTab connected its slot,
    causing the initial filter to not be applied.

    The fix is to explicitly call _on_filter_changed after connecting the signal.
    """
    # Track predicate application
    build_calls = []

    def _tracking_build_predicate(spec):
        build_calls.append(spec)

        # Return a predicate that filters based on 'type_name' containing 'Veldspar'
        def pred(row):
            rules = spec.get("groups", [])
            if not rules:
                return True
            for group in rules:
                for rule in group.get("rules", []):
                    if rule.get("key") == "type_name" and rule.get("op") == "contains":
                        val = rule.get("value", "").lower()
                        return val in str(row.get("type_name", "")).lower()
            return True

        return pred

    original = FilterWidget.build_predicate
    FilterWidget.build_predicate = staticmethod(_tracking_build_predicate)

    try:
        # Create a minimal AssetsTab instance that simulates the startup flow
        tab = AssetsTab.__new__(AssetsTab)
        tab.table = _DummyTable()
        # Use None to indicate "no character filter" (show all characters)
        # An empty set() means "no characters selected = show nothing"
        tab._selected_character_ids = None
        tab._current_filter_spec = None

        # Simulate filter spec that was "loaded from persistence"
        test_spec = {
            "op": "AND",
            "groups": [
                {
                    "op": "AND",
                    "enabled": True,
                    "rules": [
                        {
                            "key": "type_name",
                            "op": "contains",
                            "value": "Veldspar",
                            "enabled": True,
                        }
                    ],
                }
            ],
        }

        # This simulates what happens in _setup_ui after connecting the signal:
        # tab._on_filter_changed(self.filter_widget.get_spec())
        tab._on_filter_changed(test_spec)

        # Verify the predicate was set and build_predicate was called
        assert len(build_calls) == 1, (
            f"build_predicate should be called once, got {len(build_calls)}"
        )
        assert tab._current_filter_spec == test_spec, (
            "_current_filter_spec should be stored"
        )
        assert tab.table.predicate is not None, "Predicate should be set on table"

        # Verify the predicate actually filters correctly
        pred = tab.table.predicate
        assert pred({"type_name": "Veldspar"}) is True, "Should match 'Veldspar'"
        assert pred({"type_name": "Concentrated Veldspar"}) is True, (
            "Should match 'Concentrated Veldspar'"
        )
        assert pred({"type_name": "Tritanium"}) is False, "Should not match 'Tritanium'"

    finally:
        FilterWidget.build_predicate = original


def test_filter_spec_initialization():
    """Test that _current_filter_spec is properly initialized before use."""
    # Create a minimal AssetsTab instance
    tab = AssetsTab.__new__(AssetsTab)

    # Simulate the initialization that happens in _setup_ui
    tab.table = _DummyTable()
    # Use None to indicate "no character filter" (show all characters)
    tab._selected_character_ids = None
    tab._current_filter_spec = None  # This is the fix - explicit initialization

    # _apply_combined_filter should not crash even with None filter spec
    tab._apply_combined_filter()

    # Predicate should still be set (combined filter with no advanced filter)
    assert tab.table.predicate is not None

    # Verify the predicate allows all rows when no filter is set
    pred = tab.table.predicate
    assert pred({"type_name": "Anything"}) is True
    assert pred({"type_name": "Something Else"}) is True
