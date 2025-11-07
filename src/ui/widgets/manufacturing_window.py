"""Manufacturing calculator window with recursive material analysis."""

import logging
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import ManufacturingService
from data.providers import SDEProvider
from utils import format_time

logger = logging.getLogger(__name__)


# Structure definitions with bonuses
STRUCTURES = {
    "NPC Station": {
        "material": 0.0,
        "time": 0.0,
        "cost": 0.0,
    },
    "Raitaru (M)": {
        "material": 0.01,
        "time": 0.15,
        "cost": 0.0,
    },
    "Azbel (L)": {
        "material": 0.01,
        "time": 0.20,
        "cost": 0.0,
    },
    "Sotiyo (XL)": {
        "material": 0.01,
        "time": 0.30,
        "cost": 0.0,
    },
}

# Rig definitions (can be combined)
RIGS = {
    "None": {"material": 0.0, "time": 0.0, "cost": 0.0},
    "T1 ME Rig": {"material": 0.02, "time": 0.0, "cost": 0.0},
    "T2 ME Rig": {"material": 0.024, "time": 0.0, "cost": 0.0},
    "T1 TE Rig": {"material": 0.0, "time": 0.20, "cost": 0.0},
    "T2 TE Rig": {"material": 0.0, "time": 0.24, "cost": 0.0},
    "T1 Cost Rig": {"material": 0.0, "time": 0.0, "cost": 0.03},
    "T2 Cost Rig": {"material": 0.0, "time": 0.0, "cost": 0.036},
}


class ManufacturingWindow(QWidget):
    """Manufacturing calculator window with recursive analysis."""

    def __init__(
        self,
        sde_provider: SDEProvider,
        manufacturing_service: ManufacturingService,
        parent=None,
    ):
        """Initialize the manufacturing window.

        Args:
            sde_provider: SDEProvider instance for data access
            manufacturing_service: ManufacturingService for calculations
            parent: Parent widget

        """
        super().__init__(parent)
        self._sde_provider = sde_provider
        self._manufacturing_service = manufacturing_service
        self._current_blueprint_id: int | None = None
        self._manufacturing_tree: dict = {}
        self._all_blueprints: list = []  # Store all loaded blueprints
        self._setup_ui()
        self._load_blueprints()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        main_layout = QVBoxLayout(self)

        # Title
        title = QLabel("<h1>Manufacturing Calculator</h1>")
        main_layout.addWidget(title)

        # Splitter for left (controls) and right (results)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Controls
        left_panel = self._create_controls_panel()
        splitter.addWidget(left_panel)

        # Right panel - Results
        right_panel = self._create_results_panel()
        splitter.addWidget(right_panel)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter)

    def _create_controls_panel(self) -> QWidget:
        """Create the controls panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Search bar
        search_group = QGroupBox("Search")
        search_layout = QVBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search blueprints by product name...")
        self._search_input.textChanged.connect(self._filter_blueprints)
        search_layout.addWidget(self._search_input)

        self._search_count_label = QLabel("")
        search_layout.addWidget(self._search_count_label)

        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # Filter options
        filter_group = QGroupBox("Filters")
        filter_layout = QVBoxLayout()

        self._filter_t1 = QCheckBox("Tech 1 Items")
        self._filter_t1.setChecked(True)
        self._filter_t1.stateChanged.connect(self._filter_blueprints)
        filter_layout.addWidget(self._filter_t1)

        self._filter_t2 = QCheckBox("Tech 2 Items")
        self._filter_t2.setChecked(True)
        self._filter_t2.stateChanged.connect(self._filter_blueprints)
        filter_layout.addWidget(self._filter_t2)

        self._filter_t3 = QCheckBox("Tech 3 Items")
        self._filter_t3.setChecked(True)
        self._filter_t3.stateChanged.connect(self._filter_blueprints)
        filter_layout.addWidget(self._filter_t3)

        self._filter_faction = QCheckBox("Faction Items")
        self._filter_faction.setChecked(True)
        self._filter_faction.stateChanged.connect(self._filter_blueprints)
        filter_layout.addWidget(self._filter_faction)

        self._filter_reactions = QCheckBox("Reactions")
        self._filter_reactions.setChecked(True)
        self._filter_reactions.stateChanged.connect(self._filter_blueprints)
        filter_layout.addWidget(self._filter_reactions)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Blueprint selection
        bp_group = QGroupBox("Blueprint Selection")
        bp_layout = QVBoxLayout()

        self._blueprint_combo = QComboBox()
        self._blueprint_combo.currentIndexChanged.connect(self._on_blueprint_changed)
        bp_layout.addWidget(QLabel("Select Blueprint:"))
        bp_layout.addWidget(self._blueprint_combo)

        bp_group.setLayout(bp_layout)
        layout.addWidget(bp_group)

        # Manufacturing parameters
        params_group = QGroupBox("Manufacturing Parameters")
        params_layout = QFormLayout()

        # Runs
        self._runs_spin = QSpinBox()
        self._runs_spin.setRange(1, 1000000)
        self._runs_spin.setValue(1)
        params_layout.addRow("Runs:", self._runs_spin)

        # ME/TE
        self._me_spin = QSpinBox()
        self._me_spin.setRange(0, 10)
        self._me_spin.setValue(10)
        params_layout.addRow("ME Level:", self._me_spin)

        self._te_spin = QSpinBox()
        self._te_spin.setRange(0, 20)
        self._te_spin.setValue(20)
        params_layout.addRow("TE Level:", self._te_spin)

        params_group.setLayout(params_layout)
        layout.addWidget(params_group)

        # Structure selection
        struct_group = QGroupBox("Structure & Rigs")
        struct_layout = QVBoxLayout()

        # Structure type
        struct_layout.addWidget(QLabel("Structure Type:"))
        self._structure_combo = QComboBox()
        self._structure_combo.addItems(STRUCTURES.keys())
        self._structure_combo.setCurrentText("Raitaru (M)")
        struct_layout.addWidget(self._structure_combo)

        # Rigs selection
        struct_layout.addWidget(QLabel("Rigs (select up to 3):"))
        self._rig_checks = []
        for rig_name in RIGS.keys():
            if rig_name != "None":
                checkbox = QCheckBox(rig_name)
                checkbox.stateChanged.connect(self._on_rig_changed)
                self._rig_checks.append(checkbox)
                struct_layout.addWidget(checkbox)

        struct_group.setLayout(struct_layout)
        layout.addWidget(struct_group)

        # System settings
        system_group = QGroupBox("System Settings")
        system_layout = QFormLayout()

        # System cost index
        self._sci_spin = QSpinBox()
        self._sci_spin.setRange(0, 100)
        self._sci_spin.setValue(2)
        self._sci_spin.setSuffix("%")
        system_layout.addRow("System Cost Index:", self._sci_spin)

        system_group.setLayout(system_layout)
        layout.addWidget(system_group)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()

        self._recursive_check = QCheckBox("Calculate intermediate manufacturing steps")
        self._recursive_check.setChecked(True)
        options_layout.addWidget(self._recursive_check)

        self._buy_intermediates_check = QCheckBox(
            "Buy intermediate products instead of crafting"
        )
        self._buy_intermediates_check.setChecked(False)
        options_layout.addWidget(self._buy_intermediates_check)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Calculate button
        calc_button = QPushButton("Calculate Manufacturing Cost")
        calc_button.clicked.connect(self._calculate)
        calc_button.setStyleSheet(
            "QPushButton { background-color: #4CAF50; color: white; "
            "font-weight: bold; padding: 10px; }"
        )
        layout.addWidget(calc_button)

        layout.addStretch()

        return panel

    def _create_results_panel(self) -> QWidget:
        """Create the results panel."""
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Tabs for different views
        self._tabs = QTabWidget()

        # Summary tab
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        self._summary_label = QLabel("Select a blueprint and click Calculate")
        self._summary_label.setWordWrap(True)
        self._summary_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        summary_layout.addWidget(self._summary_label)
        self._tabs.addTab(summary_tab, "Summary")

        # Manufacturing tree tab
        tree_tab = QWidget()
        tree_layout = QVBoxLayout(tree_tab)
        self._tree_widget = QTreeWidget()
        self._tree_widget.setHeaderLabels(
            ["Item", "Quantity", "Unit Cost", "Total Cost", "Source"]
        )
        self._tree_widget.setAlternatingRowColors(True)
        tree_layout.addWidget(self._tree_widget)
        self._tabs.addTab(tree_tab, "Manufacturing Tree")

        # Materials breakdown tab
        materials_tab = QWidget()
        materials_layout = QVBoxLayout(materials_tab)
        self._materials_table = QTableWidget()
        self._materials_table.setColumnCount(5)
        self._materials_table.setHorizontalHeaderLabels(
            ["Material", "Base Qty", "ME Adjusted", "Final Qty", "Total Cost"]
        )
        self._materials_table.setAlternatingRowColors(True)
        header = self._materials_table.horizontalHeader()
        if header:
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(True)
        materials_layout.addWidget(self._materials_table)
        self._tabs.addTab(materials_tab, "Materials Breakdown")

        layout.addWidget(self._tabs)

        return panel

    def _load_blueprints(self) -> None:
        """Load blueprints into the combo box."""
        logger.info("Loading blueprints for manufacturing window...")

        try:
            blueprints = self._sde_provider.get_all_blueprints()
            logger.info(f"Total blueprints loaded: {len(blueprints)}")

            # Filter to manufacturing OR reaction blueprints
            valid_blueprints = []

            for bp in blueprints:
                has_manufacturing = bp.activities.manufacturing is not None
                has_reaction = bp.activities.reaction is not None

                if has_manufacturing or has_reaction:
                    valid_blueprints.append(bp)

            logger.info(
                f"Valid blueprints (manufacturing or reaction): {len(valid_blueprints)}"
            )

            # Sort by ID
            valid_blueprints.sort(key=lambda bp: bp.id)

            # Store for filtering
            self._all_blueprints = []

            # Build blueprint data with metadata
            for bp in valid_blueprints:
                bp_type = self._sde_provider.get_type_by_id(bp.blueprint_type_id)

                if not bp_type or not bp_type.name:
                    continue

                bp_name = bp_type.name.en
                product_name = ""
                product_id = None
                meta_level = 0
                is_reaction = False
                category_id = None

                # Get product info
                if bp.activities.manufacturing and bp.activities.manufacturing.products:
                    product_id = bp.activities.manufacturing.products[0].type_id
                    product_type = self._sde_provider.get_type_by_id(product_id)
                    if product_type:
                        product_name = product_type.name.en
                        # Get meta level for T1/T2/T3 detection
                        if hasattr(product_type, "meta_group_id"):
                            meta_level = product_type.meta_group_id or 0
                        # Get category
                        if product_type.group_id:
                            group = self._sde_provider.get_group_by_id(
                                product_type.group_id
                            )
                            if group:
                                category_id = group.category_id

                elif bp.activities.reaction and bp.activities.reaction.products:
                    is_reaction = True
                    product_id = bp.activities.reaction.products[0].type_id
                    product_type = self._sde_provider.get_type_by_id(product_id)
                    if product_type:
                        product_name = product_type.name.en

                display_name = (
                    f"{product_name} (BP: {bp_name})" if product_name else bp_name
                )

                self._all_blueprints.append(
                    {
                        "bp_id": bp.id,
                        "display_name": display_name,
                        "product_name": product_name.lower(),
                        "bp_name": bp_name.lower(),
                        "meta_level": meta_level,
                        "is_reaction": is_reaction,
                        "category_id": category_id,
                    }
                )

            logger.info(f"Prepared {len(self._all_blueprints)} blueprint entries")

            # Initial filter
            self._filter_blueprints()

        except Exception as e:
            logger.error(f"Error loading blueprints: {e}", exc_info=True)

    def _filter_blueprints(self) -> None:
        """Filter blueprints based on search and type filters."""
        search_text = self._search_input.text().lower()

        # Determine which meta levels to include
        include_t1 = self._filter_t1.isChecked()
        include_t2 = self._filter_t2.isChecked()
        include_t3 = self._filter_t3.isChecked()
        include_faction = self._filter_faction.isChecked()
        include_reactions = self._filter_reactions.isChecked()

        # Meta group IDs for EVE Online:
        # 1 = T1, 2 = T2, 14 = T3, 4 = Faction, 53 = T3 Cruisers
        # Reactions are separate from meta levels
        filtered = []
        for bp_data in self._all_blueprints:
            # Check search filter
            if search_text:
                matches_search = (
                    search_text in bp_data["product_name"]
                    or search_text in bp_data["bp_name"]
                )
                if not matches_search:
                    continue

            # Check type filters
            is_reaction = bp_data["is_reaction"]
            meta_level = bp_data["meta_level"]

            # Reactions filter
            if is_reaction:
                if not include_reactions:
                    continue
            else:
                # Meta level filters for manufacturing items
                passes_filter = False

                if include_t1 and meta_level in (0, 1):
                    passes_filter = True
                if include_t2 and meta_level == 2:
                    passes_filter = True
                if include_t3 and meta_level in (14, 53):
                    passes_filter = True
                if include_faction and meta_level in (3, 4, 6):
                    passes_filter = True

                if not passes_filter:
                    continue

            filtered.append(bp_data)

        # Update combo box
        self._blueprint_combo.blockSignals(True)
        self._blueprint_combo.clear()

        for bp_data in filtered:
            self._blueprint_combo.addItem(bp_data["display_name"], bp_data["bp_id"])

        self._blueprint_combo.blockSignals(False)

        # Update count label
        total = len(self._all_blueprints)
        shown = len(filtered)
        self._search_count_label.setText(f"Showing {shown} of {total} blueprints")

        # Trigger blueprint change if we have results
        if shown > 0:
            self._on_blueprint_changed(0)

    def _on_blueprint_changed(self, index: int) -> None:
        """Handle blueprint selection changes."""
        if index < 0:
            return

        self._current_blueprint_id = self._blueprint_combo.itemData(index)

    def _on_rig_changed(self, state: int) -> None:
        """Handle rig checkbox changes."""
        # Count checked rigs
        checked_count = sum(1 for checkbox in self._rig_checks if checkbox.isChecked())

        # Disable unchecked rigs if 3 are selected
        if checked_count >= 3:
            for checkbox in self._rig_checks:
                if not checkbox.isChecked():
                    checkbox.setEnabled(False)
        else:
            for checkbox in self._rig_checks:
                checkbox.setEnabled(True)

    def _get_structure_bonuses(self) -> tuple[float, float, float]:
        """Get structure bonuses based on selections.

        Returns:
            Tuple of (material_bonus, time_bonus, cost_bonus)

        """
        structure_name = self._structure_combo.currentText()
        structure_bonuses = STRUCTURES.get(structure_name, STRUCTURES["NPC Station"])

        material_bonus = structure_bonuses["material"]
        time_bonus = structure_bonuses["time"]
        cost_bonus = structure_bonuses["cost"]

        # Add rig bonuses
        for checkbox in self._rig_checks:
            if checkbox.isChecked():
                rig_name = checkbox.text()
                rig_bonuses = RIGS.get(rig_name, RIGS["None"])
                material_bonus += rig_bonuses["material"]
                time_bonus += rig_bonuses["time"]
                cost_bonus += rig_bonuses["cost"]

        return material_bonus, time_bonus, cost_bonus

    def _calculate(self) -> None:
        """Calculate manufacturing costs."""
        if not self._current_blueprint_id:
            self._summary_label.setText("Please select a blueprint first.")
            return

        try:
            # Get parameters
            runs = self._runs_spin.value()
            me_level = self._me_spin.value()
            te_level = self._te_spin.value()
            sci = self._sci_spin.value() / 100.0
            mat_bonus, time_bonus, cost_bonus = self._get_structure_bonuses()

            # Calculate
            if self._recursive_check.isChecked():
                self._calculate_recursive(
                    self._current_blueprint_id,
                    runs,
                    me_level,
                    te_level,
                    sci,
                    mat_bonus,
                    time_bonus,
                    cost_bonus,
                )
            else:
                self._calculate_simple(
                    self._current_blueprint_id,
                    runs,
                    me_level,
                    te_level,
                    sci,
                    mat_bonus,
                    time_bonus,
                    cost_bonus,
                )

        except Exception as e:
            logger.error(f"Error calculating: {e}", exc_info=True)
            self._summary_label.setText(f"Error: {e}")

    def _calculate_simple(
        self,
        bp_id: int,
        runs: int,
        me: int,
        te: int,
        sci: float,
        mat_bonus: float,
        time_bonus: float,
        cost_bonus: float,
    ) -> None:
        """Calculate simple manufacturing cost without recursion."""
        breakdown = self._manufacturing_service.calculate_manufacturing_cost(
            blueprint_id=bp_id,
            runs=runs,
            me_level=me,
            te_level=te,
            system_cost_index=sci,
            structure_material_bonus=mat_bonus,
            structure_time_bonus=time_bonus,
            structure_cost_bonus=cost_bonus,
        )

        if not breakdown:
            self._summary_label.setText("Unable to calculate costs.")
            return

        self._display_results(breakdown)

    def _calculate_recursive(
        self,
        bp_id: int,
        runs: int,
        me: int,
        te: int,
        sci: float,
        mat_bonus: float,
        time_bonus: float,
        cost_bonus: float,
    ) -> None:
        """Calculate manufacturing with recursive intermediate steps."""
        # Build manufacturing tree
        tree = self._build_manufacturing_tree(
            bp_id, runs, me, te, sci, mat_bonus, time_bonus, cost_bonus
        )

        if not tree:
            self._summary_label.setText("Unable to calculate costs.")
            return

        self._manufacturing_tree = tree
        self._display_tree_results(tree)

    def _build_manufacturing_tree(
        self,
        bp_id: int,
        runs: int,
        me: int,
        te: int,
        sci: float,
        mat_bonus: float,
        time_bonus: float,
        cost_bonus: float,
        depth: int = 0,
    ) -> dict | None:
        """Build recursive manufacturing tree.

        Args:
            bp_id: Blueprint ID
            runs: Number of runs
            me: ME level
            te: TE level
            sci: System cost index
            mat_bonus: Material bonus
            time_bonus: Time bonus
            cost_bonus: Cost bonus
            depth: Current recursion depth

        Returns:
            Dictionary with manufacturing tree data

        """
        if depth > 5:  # Prevent infinite recursion
            return None

        # Calculate this level
        breakdown = self._manufacturing_service.calculate_manufacturing_cost(
            blueprint_id=bp_id,
            runs=runs,
            me_level=me,
            te_level=te,
            system_cost_index=sci,
            structure_material_bonus=mat_bonus,
            structure_time_bonus=time_bonus,
            structure_cost_bonus=cost_bonus,
        )

        if not breakdown:
            return None

        # Check if we should buy intermediates
        buy_intermediates = self._buy_intermediates_check.isChecked()

        # Build tree node
        tree_node: dict[str, Any] = {
            "blueprint_id": bp_id,
            "breakdown": breakdown,
            "children": [],
        }

        # Process materials recursively
        if not buy_intermediates:
            for material in breakdown["materials"]:
                type_id = material["type_id"]

                # Check if this material can be manufactured
                mat_bp = self._find_blueprint_for_product(type_id)

                if mat_bp:
                    # Calculate how many runs needed
                    needed_qty = material["final_quantity"]
                    product_qty = self._get_product_quantity(mat_bp)

                    if product_qty > 0:
                        needed_runs = (needed_qty + product_qty - 1) // product_qty

                        # Recursively calculate this material
                        child_tree = self._build_manufacturing_tree(
                            mat_bp,
                            needed_runs,
                            me,
                            te,
                            sci,
                            mat_bonus,
                            time_bonus,
                            cost_bonus,
                            depth + 1,
                        )

                        if child_tree:
                            tree_node["children"].append(
                                {
                                    "material_type_id": type_id,
                                    "needed_quantity": needed_qty,
                                    "tree": child_tree,
                                }
                            )

        return tree_node

    def _find_blueprint_for_product(self, product_type_id: int) -> int | None:
        """Find blueprint that produces the given product.

        Args:
            product_type_id: Product type ID to search for

        Returns:
            Blueprint ID or None

        """
        try:
            blueprints = self._sde_provider.get_all_blueprints()

            for bp in blueprints:
                if not bp.activities.manufacturing:
                    continue

                if not bp.activities.manufacturing.products:
                    continue

                for product in bp.activities.manufacturing.products:
                    if product.type_id == product_type_id:
                        return bp.id

        except Exception as e:
            logger.error(f"Error finding blueprint: {e}")

        return None

    def _get_product_quantity(self, bp_id: int) -> int:
        """Get product quantity for a blueprint.

        Args:
            bp_id: Blueprint ID

        Returns:
            Product quantity per run

        """
        try:
            bp = self._sde_provider.get_blueprint_by_id(bp_id)
            if (
                bp
                and bp.activities.manufacturing
                and bp.activities.manufacturing.products
            ):
                return bp.activities.manufacturing.products[0].quantity
        except Exception:
            pass

        return 0

    def _display_results(self, breakdown: dict) -> None:
        """Display simple results."""
        # Build summary
        summary_lines = []
        summary_lines.append("<h2>Manufacturing Cost Summary</h2>")
        summary_lines.append("")

        # Product info
        product_type = self._sde_provider.get_type_by_id(breakdown["product_type_id"])
        if product_type:
            summary_lines.append(f"<b>Product:</b> {product_type.name.en}")
        summary_lines.append(
            f"<b>Units Produced:</b> "
            f"{breakdown['product_quantity'] * breakdown['runs']:,}"
        )
        summary_lines.append("")

        # Costs
        summary_lines.append("<h3>Costs</h3>")
        summary_lines.append(
            f"Material Cost: {breakdown['total_material_cost']:,.2f} ISK"
        )
        summary_lines.append(f"Job Cost: {breakdown['job_installation_cost']:,.2f} ISK")
        summary_lines.append(f"<b>Total Cost: {breakdown['total_cost']:,.2f} ISK</b>")
        summary_lines.append(
            f"<b>Cost per Unit: {breakdown['cost_per_unit']:,.2f} ISK</b>"
        )
        summary_lines.append("")

        # Time
        summary_lines.append("<h3>Time</h3>")
        summary_lines.append(
            f"Time per Run: {format_time(breakdown['final_time_per_run'])}"
        )
        summary_lines.append(
            f"Total Time: {format_time(breakdown['total_manufacturing_time'])}"
        )

        self._summary_label.setText("<br>".join(summary_lines))

        # Update materials table
        self._update_materials_table(breakdown["materials"])

    def _display_tree_results(self, tree: dict) -> None:
        """Display recursive tree results."""
        # Calculate totals
        total_cost = self._calculate_tree_total_cost(tree)
        breakdown = tree["breakdown"]

        # Build summary
        summary_lines = []
        summary_lines.append("<h2>Manufacturing Cost Summary (Recursive)</h2>")
        summary_lines.append("")

        # Product info
        product_type = self._sde_provider.get_type_by_id(breakdown["product_type_id"])
        if product_type:
            summary_lines.append(f"<b>Product:</b> {product_type.name.en}")
        summary_lines.append(
            f"<b>Units Produced:</b> "
            f"{breakdown['product_quantity'] * breakdown['runs']:,}"
        )
        summary_lines.append("")

        # Costs
        summary_lines.append("<h3>Total Costs (All Steps)</h3>")
        summary_lines.append(f"<b>Total Cost: {total_cost:,.2f} ISK</b>")
        units = breakdown["product_quantity"] * breakdown["runs"]
        summary_lines.append(
            f"<b>Cost per Unit: {total_cost / units if units > 0 else 0:,.2f} ISK</b>"
        )

        self._summary_label.setText("<br>".join(summary_lines))

        # Update tree widget
        self._update_tree_widget(tree)

        # Update materials table with root level
        self._update_materials_table(breakdown["materials"])

    def _calculate_tree_total_cost(self, tree: dict) -> float:
        """Calculate total cost including all child nodes."""
        total = tree["breakdown"]["total_cost"]

        for child in tree.get("children", []):
            total += self._calculate_tree_total_cost(child["tree"])

        return total

    def _update_materials_table(self, materials: list) -> None:
        """Update the materials breakdown table."""
        self._materials_table.setRowCount(len(materials))

        for row, material in enumerate(materials):
            # Material name
            name_item = QTableWidgetItem(material["type_name"])
            self._materials_table.setItem(row, 0, name_item)

            # Base quantity
            base_item = QTableWidgetItem(f"{material['base_quantity']:,}")
            base_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self._materials_table.setItem(row, 1, base_item)

            # ME adjusted
            me_item = QTableWidgetItem(f"{material['me_adjusted_quantity']:,}")
            me_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self._materials_table.setItem(row, 2, me_item)

            # Final quantity
            final_item = QTableWidgetItem(f"{material['final_quantity']:,}")
            final_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self._materials_table.setItem(row, 3, final_item)

            # Total cost
            cost_item = QTableWidgetItem(f"{material['total_cost']:,.2f} ISK")
            cost_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self._materials_table.setItem(row, 4, cost_item)

    def _update_tree_widget(self, tree: dict) -> None:
        """Update the manufacturing tree widget."""
        self._tree_widget.clear()

        # Add root item
        root_item = self._create_tree_item(tree, is_root=True)
        self._tree_widget.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def _create_tree_item(self, tree: dict, is_root: bool = False) -> QTreeWidgetItem:
        """Create a tree widget item from tree node."""
        breakdown = tree["breakdown"]

        # Get product name
        product_type = self._sde_provider.get_type_by_id(breakdown["product_type_id"])
        product_name = (
            product_type.name.en
            if product_type
            else f"Type {breakdown['product_type_id']}"
        )

        quantity = breakdown["product_quantity"] * breakdown["runs"]
        cost_per_unit = breakdown["cost_per_unit"]
        total_cost = breakdown["total_cost"]

        item = QTreeWidgetItem(
            [
                product_name,
                f"{quantity:,}",
                f"{cost_per_unit:,.2f} ISK",
                f"{total_cost:,.2f} ISK",
                "Manufacture" if is_root else "Craft",
            ]
        )

        # Add children
        for child in tree.get("children", []):
            child_item = self._create_tree_item(child["tree"])
            item.addChild(child_item)

        # Add materials that are bought
        for material in breakdown["materials"]:
            # Check if this material has a child node
            has_child = any(
                c["material_type_id"] == material["type_id"]
                for c in tree.get("children", [])
            )

            if not has_child:
                # This is a bought material
                mat_type = self._sde_provider.get_type_by_id(material["type_id"])
                mat_name = (
                    mat_type.name.en if mat_type else f"Type {material['type_id']}"
                )

                mat_item = QTreeWidgetItem(
                    [
                        mat_name,
                        f"{material['final_quantity']:,}",
                        f"{material['unit_price']:,.2f} ISK",
                        f"{material['total_cost']:,.2f} ISK",
                        "Buy",
                    ]
                )
                item.addChild(mat_item)

        return item
