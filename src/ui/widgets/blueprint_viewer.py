"""Blueprint viewer widget for viewing blueprint details."""

import logging

from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from src.data.managers import SDEManager
from src.models.eve import EveBlueprint
from src.models.ui import BlueprintTableModel
from src.utils import format_time

logger = logging.getLogger(__name__)


class BlueprintViewer(QWidget):
    """Widget for viewing blueprint details and activities."""

    def __init__(self, sde_manager: SDEManager, parent=None):
        """Initialize the blueprint viewer.

        Args:
            sde_manager: SDEManager instance for data access
            parent: Parent widget

        """
        super().__init__(parent)
        self._sde_manager = sde_manager
        self._current_blueprint: EveBlueprint | None = None
        self._setup_ui()
        self._load_blueprints()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        main_layout = QVBoxLayout(self)

        # Header
        title = QLabel("<h2>Blueprint Viewer</h2>")
        main_layout.addWidget(title)

        # Blueprint selector
        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Select Blueprint:"))

        self._blueprint_combo = QComboBox()
        self._blueprint_combo.currentIndexChanged.connect(self._on_blueprint_changed)
        selector_layout.addWidget(self._blueprint_combo)

        main_layout.addLayout(selector_layout)

        # Blueprint info
        self._info_label = QLabel()
        main_layout.addWidget(self._info_label)

        # Activities tabs
        activities_group = QGroupBox("Activities")
        activities_layout = QVBoxLayout()

        # Activity selector
        activity_layout = QHBoxLayout()
        activity_layout.addWidget(QLabel("Activity:"))

        self._activity_combo = QComboBox()
        self._activity_combo.addItem("Manufacturing", "manufacturing")
        self._activity_combo.addItem("Research Material", "research_material")
        self._activity_combo.addItem("Research Time", "research_time")
        self._activity_combo.addItem("Copying", "copying")
        self._activity_combo.addItem("Invention", "invention")
        self._activity_combo.addItem("Reaction", "reaction")
        self._activity_combo.currentIndexChanged.connect(self._on_activity_changed)
        activity_layout.addWidget(self._activity_combo)

        activities_layout.addLayout(activity_layout)

        # Activity details
        self._activity_info_label = QLabel()
        activities_layout.addWidget(self._activity_info_label)

        # Materials table
        materials_label = QLabel("<b>Materials:</b>")
        activities_layout.addWidget(materials_label)

        self._materials_table = QTableView()
        self._materials_model = BlueprintTableModel()
        self._materials_table.setModel(self._materials_model)
        self._materials_table.setAlternatingRowColors(True)

        # Auto-resize columns
        header = self._materials_table.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(True)

        activities_layout.addWidget(self._materials_table)

        # Products table
        products_label = QLabel("<b>Products:</b>")
        activities_layout.addWidget(products_label)

        self._products_table = QTableView()
        self._products_model = BlueprintTableModel()
        self._products_table.setModel(self._products_model)
        self._products_table.setAlternatingRowColors(True)

        # Auto-resize columns
        products_header = self._products_table.horizontalHeader()
        if products_header:
            products_header.setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
            products_header.setStretchLastSection(True)

        activities_layout.addWidget(self._products_table)

        activities_group.setLayout(activities_layout)
        main_layout.addWidget(activities_group)

    def _load_blueprints(self) -> None:
        """Load blueprints into the combo box."""
        logger.info("Loading blueprints...")

        try:
            blueprints = self._sde_manager.get_all_blueprints()
            logger.info(f"Loaded {len(blueprints)} blueprints")

            # Sort blueprints by ID
            blueprints.sort(key=lambda bp: bp.id)

            # Add to combo box
            for bp in blueprints[:100]:  # Limit to first 100 for performance
                # Try to get the blueprint type name
                bp_type = self._sde_manager.get_type_by_id(bp.blueprint_type_id)
                name = bp_type.name.en if bp_type else f"Blueprint {bp.id}"
                self._blueprint_combo.addItem(name, bp)

        except Exception as e:
            logger.error(f"Error loading blueprints: {e}", exc_info=True)

    def _on_blueprint_changed(self, index: int) -> None:
        """Handle blueprint selection changes.

        Args:
            index: Index of selected blueprint

        """
        if index < 0:
            return

        blueprint = self._blueprint_combo.itemData(index)
        if blueprint:
            self._current_blueprint = blueprint
            self._show_blueprint_info()
            self._on_activity_changed(self._activity_combo.currentIndex())

    def _show_blueprint_info(self) -> None:
        """Show general blueprint information."""
        if not self._current_blueprint:
            self._info_label.clear()
            return

        bp = self._current_blueprint
        info = []
        info.append(f"<b>Blueprint ID:</b> {bp.id}")
        info.append(f"<b>Blueprint Type ID:</b> {bp.blueprint_type_id}")
        info.append(f"<b>Max Production Limit:</b> {bp.max_production_limit:,}")

        self._info_label.setText(" | ".join(info))

    def _on_activity_changed(self, index: int) -> None:
        """Handle activity selection changes.

        Args:
            index: Index of selected activity

        """
        if not self._current_blueprint:
            return

        activity_name = self._activity_combo.itemData(index)
        self._show_activity_details(activity_name)

    def _show_activity_details(self, activity_name: str) -> None:
        """Show details for a specific activity.

        Args:
            activity_name: Name of the activity to display

        """
        if not self._current_blueprint:
            return

        activity = getattr(self._current_blueprint.activities, activity_name, None)

        if not activity:
            self._activity_info_label.setText(
                f"<i>This blueprint does not have {activity_name} activity.</i>"
            )
            self._materials_model.update_materials([])
            self._products_model.update_materials([])
            return

        # Show activity info
        info_parts = []
        if hasattr(activity, "time"):
            info_parts.append(f"<b>Time:</b> {format_time(activity.time)}")

        self._activity_info_label.setText(" | ".join(info_parts) if info_parts else "")

        # Get type names for materials
        type_names = {}
        all_type_ids = set()

        # Collect all type IDs
        if hasattr(activity, "materials") and activity.materials:
            all_type_ids.update(m.type_id for m in activity.materials)
        if hasattr(activity, "products") and activity.products:
            all_type_ids.update(p.type_id for p in activity.products)

        # Fetch type names
        for type_id in all_type_ids:
            eve_type = self._sde_manager.get_type_by_id(type_id)
            if eve_type:
                type_names[type_id] = eve_type.name.en

        # Show materials
        if hasattr(activity, "materials") and activity.materials:
            self._materials_model.update_materials(activity.materials, type_names)
        else:
            self._materials_model.update_materials([])

        # Show products
        if hasattr(activity, "products") and activity.products:
            self._products_model.update_materials(activity.products, type_names)
        else:
            self._products_model.update_materials([])
