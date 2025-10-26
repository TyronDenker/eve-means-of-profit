"""Types browser widget for searching and viewing EVE types."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.data.managers import SDEManager
from src.models.eve import EveType
from src.models.ui import TypesTableModel
from src.ui.widgets.filter_panel import FilterPanel
from src.ui.widgets.search_bar import SearchBar

logger = logging.getLogger(__name__)


class TypesBrowser(QWidget):
    """Widget for browsing and searching EVE types."""

    def __init__(self, sde_manager: SDEManager, parent=None):
        """Initialize the types browser.

        Args:
            sde_manager: SDEManager instance for data access
            parent: Parent widget

        """
        super().__init__(parent)
        self._sde_manager = sde_manager
        self._all_types: list[EveType] = []
        self._filtered_types: list[EveType] = []
        self._setup_ui()
        self._load_initial_data()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        main_layout = QVBoxLayout(self)

        # Header with search
        header_layout = QVBoxLayout()

        title = QLabel("<h2>EVE Types Browser</h2>")
        header_layout.addWidget(title)

        # Search bar
        self._search_bar = SearchBar("Search by name or ID...")
        self._search_bar.search_changed.connect(self._on_search_changed)
        header_layout.addWidget(self._search_bar)

        main_layout.addLayout(header_layout)

        # Create splitter for filter panel and main content
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side: Filter panel
        self._filter_panel = FilterPanel()
        self._filter_panel.filters_changed.connect(self._on_filters_changed)
        self._filter_panel.setMaximumWidth(300)
        splitter.addWidget(self._filter_panel)

        # Right side: Table and details
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Table view
        self._table_view = QTableView()
        self._table_model = TypesTableModel()
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSortingEnabled(True)

        # Auto-resize columns
        header = self._table_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)

        self._table_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        right_layout.addWidget(self._table_view)

        # Details panel
        details_label = QLabel("<b>Details:</b>")
        right_layout.addWidget(details_label)

        self._details_text = QTextEdit()
        self._details_text.setReadOnly(True)
        self._details_text.setMaximumHeight(150)
        right_layout.addWidget(self._details_text)

        splitter.addWidget(right_widget)
        splitter.setSizes([250, 750])

        main_layout.addWidget(splitter)

        # Status bar
        status_layout = QHBoxLayout()
        self._status_label = QLabel("Loading...")
        status_layout.addWidget(self._status_label)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._load_initial_data)
        status_layout.addWidget(refresh_button)

        main_layout.addLayout(status_layout)

    def _load_initial_data(self) -> None:
        """Load initial data from SDE manager."""
        logger.info("Loading types data...")
        self._status_label.setText("Loading types...")

        try:
            # Load all types
            self._all_types = self._sde_manager.get_all_types()
            logger.info(f"Loaded {len(self._all_types)} types")

            # Load categories for filter
            categories = self._sde_manager.get_all_categories()
            category_list = [
                (cat.id, cat.name.en) for cat in categories if cat.published
            ]
            category_list.sort(key=lambda x: x[1])
            self._filter_panel.set_categories(category_list)

            # Load groups for filter
            groups = self._sde_manager.get_all_groups()
            group_list = [(grp.id, grp.name.en) for grp in groups if grp.published]
            group_list.sort(key=lambda x: x[1])
            self._filter_panel.set_groups(group_list)

            # Apply initial filters
            self._apply_filters()

        except Exception as e:
            logger.error(f"Error loading types: {e}", exc_info=True)
            self._status_label.setText(f"Error: {e}")

    def _on_search_changed(self, search_text: str) -> None:
        """Handle search text changes.

        Args:
            search_text: New search text

        """
        self._apply_filters()

    def _on_filters_changed(self, filters: dict) -> None:
        """Handle filter changes.

        Args:
            filters: New filter settings

        """
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Apply current search and filter settings."""
        search_text = self._search_bar.get_text().lower()
        filters = self._filter_panel.get_filters()

        # Start with all types
        filtered = self._all_types

        # Apply published filter
        if filters.get("published_only", True):
            filtered = [t for t in filtered if t.published]

        # Apply category filter
        category_id = filters.get("category_id")
        if category_id is not None:
            filtered = self._sde_manager.get_types_by_category(category_id)
            if filters.get("published_only", True):
                filtered = [t for t in filtered if t.published]

        # Apply group filter
        group_id = filters.get("group_id")
        if group_id is not None:
            filtered = self._sde_manager.get_types_by_group(group_id)
            if filters.get("published_only", True):
                filtered = [t for t in filtered if t.published]

        # Apply search filter
        if search_text:
            filtered = [
                t
                for t in filtered
                if search_text in t.name.en.lower() or search_text in str(t.id)
            ]

        self._filtered_types = filtered
        self._table_model.update_types(filtered)
        self._status_label.setText(f"Showing {len(filtered)} types")

    def _on_selection_changed(self) -> None:
        """Handle table selection changes."""
        selection = self._table_view.selectionModel().selectedRows()
        if not selection:
            self._details_text.clear()
            return

        row = selection[0].row()
        eve_type = self._table_model.get_type_at_row(row)
        if eve_type:
            self._show_type_details(eve_type)

    def _show_type_details(self, eve_type: EveType) -> None:
        """Show detailed information about a type.

        Args:
            eve_type: EveType object to display

        """
        details = []
        details.append(f"<b>ID:</b> {eve_type.id}")
        details.append(f"<b>Name:</b> {eve_type.name.en}")

        if eve_type.description and hasattr(eve_type.description, "en"):
            desc = eve_type.description.en[:200]
            if len(eve_type.description.en) > 200:
                desc += "..."
            details.append(f"<b>Description:</b> {desc}")

        details.append(f"<b>Published:</b> {'Yes' if eve_type.published else 'No'}")

        if eve_type.group_id is not None:
            group = self._sde_manager.get_group_by_id(eve_type.group_id)
            if group:
                details.append(f"<b>Group:</b> {group.name.en} (ID: {group.id})")

        if eve_type.market_group_id is not None:
            details.append(f"<b>Market Group ID:</b> {eve_type.market_group_id}")

        if eve_type.base_price is not None:
            details.append(f"<b>Base Price:</b> {eve_type.base_price:,.2f} ISK")

        if eve_type.volume is not None:
            details.append(f"<b>Volume:</b> {eve_type.volume:,.2f} m³")

        if eve_type.mass is not None:
            details.append(f"<b>Mass:</b> {eve_type.mass:,.2f} kg")

        self._details_text.setHtml("<br>".join(details))
