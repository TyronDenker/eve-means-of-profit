"""Compact character filter widget for asset filtering.

Provides a collapsible list of characters with checkboxes for filtering
assets by selected characters.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from services.character_service import CharacterService

from ui.styles import COLORS, AppStyles

logger = logging.getLogger(__name__)

PORTRAIT_SIZE = 32  # Small portrait for compact display


class CharacterFilterItem(QWidget):
    """Single character row with checkbox, portrait, and name."""

    toggled = pyqtSignal(int, bool)  # character_id, checked

    def __init__(
        self,
        character_id: int,
        character_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.character_id = character_id
        self.character_name = character_name

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setStyleSheet(AppStyles.CHECKBOX)
        self.checkbox.stateChanged.connect(self._on_state_changed)
        layout.addWidget(self.checkbox)

        # Portrait placeholder
        self.portrait_label = QLabel()
        self.portrait_label.setFixedSize(PORTRAIT_SIZE, PORTRAIT_SIZE)
        self.portrait_label.setScaledContents(True)
        self.portrait_label.setStyleSheet(
            f"border: 1px solid {COLORS.BORDER_MEDIUM}; background: {COLORS.BG_DARK}; border-radius: 2px;"
        )
        self._set_placeholder_portrait()
        layout.addWidget(self.portrait_label)

        # Character name
        self.name_label = QLabel(character_name)
        self.name_label.setStyleSheet(
            f"color: {COLORS.TEXT_SECONDARY}; font-size: 11px;"
        )
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self.name_label)

        # Allow clicking anywhere on the row to toggle
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _set_placeholder_portrait(self) -> None:
        """Set a placeholder portrait."""
        self.portrait_label.setText("?")
        self.portrait_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def set_portrait(self, img_data: bytes | None) -> None:
        """Set the portrait image from bytes."""
        if not img_data:
            self._set_placeholder_portrait()
            return

        try:
            pixmap = QPixmap()
            if pixmap.loadFromData(img_data):
                scaled = pixmap.scaled(
                    PORTRAIT_SIZE,
                    PORTRAIT_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.portrait_label.setPixmap(scaled)
                self.portrait_label.setText("")
        except Exception:
            logger.debug("Failed to load portrait for %d", self.character_id)
            self._set_placeholder_portrait()

    def _on_state_changed(self, state: int) -> None:
        """Emit toggle signal when checkbox state changes."""
        checked = state == Qt.CheckState.Checked.value
        self.toggled.emit(self.character_id, checked)

    def is_checked(self) -> bool:
        """Return whether this character is selected."""
        return self.checkbox.isChecked()

    def set_checked(self, checked: bool) -> None:
        """Set the checkbox state without emitting signal."""
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)

    def mousePressEvent(self, event) -> None:  # type: ignore[override] # noqa: N802
        """Toggle checkbox when clicking anywhere on the row."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


class CharacterFilterWidget(QWidget):
    """Collapsible character filter with compact vertical list."""

    filter_changed = pyqtSignal(set)  # Emits set of selected character_ids

    def __init__(
        self,
        character_service: CharacterService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._character_service = character_service
        self._character_items: dict[int, CharacterFilterItem] = {}
        self._selected_character_ids: set[int] = set()
        self._all_character_ids: set[int] = set()
        self._collapsed = False
        self._background_tasks: set[asyncio.Task] = set()

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header with collapse toggle and quick buttons
        header = QFrame()
        header.setStyleSheet(
            f"QFrame {{ background: {COLORS.BG_LIGHT}; border: 1px solid {COLORS.BORDER_MEDIUM}; border-radius: 3px; }}"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_layout.setSpacing(8)

        # Collapse toggle button
        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("▼")
        self.collapse_btn.setStyleSheet(
            f"QToolButton {{ border: none; color: {COLORS.TEXT_MUTED}; font-size: 10px; }}"
            f"QToolButton:hover {{ color: {COLORS.TEXT_PRIMARY}; }}"
        )
        self.collapse_btn.setFixedSize(16, 16)
        self.collapse_btn.clicked.connect(self._toggle_collapse)
        header_layout.addWidget(self.collapse_btn)

        # Title
        title = QLabel("Characters")
        title.setStyleSheet(
            f"color: {COLORS.TEXT_SECONDARY}; font-weight: bold; font-size: 11px;"
        )
        header_layout.addWidget(title)

        # Character count label
        self.count_label = QLabel("(0/0)")
        self.count_label.setStyleSheet(f"color: {COLORS.TEXT_MUTED}; font-size: 10px;")
        header_layout.addWidget(self.count_label)

        header_layout.addStretch()

        # Quick selection buttons
        self.all_btn = QPushButton("All")
        self.all_btn.setStyleSheet(AppStyles.BUTTON_SMALL)
        self.all_btn.setFixedHeight(20)
        self.all_btn.clicked.connect(self._select_all)
        header_layout.addWidget(self.all_btn)

        self.none_btn = QPushButton("None")
        self.none_btn.setStyleSheet(AppStyles.BUTTON_SMALL)
        self.none_btn.setFixedHeight(20)
        self.none_btn.clicked.connect(self._select_none)
        header_layout.addWidget(self.none_btn)

        main_layout.addWidget(header)

        # Scrollable character list container
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {COLORS.BORDER_MEDIUM}; border-top: none; background: {COLORS.BG_MEDIUM}; }}"
            + AppStyles.SCROLLBAR
        )
        # Set max height for scrollable area (shows ~6 characters before scrolling)
        self.scroll_area.setMaximumHeight(220)

        # Container for character items
        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(4, 4, 4, 4)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()

        self.scroll_area.setWidget(self.list_container)
        main_layout.addWidget(self.scroll_area)

    def _toggle_collapse(self) -> None:
        """Toggle the collapsed state of the character list."""
        self._collapsed = not self._collapsed
        self.scroll_area.setVisible(not self._collapsed)
        self.collapse_btn.setText("▶" if self._collapsed else "▼")

    def _select_all(self) -> None:
        """Select all characters."""
        for item in self._character_items.values():
            item.set_checked(True)
        self._selected_character_ids = set(self._all_character_ids)
        self._update_count_label()
        self.filter_changed.emit(self._selected_character_ids)

    def _select_none(self) -> None:
        """Deselect all characters."""
        for item in self._character_items.values():
            item.set_checked(False)
        self._selected_character_ids.clear()
        self._update_count_label()
        self.filter_changed.emit(self._selected_character_ids)

    def _update_count_label(self) -> None:
        """Update the character count label."""
        total = len(self._all_character_ids)
        selected = len(self._selected_character_ids)
        self.count_label.setText(f"({selected}/{total})")

    def _on_character_toggled(self, character_id: int, checked: bool) -> None:
        """Handle character checkbox toggle."""
        if checked:
            self._selected_character_ids.add(character_id)
        else:
            self._selected_character_ids.discard(character_id)
        self._update_count_label()
        self.filter_changed.emit(self._selected_character_ids)

    def set_characters(self, characters: list) -> None:
        """Set the list of characters to display.

        Args:
            characters: List of CharacterInfo objects or dicts with character_id and character_name
        """
        # Clear existing items
        for item in self._character_items.values():
            item.setParent(None)
            item.deleteLater()
        self._character_items.clear()
        self._all_character_ids.clear()

        # Remove stretch at end
        while self.list_layout.count() > 0:
            layout_item = self.list_layout.takeAt(0)
            if layout_item is not None:
                widget = layout_item.widget()
                if widget is not None:
                    widget.deleteLater()

        # Add character items
        for char in characters:
            char_id = getattr(char, "character_id", None) or char.get("character_id")
            char_name = getattr(char, "character_name", None) or char.get(
                "character_name", str(char_id)
            )

            if char_id is None:
                continue

            item = CharacterFilterItem(char_id, char_name, self)
            item.toggled.connect(self._on_character_toggled)
            self._character_items[char_id] = item
            self._all_character_ids.add(char_id)
            self._selected_character_ids.add(char_id)  # Select all by default
            self.list_layout.addWidget(item)

        # Add stretch at end
        self.list_layout.addStretch()

        self._update_count_label()

        # Load portraits asynchronously
        self._load_portraits()

    def _load_portraits(self) -> None:
        """Load character portraits asynchronously."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, skip portrait loading
            return

        async def load_all_portraits():
            for char_id, item in self._character_items.items():
                try:
                    portrait_data = (
                        await self._character_service.get_character_portrait(
                            char_id, preferred_size=64
                        )
                    )
                    if portrait_data:
                        item.set_portrait(portrait_data)
                except Exception:
                    logger.debug("Failed to load portrait for %d", char_id)

        task = loop.create_task(load_all_portraits())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def get_selected_character_ids(self) -> set[int]:
        """Return the set of selected character IDs."""
        return set(self._selected_character_ids)

    def get_all_character_ids(self) -> set[int]:
        """Return the set of all character IDs."""
        return set(self._all_character_ids)

    def is_character_selected(self, character_id: int) -> bool:
        """Check if a specific character is selected."""
        return character_id in self._selected_character_ids

    def build_predicate(self):
        """Build a predicate function for filtering rows by selected characters.

        Returns:
            A callable that takes a row dict and returns True if the row's
            owner_character_id is in the selected characters.
        """
        selected = self._selected_character_ids.copy()

        def predicate(row: dict) -> bool:
            owner_id = row.get("owner_character_id")
            if owner_id is None:
                return True  # Include rows without owner info
            try:
                return int(owner_id) in selected
            except (ValueError, TypeError):
                return True

        return predicate
