"""Tests for the CharacterFilterWidget."""

import os
import sys
from pathlib import Path

# Ensure src is on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Run Qt in minimal mode to avoid GUI plugin errors in CI/console runs
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")


class _MockCharacterService:
    """Mock character service for testing."""

    async def get_character_portrait(self, character_id: int, preferred_size: int = 64):
        return None  # No portrait data in tests


class _MockCharacter:
    """Mock character object for testing."""

    def __init__(self, character_id: int, character_name: str):
        self.character_id = character_id
        self.character_name = character_name


def test_character_filter_item_toggle():
    """Test CharacterFilterItem checkbox toggle."""
    from ui.widgets.character_filter_widget import CharacterFilterItem

    item = CharacterFilterItem(123, "Test Character")

    # Check initial state
    assert item.is_checked() is True
    assert item.character_id == 123
    assert item.character_name == "Test Character"

    # Test set_checked without signal
    toggled_calls = []
    item.toggled.connect(lambda cid, checked: toggled_calls.append((cid, checked)))

    item.set_checked(False)
    assert item.is_checked() is False
    assert len(toggled_calls) == 0  # Signal was blocked

    # Test checkbox direct toggle (emits signal)
    item.checkbox.setChecked(True)
    assert item.is_checked() is True
    assert len(toggled_calls) == 1
    assert toggled_calls[0] == (123, True)


def test_character_filter_widget_set_characters():
    """Test CharacterFilterWidget character list management."""
    from ui.widgets.character_filter_widget import CharacterFilterWidget

    widget = CharacterFilterWidget(_MockCharacterService())

    # Test setting characters
    characters = [
        _MockCharacter(1, "Char One"),
        _MockCharacter(2, "Char Two"),
        _MockCharacter(3, "Char Three"),
    ]
    widget.set_characters(characters)

    # All characters should be selected by default
    assert widget.get_all_character_ids() == {1, 2, 3}
    assert widget.get_selected_character_ids() == {1, 2, 3}

    # Test individual character selection check
    assert widget.is_character_selected(1) is True
    assert widget.is_character_selected(2) is True
    assert widget.is_character_selected(999) is False  # Non-existent


def test_character_filter_widget_select_all_none():
    """Test CharacterFilterWidget select all/none functionality."""
    from ui.widgets.character_filter_widget import CharacterFilterWidget

    widget = CharacterFilterWidget(_MockCharacterService())

    characters = [
        _MockCharacter(1, "Char One"),
        _MockCharacter(2, "Char Two"),
    ]
    widget.set_characters(characters)

    # Track filter changes
    filter_changes = []
    widget.filter_changed.connect(lambda ids: filter_changes.append(set(ids)))

    # Test select none
    widget._select_none()
    assert widget.get_selected_character_ids() == set()
    assert len(filter_changes) == 1
    assert filter_changes[-1] == set()

    # Test select all
    widget._select_all()
    assert widget.get_selected_character_ids() == {1, 2}
    assert len(filter_changes) == 2
    assert filter_changes[-1] == {1, 2}


def test_character_filter_widget_toggle_character():
    """Test CharacterFilterWidget individual character toggle."""
    from ui.widgets.character_filter_widget import CharacterFilterWidget

    widget = CharacterFilterWidget(_MockCharacterService())

    characters = [
        _MockCharacter(1, "Char One"),
        _MockCharacter(2, "Char Two"),
    ]
    widget.set_characters(characters)

    # Track filter changes
    filter_changes = []
    widget.filter_changed.connect(lambda ids: filter_changes.append(set(ids)))

    # Toggle character 1 off
    widget._on_character_toggled(1, False)
    assert widget.get_selected_character_ids() == {2}
    assert len(filter_changes) == 1
    assert filter_changes[-1] == {2}

    # Toggle character 1 back on
    widget._on_character_toggled(1, True)
    assert widget.get_selected_character_ids() == {1, 2}
    assert len(filter_changes) == 2
    assert filter_changes[-1] == {1, 2}


def test_character_filter_widget_collapse_toggle():
    """Test CharacterFilterWidget collapse functionality."""
    from ui.widgets.character_filter_widget import CharacterFilterWidget

    widget = CharacterFilterWidget(_MockCharacterService())

    # Initially expanded
    assert widget._collapsed is False
    assert widget.scroll_area.isVisible() is True
    assert widget.collapse_btn.text() == "▼"

    # Toggle to collapsed
    widget._toggle_collapse()
    assert widget._collapsed is True
    assert widget.scroll_area.isVisible() is False
    assert widget.collapse_btn.text() == "▶"

    # Toggle back to expanded
    widget._toggle_collapse()
    assert widget._collapsed is False
    assert widget.scroll_area.isVisible() is True
    assert widget.collapse_btn.text() == "▼"
