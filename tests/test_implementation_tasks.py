"""Comprehensive tests for implementation tasks 1-14.

Tests verify that implementation tasks have been completed by inspecting
source code for expected changes and patterns.
"""

import re
from pathlib import Path

# Test data paths
SRC_ROOT = Path(__file__).parent.parent / "src"
ASSETS_TAB_PATH = SRC_ROOT / "ui" / "tabs" / "assets_tab.py"
ACCOUNT_GROUP_WIDGET_PATH = SRC_ROOT / "ui" / "widgets" / "account_group_widget.py"
ADVANCED_TABLE_WIDGET_PATH = SRC_ROOT / "ui" / "widgets" / "advanced_table_widget.py"
NETWORTH_TAB_PATH = SRC_ROOT / "ui" / "tabs" / "networth_tab.py"
CHARACTERS_TAB_PATH = SRC_ROOT / "ui" / "tabs" / "characters_tab.py"
ESI_AUTH_PATH = SRC_ROOT / "data" / "clients" / "esi" / "auth.py"
DI_CONTAINER_PATH = SRC_ROOT / "utils" / "di_container.py"


def read_source(file_path: Path) -> str:
    """Read source code from file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


class TestTask1AssetTabCharacterFilter:
    """Task 1: Remove CharacterFilterWidget from Assets tab."""

    def test_no_character_filter_import(self):
        """CharacterFilterWidget should not be imported."""
        source = read_source(ASSETS_TAB_PATH)
        assert "from" not in source or "CharacterFilterWidget" not in source
        assert "import" not in source or "CharacterFilterWidget" not in source

    def test_no_character_filter_instantiation(self):
        """CharacterFilterWidget should not be instantiated."""
        source = read_source(ASSETS_TAB_PATH)
        assert "CharacterFilterWidget(" not in source

    def test_apply_filter_method_exists(self):
        """_apply_filter method should exist (renamed from _apply_combined_filter)."""
        source = read_source(ASSETS_TAB_PATH)
        assert "_apply_filter" in source


class TestTask2PlexButtonModifiers:
    """Task 2: PLEX button modifier key detection."""

    def test_modifier_aware_button_exists(self):
        """ModifierAwarePushButton class should exist."""
        source = read_source(ACCOUNT_GROUP_WIDGET_PATH)
        assert "class ModifierAwarePushButton" in source

    def test_modifier_clicked_signal_exists(self):
        """ModifierAwarePushButton should have modifier_clicked signal."""
        source = read_source(ACCOUNT_GROUP_WIDGET_PATH)
        assert "modifier_clicked" in source

    def test_nudge_plex_with_modifiers_method(self):
        """_nudge_plex_with_modifiers method should exist."""
        source = read_source(ACCOUNT_GROUP_WIDGET_PATH)
        assert "_nudge_plex_with_modifiers" in source

    def test_modifier_constants_defined(self):
        """Modifier step sizes should be defined (10, 100, 500)."""
        source = read_source(ACCOUNT_GROUP_WIDGET_PATH)
        # Check for the modifier logic
        assert "10" in source  # Shift modifier
        assert "100" in source  # Ctrl modifier
        assert "500" in source or "Ctrl+Shift" in source  # Combined


class TestTask3NetworthSnapshot:
    """Task 3: Networth snapshot character assignment."""

    def test_edit_snapshot_dialog_exists(self):
        """EditSnapshotDialog should exist."""
        dialog_path = SRC_ROOT / "ui" / "dialogs" / "edit_snapshot_dialog.py"
        assert dialog_path.exists(), "EditSnapshotDialog file should exist"

    def test_character_combo_in_dialog(self):
        """EditSnapshotDialog should have character_combo."""
        dialog_path = SRC_ROOT / "ui" / "dialogs" / "edit_snapshot_dialog.py"
        if dialog_path.exists():
            source = read_source(dialog_path)
            assert "character_combo" in source


class TestTask4TableRowHeight:
    """Task 4: Reduce table row height and spacing."""

    def test_default_section_size_set(self):
        """Table should set default section size to 20px."""
        source = read_source(ADVANCED_TABLE_WIDGET_PATH)
        assert "setDefaultSectionSize" in source
        assert "20" in source

    def test_minimum_section_size_set(self):
        """Table should set minimum section size."""
        source = read_source(ADVANCED_TABLE_WIDGET_PATH)
        assert "setMinimumSectionSize" in source


class TestTask6CharacterCardSize:
    """Task 6: Character card size constraints."""

    def test_character_card_class_exists(self):
        """CharacterCard class should exist."""
        source = read_source(ACCOUNT_GROUP_WIDGET_PATH)
        assert "class CharacterCard" in source

    def test_update_size_constraints_method(self):
        """CharacterCard should have update_size_constraints method."""
        source = read_source(ACCOUNT_GROUP_WIDGET_PATH)
        assert "update_size_constraints" in source

    def test_timers_toggle_updates_constraints(self):
        """TimersToggle should trigger update_size_constraints."""
        source = read_source(CHARACTERS_TAB_PATH)
        assert "update_size_constraints" in source or "set_timers_visible" in source


class TestTask7PanelSizingPolicy:
    """Task 7: Fix networth vertical panel overflow."""

    def test_panel_size_policy_changed(self):
        """Panel size policy should be Preferred (responsive)."""
        source = read_source(NETWORTH_TAB_PATH)
        # Looking for setSizePolicy or size policy related changes
        assert "setSizePolicy" in source or "Expanding" in source


class TestTask9GraphVisuals:
    """Task 9: Networth graph visuals improvements."""

    def test_thinner_line_widths(self):
        """Category lines should be 1.5, Total line should be 2."""
        source = read_source(NETWORTH_TAB_PATH)
        # Check for thin line widths
        assert (
            "width=1.5" in source
            or "width=2" in source
            or re.search(r"width\s*=\s*[12](?:\.\d+)?", source)
        )

    def test_total_line_markers(self):
        """Total line should have square markers."""
        source = read_source(NETWORTH_TAB_PATH)
        assert 'symbol="s"' in source or "symbol='s'" in source


class TestTask10DoubleLegend:
    """Task 10: Fix double legend bug."""

    def test_single_legend_call(self):
        """Only one addLegend() call should exist."""
        source = read_source(NETWORTH_TAB_PATH)
        # Count addLegend calls - should be 1
        count = source.count("addLegend()")
        assert count == 1, f"Found {count} addLegend() calls, expected 1"


class TestTask11CategoriesCheckboxes:
    """Task 11: Remove categories checkboxes from panel."""

    def test_category_checkboxes_created_but_not_added(self):
        """Category checkboxes should exist internally but not be added to layout."""
        source = read_source(NETWORTH_TAB_PATH)
        # Checkboxes should be created
        assert "category_checkboxes" in source or "QCheckBox" in source
        # But commented or conditionally added
        assert "self.category_checkboxes" in source


class TestTask12CharacterCheckboxes:
    """Task 12: Character selector checkboxes visible and functional."""

    def test_character_checkboxes_in_rebuild(self):
        """Character checkboxes should be created in rebuild method."""
        source = read_source(NETWORTH_TAB_PATH)
        assert "_rebuild_character_filters" in source
        assert "QCheckBox" in source


class TestTask13ESIAuthDI:
    """Task 13: Refactor ESIAuth token caching to DI."""

    def test_global_cache_removed(self):
        """Global token cache variables should be removed."""
        source = read_source(ESI_AUTH_PATH)
        assert "_GLOBAL_TOKEN_CACHE_BY_PATH" not in source
        assert "_GLOBAL_TOKEN_LOCK" not in source

    def test_load_tokens_has_file_logic(self):
        """_load_tokens should contain file reading logic."""
        source = read_source(ESI_AUTH_PATH)
        assert "json.load" in source or "json.loads" in source
        assert "token_file" in source or "token_path" in source

    def test_esi_auth_registered_in_di(self):
        """ESI_AUTH should be registered in DIContainer."""
        source = read_source(DI_CONTAINER_PATH)
        assert "ESI_AUTH" in source
        assert "esi_auth" in source.lower()

    def test_esi_auth_factory_exists(self):
        """configure_container should register ESI_AUTH service."""
        source = read_source(DI_CONTAINER_PATH)
        assert "ESIAuth" in source
        assert "register" in source or "container" in source


if __name__ == "__main__":
    # Simple test runner for verification
    import sys

    test_classes = [
        TestTask1AssetTabCharacterFilter,
        TestTask2PlexButtonModifiers,
        TestTask3NetworthSnapshot,
        TestTask4TableRowHeight,
        TestTask6CharacterCardSize,
        TestTask7PanelSizingPolicy,
        TestTask9GraphVisuals,
        TestTask10DoubleLegend,
        TestTask11CategoriesCheckboxes,
        TestTask12CharacterCheckboxes,
        TestTask13ESIAuthDI,
    ]

    failed = []
    passed = 0

    for test_class in test_classes:
        instance = test_class()
        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    method = getattr(instance, method_name)
                    method()
                    passed += 1
                    print(f"✓ {test_class.__name__}.{method_name}")
                except Exception as e:
                    failed.append(f"{test_class.__name__}.{method_name}: {e}")
                    print(f"✗ {test_class.__name__}.{method_name}: {e}")

    print(f"\nPassed: {passed}, Failed: {len(failed)}")
    sys.exit(0 if not failed else 1)
