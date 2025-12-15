"""Tests for context menu framework"""

import os
import sys
from pathlib import Path

# Ensure src is on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Run Qt in minimal mode to avoid GUI plugin errors
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from unittest.mock import Mock, patch

import pytest
from PyQt6.QtWidgets import QMenu, QWidget

from ui.menus.context_menu_factory import ContextMenuFactory
from ui.utils.clipboard import (
    copy_cells_as_text,
    copy_column_headers,
    copy_field_values,
    copy_rows_as_csv,
    copy_to_clipboard,
)


@pytest.fixture
def mock_settings():
    """Create mock settings manager."""
    settings = Mock()
    settings.get_custom_price = Mock(return_value=None)
    settings.get_custom_location_name = Mock(return_value=None)
    settings.set_custom_price = Mock()
    settings.set_custom_location_name = Mock()
    settings.remove_custom_price = Mock()
    settings.remove_custom_location_name = Mock()
    return settings


@pytest.fixture
def context_menu_factory(mock_settings):
    """Create ContextMenuFactory instance."""
    return ContextMenuFactory(mock_settings)


@pytest.fixture
def sample_rows():
    """Sample row data for testing."""
    return [
        {
            "type_id": 34,
            "type_name": "Tritanium",
            "quantity": 1000,
            "location_id": 60003760,
            "location_name": "Jita IV - Moon 4",
        },
        {
            "type_id": 35,
            "type_name": "Pyerite",
            "quantity": 500,
            "location_id": 60003760,
            "location_name": "Jita IV - Moon 4",
        },
    ]


@pytest.fixture
def sample_columns():
    """Sample column definitions."""
    return [
        ("type_id", "Type ID"),
        ("type_name", "Item"),
        ("quantity", "Quantity"),
        ("location_id", "Location ID"),
        ("location_name", "Location"),
    ]


def test_context_menu_factory_creates_menu(
    qtbot, context_menu_factory, sample_rows, sample_columns
):
    """Test that context menu factory creates a QMenu."""
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = context_menu_factory.build_table_menu(
        parent, sample_rows, sample_columns, enable_copy=True
    )

    assert isinstance(menu, QMenu)
    assert menu.parent() == parent


def test_context_menu_copy_actions_present(
    qtbot, context_menu_factory, sample_rows, sample_columns
):
    """Test that copy submenu is created when enabled."""
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = context_menu_factory.build_table_menu(
        parent, sample_rows, sample_columns, enable_copy=True
    )

    # Find copy submenu
    actions = menu.actions()
    copy_action = next((a for a in actions if "Copy" in a.text()), None)
    assert copy_action is not None

    # Check copy submenu exists
    copy_menu = copy_action.menu()
    assert copy_menu is not None


def test_context_menu_custom_price_single_item(
    qtbot, context_menu_factory, sample_rows, sample_columns, mock_settings
):
    """Test custom price menu for single selected item."""
    parent = QWidget()
    qtbot.addWidget(parent)

    single_row = [sample_rows[0]]  # Single item

    menu = context_menu_factory.build_table_menu(
        parent,
        single_row,
        sample_columns,
        enable_custom_price=True,
        type_id_key="type_id",
    )

    # Find price submenu
    actions = menu.actions()
    price_action = next((a for a in actions if "Price" in a.text()), None)
    assert price_action is not None


def test_context_menu_custom_price_multiple_items(
    qtbot, context_menu_factory, sample_rows, sample_columns, mock_settings
):
    """Test custom price menu for multiple selected items."""
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = context_menu_factory.build_table_menu(
        parent,
        sample_rows,
        sample_columns,
        enable_custom_price=True,
        type_id_key="type_id",
    )

    # Find price submenu
    actions = menu.actions()
    price_action = next((a for a in actions if "Price" in a.text()), None)
    assert price_action is not None


def test_context_menu_custom_location(
    qtbot, context_menu_factory, sample_rows, sample_columns, mock_settings
):
    """Test custom location menu appears when enabled."""
    parent = QWidget()
    qtbot.addWidget(parent)

    single_row = [sample_rows[0]]

    menu = context_menu_factory.build_table_menu(
        parent,
        single_row,
        sample_columns,
        enable_custom_location=True,
        location_id_key="location_id",
    )

    # Find location submenu
    actions = menu.actions()
    location_action = next((a for a in actions if "Location" in a.text()), None)
    assert location_action is not None


def test_context_menu_selection_info(
    qtbot, context_menu_factory, sample_rows, sample_columns
):
    """Test that selection info is displayed in menu."""
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = context_menu_factory.build_table_menu(
        parent, sample_rows, sample_columns, enable_copy=True
    )

    # Find selection info action
    actions = menu.actions()
    info_action = next(
        (a for a in actions if "Selection" in a.text() and "item" in a.text()), None
    )
    assert info_action is not None
    assert "2 item" in info_action.text()


def test_context_menu_custom_actions(
    qtbot, context_menu_factory, sample_rows, sample_columns
):
    """Test that custom actions are added to menu."""
    parent = QWidget()
    qtbot.addWidget(parent)

    custom_callback = Mock()
    custom_actions = [("Custom Action", custom_callback)]

    menu = context_menu_factory.build_table_menu(
        parent, sample_rows, sample_columns, custom_actions=custom_actions
    )

    # Find custom action
    actions = menu.actions()
    custom_action = next((a for a in actions if "Custom Action" in a.text()), None)
    assert custom_action is not None


def test_extract_unique_ids(context_menu_factory, sample_rows):
    """Test extraction of unique IDs from rows."""
    type_ids = context_menu_factory._extract_unique_ids(sample_rows, "type_id")
    assert type_ids == [34, 35]

    location_ids = context_menu_factory._extract_unique_ids(sample_rows, "location_id")
    assert location_ids == [60003760]


def test_find_common_keys(context_menu_factory, sample_rows, sample_columns):
    """Test finding common keys across selected rows."""
    common = context_menu_factory._find_common_keys(sample_rows, sample_columns)

    # All columns should be common since both rows have all values
    assert len(common) == len(sample_columns)
    assert ("type_name", "Item") in common


@patch("ui.utils.clipboard.QApplication.clipboard")
def test_copy_to_clipboard(mock_clipboard_getter):
    """Test copying text to clipboard."""
    mock_clipboard = Mock()
    mock_clipboard_getter.return_value = mock_clipboard

    copy_to_clipboard("test text")

    mock_clipboard.setText.assert_called_once_with("test text")


def test_copy_cells_as_text(sample_rows, sample_columns):
    """Test copying cells as tab-separated text."""
    with patch("ui.utils.clipboard.copy_to_clipboard") as mock_copy:
        keys = [col[0] for col in sample_columns]
        copy_cells_as_text(sample_rows, keys)

        # Should have called with tab-separated values
        call_arg = mock_copy.call_args[0][0]
        assert "\t" in call_arg
        assert "Tritanium" in call_arg
        assert "Pyerite" in call_arg


def test_copy_rows_as_csv(sample_rows, sample_columns):
    """Test copying rows as CSV with headers."""
    with patch("ui.utils.clipboard.copy_to_clipboard") as mock_copy:
        copy_rows_as_csv(sample_rows, sample_columns)

        # Should have headers and CSV format
        call_arg = mock_copy.call_args[0][0]
        assert '"Type ID"' in call_arg
        assert '"Item"' in call_arg
        assert '"Tritanium"' in call_arg


def test_copy_column_headers(sample_columns):
    """Test copying column headers."""
    with patch("ui.utils.clipboard.copy_to_clipboard") as mock_copy:
        copy_column_headers(sample_columns)

        call_arg = mock_copy.call_args[0][0]
        assert "Type ID\tItem\tQuantity" in call_arg


def test_copy_field_values(sample_rows):
    """Test copying single field values."""
    with patch("ui.utils.clipboard.copy_to_clipboard") as mock_copy:
        copy_field_values(sample_rows, "type_name")

        call_arg = mock_copy.call_args[0][0]
        assert "Tritanium" in call_arg
        assert "Pyerite" in call_arg
        assert "\n" in call_arg  # Newline separated


def test_context_menu_no_rows(qtbot, context_menu_factory, sample_columns):
    """Test context menu with no selected rows."""
    parent = QWidget()
    qtbot.addWidget(parent)

    menu = context_menu_factory.build_table_menu(
        parent, [], sample_columns, enable_copy=True
    )

    # Menu should still be created but with minimal content
    assert isinstance(menu, QMenu)


@patch("ui.menus.context_menu_factory.get_signal_bus")
def test_remove_custom_price_emits_signal(
    mock_get_bus, context_menu_factory, mock_settings
):
    """Test that removing custom price emits signal."""
    mock_bus = Mock()
    mock_get_bus.return_value = mock_bus

    context_menu_factory._remove_custom_price(34)

    mock_settings.remove_custom_price.assert_called_once_with(34)
    mock_bus.custom_price_changed.emit.assert_called_once_with(34)


@patch("ui.menus.context_menu_factory.get_signal_bus")
def test_remove_custom_location_emits_signal(
    mock_get_bus, context_menu_factory, mock_settings
):
    """Test that removing custom location emits signal."""
    mock_bus = Mock()
    mock_get_bus.return_value = mock_bus

    context_menu_factory._remove_custom_location(60003760)

    mock_settings.remove_custom_location_name.assert_called_once_with(60003760)
    mock_bus.custom_location_changed.emit.assert_called_once_with(60003760)
