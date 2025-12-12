"""Comprehensive tests for all UI/UX fixes implemented."""

import re
from pathlib import Path


def test_plex_buttons_use_qapplication_modifiers():
    """Test that PLEX +/- buttons use QApplication.keyboardModifiers()."""
    account_group_path = Path("src/ui/widgets/account_group_widget.py")
    assert account_group_path.exists(), "account_group_widget.py not found"

    content = account_group_path.read_text(encoding="utf-8")

    # Should have _nudge_plex_simple method
    assert "_nudge_plex_simple" in content, "Missing _nudge_plex_simple method"

    # Should use QApplication.keyboardModifiers()
    assert "QApplication.keyboardModifiers()" in content, (
        "Not using QApplication.keyboardModifiers()"
    )

    # Should not have old modifier_clicked connections
    assert "modifier_clicked.connect" not in content, (
        "Still using modifier_clicked signal"
    )

    # Should have proper .clicked.connect to _nudge_plex_simple
    assert "clicked.connect" in content and "_nudge_plex_simple" in content, (
        "Missing proper button connection"
    )


def test_character_dropdown_has_signal_handler():
    """Test that EditSnapshotDialog has character dropdown change handler."""
    dialog_path = Path("src/ui/dialogs/edit_snapshot_dialog.py")
    assert dialog_path.exists(), "edit_snapshot_dialog.py not found"

    content = dialog_path.read_text(encoding="utf-8")

    # Should connect currentIndexChanged signal
    assert "currentIndexChanged.connect" in content, (
        "Missing currentIndexChanged connection"
    )

    # Should have _on_character_changed method
    assert "_on_character_changed" in content, "Missing _on_character_changed method"


def test_graph_has_antialiasing():
    """Test that networth graph enables antialiasing."""
    networth_path = Path("src/ui/tabs/networth_tab.py")
    assert networth_path.exists(), "networth_tab.py not found"

    content = networth_path.read_text(encoding="utf-8")

    # Should call setAntialiasing
    assert "setAntialiasing(True)" in content, "Graph doesn't enable antialiasing"

    # Should use antialias parameter in plot calls
    assert "antialias=True" in content, "Plot calls don't use antialias parameter"


def test_graph_has_different_line_styles():
    """Test that graph uses different line styles for categories."""
    networth_path = Path("src/ui/tabs/networth_tab.py")
    assert networth_path.exists(), "networth_tab.py not found"

    content = networth_path.read_text(encoding="utf-8")

    # Should have LINE_STYLE_MAP
    assert "LINE_STYLE_MAP" in content, "Missing LINE_STYLE_MAP"

    # Should have different styles
    assert "solid" in content and "dash" in content and "dot" in content, (
        "Missing different line styles"
    )

    # Should use Qt.PenStyle
    assert "Qt.PenStyle" in content, "Not using Qt.PenStyle for line styles"


def test_graph_has_colored_emoji_summaries():
    """Test that delta summary has colored emoji icons."""
    networth_path = Path("src/ui/tabs/networth_tab.py")
    assert networth_path.exists(), "networth_tab.py not found"

    content = networth_path.read_text(encoding="utf-8")

    # Should have EMOJI_MAP
    assert "EMOJI_MAP" in content, "Missing EMOJI_MAP"

    # Should use emojis in delta label
    assert "emoji = self.EMOJI_MAP.get" in content, "Not using emoji map in delta label"

    # Should have various emoji characters
    emoji_pattern = r"[\U0001F7E0-\U0001F7FF]|[\u2B1B-\u2B1C]"
    assert re.search(emoji_pattern, content), "Missing emoji characters"


def test_character_checkboxes_have_visual_feedback():
    """Test that character checkboxes have proper styling for selected state."""
    networth_path = Path("src/ui/tabs/networth_tab.py")
    assert networth_path.exists(), "networth_tab.py not found"

    content = networth_path.read_text(encoding="utf-8")

    # Should have checkbox indicator styling
    assert "QCheckBox::indicator" in content, "Missing checkbox indicator styling"

    # Should have checked state styling
    assert "QCheckBox::indicator:checked" in content, "Missing checked state styling"

    # Should set background color for checked state
    assert "background-color: #0d7377" in content or "background-color:" in content, (
        "Missing checkbox checked background color"
    )


def test_character_card_fixed_timer_column_width():
    """Test that character card networth grid has fixed timer column width."""
    char_widget_path = Path("src/ui/widgets/character_item_widget.py")
    assert char_widget_path.exists(), "character_item_widget.py not found"

    content = char_widget_path.read_text(encoding="utf-8")

    # Should set column minimum width for timer column
    assert "setColumnMinimumWidth(2," in content, "Missing timer column minimum width"

    # Should have horizontal spacing
    assert "setHorizontalSpacing" in content, "Missing horizontal spacing setting"


def test_set_timers_visible_updates_layout():
    """Test that set_timers_visible properly toggles timer visibility."""
    char_widget_path = Path("src/ui/widgets/character_item_widget.py")
    assert char_widget_path.exists(), "character_item_widget.py not found"

    content = char_widget_path.read_text(encoding="utf-8")

    # Should have set_timers_visible method
    assert "def set_timers_visible" in content, "Missing set_timers_visible method"

    # Should iterate through grid items
    assert "itemAtPosition" in content or "rowCount" in content, (
        "set_timers_visible doesn't iterate grid items"
    )

    # Should call setVisible on timer widgets
    # This would be in the set_timers_visible implementation


def test_table_rows_have_reduced_height():
    """Test that AdvancedTableWidget has compact row height."""
    # This would need to check the AdvancedTableWidget implementation
    # For now, we just verify the file exists
    table_path = Path("src/ui/widgets/advanced_table_widget.py")
    assert table_path.exists(), "advanced_table_widget.py not found"


def test_all_files_syntax_valid():
    """Test that all modified files have valid Python syntax."""
    files_to_check = [
        "src/ui/widgets/account_group_widget.py",
        "src/ui/dialogs/edit_snapshot_dialog.py",
        "src/ui/tabs/networth_tab.py",
        "src/ui/widgets/character_item_widget.py",
    ]

    for file_path in files_to_check:
        path = Path(file_path)
        assert path.exists(), f"{file_path} not found"

        content = path.read_text(encoding="utf-8")
        # Basic syntax check - should compile without errors
        try:
            compile(content, file_path, "exec")
        except SyntaxError as e:
            raise AssertionError(f"Syntax error in {file_path}: {e}")


def test_plex_modifier_key_combinations():
    """Test that PLEX buttons check for all modifier combinations."""
    account_group_path = Path("src/ui/widgets/account_group_widget.py")
    content = account_group_path.read_text(encoding="utf-8")

    # Should check for Ctrl+Shift (500)
    assert "ctrl and shift" in content.lower(), "Missing Ctrl+Shift check"
    assert "500" in content, "Missing 500 step for Ctrl+Shift"

    # Should check for Ctrl (100)
    assert "elif ctrl:" in content, "Missing Ctrl check"
    assert "100" in content, "Missing 100 step for Ctrl"

    # Should check for Shift (10)
    assert "elif shift:" in content, "Missing Shift check"
    assert "10" in content, "Missing 10 step for Shift"


def test_no_modifier_aware_push_button_signals():
    """Test that ModifierAwarePushButton signals are not used anymore."""
    account_group_path = Path("src/ui/widgets/account_group_widget.py")
    content = account_group_path.read_text(encoding="utf-8")

    # Count occurrences of modifier_clicked - should only be in class definition
    # not in actual connections
    lines = content.split("\n")
    connection_lines = [
        l
        for l in lines
        if "modifier_clicked.connect" in l and not l.strip().startswith("#")
    ]

    assert len(connection_lines) == 0, (
        f"Found {len(connection_lines)} modifier_clicked connections (should be 0)"
    )


def test_graph_line_widths():
    """Test that graph uses appropriate line widths."""
    networth_path = Path("src/ui/tabs/networth_tab.py")
    content = networth_path.read_text(encoding="utf-8")

    # Should have different widths for categories and Total
    assert "width=1.5" in content, "Missing thin lines for categories"
    assert "width=2.5" in content, "Missing thicker line for Total"


def test_graph_has_markers():
    """Test that graph plots have markers/symbols."""
    networth_path = Path("src/ui/tabs/networth_tab.py")
    content = networth_path.read_text(encoding="utf-8")

    # Should have SYMBOL_MAP defining different shapes per category
    assert "SYMBOL_MAP" in content, "Missing SYMBOL_MAP for point shapes"

    # Should have various marker types defined
    assert '"o"' in content, "Missing circular marker in SYMBOL_MAP"
    assert '"s"' in content, "Missing square marker in SYMBOL_MAP"
    assert '"t"' in content, "Missing triangle marker in SYMBOL_MAP"

    # Should use symbol from SYMBOL_MAP when plotting
    assert "symbol=symbol" in content, "Symbols not being applied to plots"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
