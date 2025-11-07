"""Blueprint viewer widget for viewing blueprint details."""

import logging

from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core import BlueprintService, ManufacturingService
from data.providers import SDEProvider
from models.eve import EveBlueprint
from models.ui import BlueprintTableModel
from utils import format_time

logger = logging.getLogger(__name__)


class BlueprintViewer(QWidget):
    """Widget for viewing blueprint details and activities."""

    def __init__(
        self,
        sde_provider: SDEProvider,
        blueprint_service: BlueprintService | None = None,
        manufacturing_service: ManufacturingService | None = None,
        parent=None,
    ):
        """Initialize the blueprint viewer.

        Args:
            sde_provider: SDEProvider instance for data access
            blueprint_service: BlueprintService for calculations
            manufacturing_service: ManufacturingService for manufacturing calcs
            parent: Parent widget

        """
        super().__init__(parent)
        self._sde_provider = sde_provider
        self._blueprint_service = blueprint_service
        self._manufacturing_service = manufacturing_service
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

        # Create tab widget for different views
        self._tabs = QTabWidget()

        # Activities tab
        activities_tab = self._create_activities_tab()
        self._tabs.addTab(activities_tab, "Activities")

        # Manufacturing calculator tab
        manufacturing_tab = self._create_manufacturing_tab()
        self._tabs.addTab(manufacturing_tab, "Manufacturing Calculator")

        main_layout.addWidget(self._tabs)

    def _create_activities_tab(self) -> QWidget:
        """Create the activities tab."""
        tab = QWidget()
        activities_layout = QVBoxLayout(tab)

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

        return tab

    def _create_manufacturing_tab(self) -> QWidget:
        """Create the manufacturing calculator tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Parameters group
        params_group = QGroupBox("Manufacturing Parameters")
        params_layout = QFormLayout()

        # Runs
        self._runs_spin = QSpinBox()
        self._runs_spin.setRange(1, 1000000)
        self._runs_spin.setValue(1)
        self._runs_spin.valueChanged.connect(self._calculate_manufacturing)
        params_layout.addRow("Runs:", self._runs_spin)

        # ME Level
        self._me_spin = QSpinBox()
        self._me_spin.setRange(0, 10)
        self._me_spin.setValue(10)
        self._me_spin.valueChanged.connect(self._calculate_manufacturing)
        params_layout.addRow("ME Level:", self._me_spin)

        # TE Level
        self._te_spin = QSpinBox()
        self._te_spin.setRange(0, 20)
        self._te_spin.setValue(20)
        self._te_spin.valueChanged.connect(self._calculate_manufacturing)
        params_layout.addRow("TE Level:", self._te_spin)

        # System Cost Index
        self._sci_spin = QDoubleSpinBox()
        self._sci_spin.setRange(0.0, 1.0)
        self._sci_spin.setSingleStep(0.01)
        self._sci_spin.setValue(0.02)
        self._sci_spin.setDecimals(4)
        self._sci_spin.valueChanged.connect(self._calculate_manufacturing)
        params_layout.addRow("System Cost Index:", self._sci_spin)

        # Structure Material Bonus
        self._struct_mat_spin = QDoubleSpinBox()
        self._struct_mat_spin.setRange(0.0, 0.1)
        self._struct_mat_spin.setSingleStep(0.01)
        self._struct_mat_spin.setValue(0.01)
        self._struct_mat_spin.setDecimals(4)
        self._struct_mat_spin.valueChanged.connect(self._calculate_manufacturing)
        params_layout.addRow("Structure Mat Bonus:", self._struct_mat_spin)

        # Structure Time Bonus
        self._struct_time_spin = QDoubleSpinBox()
        self._struct_time_spin.setRange(0.0, 0.3)
        self._struct_time_spin.setSingleStep(0.01)
        self._struct_time_spin.setValue(0.15)
        self._struct_time_spin.setDecimals(4)
        self._struct_time_spin.valueChanged.connect(self._calculate_manufacturing)
        params_layout.addRow("Structure Time Bonus:", self._struct_time_spin)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Results group
        results_group = QGroupBox("Manufacturing Results")
        results_layout = QVBoxLayout()

        self._manufacturing_results_label = QLabel("Select a blueprint...")
        self._manufacturing_results_label.setWordWrap(True)
        results_layout.addWidget(self._manufacturing_results_label)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        # Materials breakdown group
        materials_group = QGroupBox("Materials Breakdown")
        materials_layout = QVBoxLayout()

        self._mfg_materials_table = QTableView()
        self._mfg_materials_model = BlueprintTableModel()
        self._mfg_materials_table.setModel(self._mfg_materials_model)
        self._mfg_materials_table.setAlternatingRowColors(True)

        header = self._mfg_materials_table.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(True)

        materials_layout.addWidget(self._mfg_materials_table)

        materials_group.setLayout(materials_layout)
        layout.addWidget(materials_group)

        return tab

    def _load_blueprints(self) -> None:
        """Load blueprints into the combo box."""
        logger.info("Loading blueprints...")

        try:
            blueprints = self._sde_provider.get_all_blueprints()
            logger.info(f"Loaded {len(blueprints)} blueprints")

            # Sort blueprints by ID
            blueprints.sort(key=lambda bp: bp.id)

            # Add to combo box
            for bp in blueprints[:100]:  # Limit to first 100 for performance
                # Try to get the blueprint type name
                bp_type = self._sde_provider.get_type_by_id(bp.blueprint_type_id)
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
            self._calculate_manufacturing()

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
            eve_type = self._sde_provider.get_type_by_id(type_id)
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

    def _calculate_manufacturing(self) -> None:
        """Calculate manufacturing costs using the ManufacturingService."""
        if not self._current_blueprint or not self._manufacturing_service:
            self._manufacturing_results_label.setText(
                "Manufacturing service not available or no blueprint selected."
            )
            self._mfg_materials_model.update_materials([])
            return

        # Get parameters
        runs = self._runs_spin.value()
        me_level = self._me_spin.value()
        te_level = self._te_spin.value()
        sci = self._sci_spin.value()
        struct_mat = self._struct_mat_spin.value()
        struct_time = self._struct_time_spin.value()

        try:
            # Calculate manufacturing cost
            breakdown = self._manufacturing_service.calculate_manufacturing_cost(
                blueprint_id=self._current_blueprint.id,
                runs=runs,
                me_level=me_level,
                te_level=te_level,
                system_cost_index=sci,
                structure_material_bonus=struct_mat,
                structure_time_bonus=struct_time,
            )

            if not breakdown:
                self._manufacturing_results_label.setText(
                    "Unable to calculate manufacturing costs."
                )
                self._mfg_materials_model.update_materials([])
                return

            # Format results
            results = []
            results.append("<b>Manufacturing Cost Analysis</b>")
            results.append("")
            results.append(f"<b>Product:</b> Type ID {breakdown['product_type_id']}")
            results.append(
                f"<b>Units Produced:</b> {breakdown['product_quantity'] * runs:,}"
            )
            results.append("")
            results.append("<b>--- Material Costs ---</b>")
            results.append(
                f"Total Material Cost: {breakdown['total_material_cost']:,.2f} ISK"
            )
            results.append("")
            results.append("<b>--- Time ---</b>")
            results.append(
                f"Base Time/Run: {format_time(breakdown['base_time_per_run'])}"
            )
            results.append(
                f"Final Time/Run: {format_time(breakdown['final_time_per_run'])}"
            )
            results.append(
                f"Total Time: {format_time(breakdown['total_manufacturing_time'])}"
            )
            results.append(
                f"Structure Time Bonus: "
                f"{breakdown['structure_time_bonus_percent']:.1f}%"
            )
            results.append("")
            results.append("<b>--- Job Costs ---</b>")
            results.append(
                f"Estimated Item Value: {breakdown['estimated_item_value']:,.2f} ISK"
            )
            results.append(f"System Cost Index: {breakdown['system_cost_index']:.4f}")
            results.append(
                f"Structure Material Bonus: "
                f"{breakdown['structure_material_bonus'] * 100:.2f}%"
            )
            results.append(f"Facility Tax: {breakdown['facility_tax'] * 100:.2f}%")
            results.append(f"SCC Surcharge: {breakdown['scc_surcharge'] * 100:.2f}%")
            results.append(
                f"Job Installation Cost: {breakdown['job_installation_cost']:,.2f} ISK"
            )
            results.append("")
            results.append("<b>--- Totals ---</b>")
            results.append(f"<b>Total Cost: {breakdown['total_cost']:,.2f} ISK</b>")
            results.append(f"<b>Cost/Unit: {breakdown['cost_per_unit']:,.2f} ISK</b>")

            self._manufacturing_results_label.setText("<br>".join(results))

            # Update materials table
            materials_data = []
            type_names = {}

            for mat in breakdown["materials"]:
                materials_data.append(
                    {
                        "type_id": mat["type_id"],
                        "quantity": mat["final_quantity"],
                    }
                )
                type_names[mat["type_id"]] = mat["type_name"]

            self._mfg_materials_model.update_materials(materials_data, type_names)

        except Exception as e:
            logger.error(f"Error calculating manufacturing: {e}", exc_info=True)
            self._manufacturing_results_label.setText(f"Error calculating: {e}")
            self._mfg_materials_model.update_materials([])
