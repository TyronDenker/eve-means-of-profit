"""Clipboard utilities for copying data from tables and other widgets."""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


def copy_to_clipboard(text: str) -> None:
    """Copy text to system clipboard.

    Args:
        text: Text to copy to clipboard
    """
    try:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
    except Exception as e:
        logger.warning("Failed to copy to clipboard: %s", e)


def copy_cells_as_text(selected_rows: list[dict[str, Any]], keys: list[str]) -> None:
    """Copy selected cells as tab-separated text.

    Args:
        selected_rows: List of row dictionaries
        keys: Column keys to extract
    """
    if not selected_rows:
        return

    lines = []
    for row in selected_rows:
        values = [str(row.get(key, "")) for key in keys]
        lines.append("\t".join(values))

    copy_to_clipboard("\n".join(lines))


def copy_rows_as_csv(
    selected_rows: list[dict[str, Any]], columns: list[tuple[str, str]]
) -> None:
    """Copy selected rows as CSV with headers.

    Args:
        selected_rows: List of row dictionaries
        columns: List of (key, title) tuples defining columns
    """
    if not selected_rows:
        return

    keys = [col[0] for col in columns]
    titles = [col[1] for col in columns]

    # Header row
    lines = [",".join(f'"{title}"' for title in titles)]

    # Data rows
    for row in selected_rows:
        values = [str(row.get(key, "")).replace('"', '""') for key in keys]
        lines.append(",".join(f'"{val}"' for val in values))

    copy_to_clipboard("\n".join(lines))


def copy_column_headers(columns: list[tuple[str, str]]) -> None:
    """Copy column headers as tab-separated text.

    Args:
        columns: List of (key, title) tuples
    """
    titles = [col[1] for col in columns]
    copy_to_clipboard("\t".join(titles))


def copy_field_values(selected_rows: list[dict[str, Any]], field_key: str) -> None:
    """Copy values of a single field from selected rows.

    Args:
        selected_rows: List of row dictionaries
        field_key: Key of the field to extract
    """
    if not selected_rows:
        return

    values = [str(row.get(field_key, "")) for row in selected_rows]
    copy_to_clipboard("\n".join(values))
