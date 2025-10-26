"""Filter panel widget for data filtering."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class FilterPanel(QWidget):
    """Reusable filter panel widget.

    Provides filtering options for EVE data.

    """

    # Signal emitted when filters change
    filters_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        """Initialize the filter panel.

        Args:
            parent: Parent widget

        """
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)

        # Published filter
        published_group = QGroupBox("Published Status")
        published_layout = QVBoxLayout()

        self._published_checkbox = QCheckBox("Show only published items")
        self._published_checkbox.setChecked(True)
        self._published_checkbox.stateChanged.connect(self._on_filters_changed)
        published_layout.addWidget(self._published_checkbox)

        published_group.setLayout(published_layout)
        layout.addWidget(published_group)

        # Category filter
        category_group = QGroupBox("Category Filter")
        category_layout = QVBoxLayout()

        category_label = QLabel("Category:")
        category_layout.addWidget(category_label)

        self._category_combo = QComboBox()
        self._category_combo.addItem("All Categories", None)
        self._category_combo.currentIndexChanged.connect(self._on_filters_changed)
        category_layout.addWidget(self._category_combo)

        category_group.setLayout(category_layout)
        layout.addWidget(category_group)

        # Group filter
        group_group = QGroupBox("Group Filter")
        group_layout = QVBoxLayout()

        group_label = QLabel("Group:")
        group_layout.addWidget(group_label)

        self._group_combo = QComboBox()
        self._group_combo.addItem("All Groups", None)
        self._group_combo.currentIndexChanged.connect(self._on_filters_changed)
        group_layout.addWidget(self._group_combo)

        group_group.setLayout(group_layout)
        layout.addWidget(group_group)

        layout.addStretch()
        self.setLayout(layout)

    def _on_filters_changed(self) -> None:
        """Handle filter changes."""
        filters = self.get_filters()
        self.filters_changed.emit(filters)

    def get_filters(self) -> dict:
        """Get the current filter settings.

        Returns:
            Dictionary with filter settings

        """
        return {
            "published_only": self._published_checkbox.isChecked(),
            "category_id": self._category_combo.currentData(),
            "group_id": self._group_combo.currentData(),
        }

    def set_categories(self, categories: list[tuple[int, str]]) -> None:
        """Set available categories.

        Args:
            categories: List of (category_id, category_name) tuples

        """
        self._category_combo.clear()
        self._category_combo.addItem("All Categories", None)
        for cat_id, cat_name in categories:
            self._category_combo.addItem(cat_name, cat_id)

    def set_groups(self, groups: list[tuple[int, str]]) -> None:
        """Set available groups.

        Args:
            groups: List of (group_id, group_name) tuples

        """
        self._group_combo.clear()
        self._group_combo.addItem("All Groups", None)
        for group_id, group_name in groups:
            self._group_combo.addItem(group_name, group_id)

    def reset_filters(self) -> None:
        """Reset all filters to default values."""
        self._published_checkbox.setChecked(True)
        self._category_combo.setCurrentIndex(0)
        self._group_combo.setCurrentIndex(0)
