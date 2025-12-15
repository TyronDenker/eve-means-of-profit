"""Advanced nested filter widget for table views.

Provides type-aware filter rows and logical grouping (AND/OR) similar to the
screenshots. Produces a JSON-serializable filter specification and a callable
predicate that can be consumed by a proxy model.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


@dataclass
class ColumnSpec:
    key: str
    title: str
    type: str  # 'text' | 'int' | 'float' | 'bool' | 'enum' | 'any'
    enum_values: list[str] | None = None


class FilterWidget(QWidget):
    """Type-aware nested filter UI."""

    filter_changed = pyqtSignal(dict)  # Emits JSON-serializable filter spec

    def __init__(
        self,
        columns: list[ColumnSpec],
        parent: QWidget | None = None,
        settings_key: str | None = None,
    ):
        super().__init__(parent)
        # Add special 'Any Column' spec for searching across all columns
        self._columns = [
            ColumnSpec("__any__", "Any Column", "text"),
            *columns,
        ]
        self._original_columns = columns  # Keep original for 'any' column filtering
        self._groups: list[FilterGroup] = []
        self._current_preset_name: str | None = None
        self._settings_key = settings_key
        # Debounce timer for persisting filter state to reduce frequent writes
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(400)  # ms
        self._persist_timer.timeout.connect(self._persist_state)
        self._setup_ui()

    # Removed custom theme styling; rely on platform defaults for readability

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Visual separator between toolbar and groups
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(sep)

        # Toolbar
        toolbar = QHBoxLayout()
        self.add_btn = QPushButton("Add Group")
        self.clear_btn = QPushButton("Clear All")
        self.save_preset_btn = QPushButton("Save Preset...")
        self.load_preset_btn = QPushButton("Load Preset...")
        self.export_btn = QPushButton("Export")
        self.show_chk = QToolButton()
        self.show_chk.setText("Show Filters")
        self.show_chk.setCheckable(True)
        self.show_chk.setChecked(True)

        # Preset name label
        self.preset_label = QLabel("")

        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.clear_btn)
        toolbar.addWidget(self.save_preset_btn)
        toolbar.addWidget(self.load_preset_btn)
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.preset_label)
        toolbar.addStretch()
        toolbar.addWidget(self.show_chk)
        layout.addLayout(toolbar)

        container_widget = QWidget()
        self.groups_container_widget = container_widget
        self.groups_container = QVBoxLayout(container_widget)
        self.groups_container.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(container_widget)

        self.add_btn.clicked.connect(self._on_add_group)
        self.clear_btn.clicked.connect(self._on_clear)
        self.save_preset_btn.clicked.connect(self._on_save_preset)
        self.load_preset_btn.clicked.connect(self._on_load_preset)
        # Toggle only the groups area so the toolbar remains visible
        self.show_chk.toggled.connect(self._on_toggle_filters)

        # Add an initial group
        self._on_add_group()

        # Load last filter state from persistence
        self._load_persisted_state()

    def _on_add_group(self) -> None:
        group = FilterGroup(self._columns)
        group.filter_changed.connect(self._emit_spec)
        group.remove_requested.connect(lambda g=group: self._remove_group(g))
        self._groups.append(group)
        self.groups_container.addWidget(group)
        self._emit_spec()

    def _on_toggle_filters(self, show: bool) -> None:
        self.groups_container_widget.setVisible(show)

    def _remove_group(self, group: FilterGroup) -> None:
        try:
            self._groups.remove(group)
        except ValueError:
            return
        group.setParent(None)
        group.deleteLater()
        self._emit_spec()

    def _on_clear(self) -> None:
        for g in list(self._groups):
            self._remove_group(g)
        self._on_add_group()

    def _on_save_preset(self) -> None:
        """Save current filter configuration as a named preset."""
        name, ok = QInputDialog.getText(
            self,
            "Save Preset",
            "Enter preset name:",
            text=self._current_preset_name or "",
        )
        if ok and name:
            spec = self.get_spec()
            self._save_preset(name, spec)
            self._current_preset_name = name
            self.preset_label.setText(f"Preset: {name}")

    def _on_load_preset(self) -> None:
        """Load a saved filter preset."""
        presets = self._get_preset_names()
        if not presets:
            QMessageBox.information(self, "No Presets", "No saved presets found.")
            return
        name, ok = QInputDialog.getItem(
            self, "Load Preset", "Select preset:", presets, 0, False
        )
        if ok and name:
            spec = self._load_preset(name)
            if spec:
                self._apply_spec(spec)
                self._current_preset_name = name
                self.preset_label.setText(f"Preset: {name}")

    def _save_preset(self, name: str, spec: dict) -> None:
        """Save preset to UI settings as JSON string."""
        if not self._settings_key:
            return
        sm = get_settings_manager()
        ui = sm.get_ui_settings(self._settings_key)
        try:
            current = json.loads(ui.filter_presets) if ui.filter_presets else {}
        except json.JSONDecodeError:
            logger.debug("Failed to parse filter presets JSON, starting fresh")
            current = {}
        current[name] = spec
        sm.update_ui_settings(self._settings_key, filter_presets=json.dumps(current))

    def _load_preset(self, name: str) -> dict | None:
        """Load preset from UI settings."""
        if not self._settings_key:
            return None
        sm = get_settings_manager()
        ui = sm.get_ui_settings(self._settings_key)
        try:
            presets = json.loads(ui.filter_presets) if ui.filter_presets else {}
        except json.JSONDecodeError:
            logger.debug("Failed to parse filter presets JSON for loading")
            presets = {}
        return presets.get(name)

    def _get_preset_names(self) -> list[str]:
        """Get list of saved preset names from UI settings."""
        if not self._settings_key:
            return []
        sm = get_settings_manager()
        ui = sm.get_ui_settings(self._settings_key)
        try:
            presets = json.loads(ui.filter_presets) if ui.filter_presets else {}
        except json.JSONDecodeError:
            logger.debug("Failed to parse filter presets JSON for listing")
            presets = {}
        return list(presets.keys())

    def _load_persisted_state(self) -> None:
        """Load last filter state from UI settings if configured."""
        if not self._settings_key:
            return
        sm = get_settings_manager()
        ui = sm.get_ui_settings(self._settings_key)
        if ui.active_filter:
            try:
                state = json.loads(ui.active_filter)
                self._apply_spec(state)
            except Exception:
                pass

    def _persist_state(self) -> None:
        """Persist current filter state to UI settings if configured."""
        if not self._settings_key:
            return
        sm = get_settings_manager()
        spec = self.get_spec()
        sm.update_ui_settings(self._settings_key, active_filter=json.dumps(spec))

    def _apply_spec(self, spec: dict) -> None:
        """Apply a filter specification to the UI."""
        # Clear existing groups
        for g in list(self._groups):
            self._remove_group(g)
        # Reconstruct from spec
        for group_spec in spec.get("groups", []):
            group = FilterGroup(self._columns)
            group.apply_spec(group_spec)
            group.filter_changed.connect(self._emit_spec)
            group.remove_requested.connect(lambda g=group: self._remove_group(g))
            self._groups.append(group)
            self.groups_container.addWidget(group)
        if not self._groups:
            self._on_add_group()
        self._emit_spec()

    def get_spec(self) -> dict:
        """Get current filter specification."""
        return {
            "op": "AND",
            "groups": [g.to_spec() for g in self._groups],
        }

    def _emit_spec(self) -> None:
        spec = self.get_spec()
        self.filter_changed.emit(spec)
        # Auto-persist state (debounced)
        try:
            self._persist_timer.start()
        except Exception:
            # Fallback to immediate persist if timer fails
            self._persist_state()

    @staticmethod
    def build_predicate(spec: dict) -> Callable[[dict[str, Any]], bool]:
        """Build a row predicate from a spec. Row is dict[column_key] -> value."""

        def eval_rule(rule: dict, row: dict[str, Any]) -> bool:
            key = rule["key"]
            op = rule["op"]
            val = rule.get("value")

            # Handle 'any column' searches
            if key == "__any__":
                # Search across all column values
                search_str = str(val or "").lower()
                for col_val in row.values():
                    if col_val is not None and search_str in str(col_val).lower():
                        return True
                return False

            rv = row.get(key)
            if rv is None:
                return False
            try:
                if op == "contains":
                    return str(val or "").lower() in str(rv).lower()
                if op == "equals":
                    return str(rv) == str(val)
                if op == "neq":
                    return str(rv) != str(val)
                if op in {"gt", "lt", "ge", "le"}:
                    if val is None:
                        return False
                    rvf = float(rv)
                    vvf = float(val)
                    if op == "gt":
                        return rvf > vvf
                    if op == "lt":
                        return rvf < vvf
                    if op == "ge":
                        return rvf >= vvf
                    if op == "le":
                        return rvf <= vvf
                if op == "is_true":
                    return bool(rv) is True
                if op == "is_false":
                    return bool(rv) is False
                if op == "in":
                    return str(rv) in [str(x) for x in (val or [])]
            except Exception:
                return False
            return False

        def eval_group(group: dict, row: dict[str, Any]) -> bool:
            # Skip disabled groups
            if not group.get("enabled", True):
                return True  # Disabled groups don't filter anything

            rule_results = [
                eval_rule(r, row)
                for r in group.get("rules", [])
                if r.get("enabled", True)  # Only evaluate enabled rules
            ]
            subgroup_specs = group.get("groups", [])
            subgroup_results = [eval_group(g, row) for g in subgroup_specs]
            combined = rule_results + subgroup_results
            if not combined:
                return True
            return all(combined) if group.get("op") == "AND" else any(combined)

        def predicate(row: dict[str, Any]) -> bool:
            groups = spec.get("groups", [])
            if not groups:
                return True
            group_results = [eval_group(g, row) for g in groups]
            return all(group_results) if spec.get("op") == "AND" else any(group_results)

        return predicate


class FilterGroup(QFrame):
    """A group of filter rules combined with AND/OR."""

    filter_changed = pyqtSignal()
    remove_requested = pyqtSignal()

    def __init__(self, columns: list[ColumnSpec]):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self._columns = columns
        self._rows: list[FilterRow] = []
        self._enabled = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(4)

        header = QHBoxLayout()

        # Enable/disable checkbox
        self.enabled_chk = QToolButton()
        self.enabled_chk.setText("✓")
        self.enabled_chk.setCheckable(True)
        self.enabled_chk.setChecked(True)
        self.enabled_chk.setToolTip("Enable/disable this filter group")
        self.enabled_chk.setFixedSize(24, 24)
        self.enabled_chk.toggled.connect(self._on_enabled_changed)

        self.op_combo = QComboBox()
        self.op_combo.addItems(["AND", "OR"])
        self.op_combo.setFixedHeight(24)

        remove_btn = QToolButton()
        remove_btn.setText("✖")
        remove_btn.setFixedSize(24, 24)
        remove_btn.clicked.connect(lambda: self.remove_requested.emit())

        add_row_btn = QPushButton("Add Rule")
        add_row_btn.setFixedHeight(24)
        add_row_btn.clicked.connect(self._on_add_row)

        add_group_btn = QPushButton("Add Subgroup")
        add_group_btn.setFixedHeight(24)
        add_group_btn.clicked.connect(self._on_add_group)

        self.add_row_btn = add_row_btn
        self.add_group_btn = add_group_btn
        self.remove_btn = remove_btn

        header.addWidget(self.enabled_chk)
        header.addWidget(QLabel("Group:"))
        header.addWidget(self.op_combo)
        header.addStretch()
        header.addWidget(add_row_btn)
        header.addWidget(add_group_btn)
        header.addWidget(remove_btn)
        v.addLayout(header)

        # Rows and subgroups containers with indentation
        rows_widget = QWidget()
        self.rows_container = QVBoxLayout(rows_widget)
        self.rows_container.setContentsMargins(20, 4, 0, 4)
        self.rows_container.setSpacing(4)
        v.addWidget(rows_widget)

        subgroups_widget = QWidget()
        self.subgroups_container = QVBoxLayout(subgroups_widget)
        self.subgroups_container.setContentsMargins(20, 4, 0, 4)
        self.subgroups_container.setSpacing(4)
        v.addWidget(subgroups_widget)

        self._on_add_row()

        self.op_combo.currentTextChanged.connect(lambda _: self.filter_changed.emit())

    def _on_enabled_changed(self, checked: bool) -> None:
        """Handle enable/disable checkbox."""
        self._enabled = checked
        # Only disable content, not the enable toggle itself
        self.set_content_enabled(checked)
        self.filter_changed.emit()

    def set_content_enabled(self, enabled: bool) -> None:
        """Enable/disable group content while keeping the toggle active."""
        try:
            # Header controls
            try:
                self.op_combo.setEnabled(enabled)
            except Exception:
                pass
            for btn_name in ("add_row_btn", "add_group_btn", "remove_btn"):
                btn = getattr(self, btn_name, None)
                if btn is not None:
                    try:
                        btn.setEnabled(enabled)
                    except Exception:
                        pass
            # Rows
            for row in getattr(self, "_rows", []):
                try:
                    if hasattr(row, "set_content_enabled"):
                        row.set_content_enabled(enabled)
                    else:
                        row.setEnabled(enabled)
                except Exception:
                    pass
            # Subgroups
            try:
                count = self.subgroups_container.count()
            except Exception:
                count = 0
            for i in range(count):
                item = self.subgroups_container.itemAt(i)
                w = item.widget() if item is not None else None
                if isinstance(w, FilterGroup):
                    try:
                        w.set_content_enabled(enabled)
                    except Exception:
                        pass
        except Exception:
            pass

    def _on_add_row(self) -> None:
        row = FilterRow(self._columns)
        row.filter_changed.connect(lambda: self.filter_changed.emit())
        row.remove_requested.connect(lambda r=row: self._remove_row(r))
        self._rows.append(row)
        self.rows_container.addWidget(row)
        self.filter_changed.emit()

    def _remove_row(self, row: FilterRow) -> None:
        try:
            self._rows.remove(row)
        except ValueError:
            return
        row.setParent(None)
        row.deleteLater()
        self.filter_changed.emit()

    def _on_add_group(self) -> None:
        subgroup = FilterGroup(self._columns)
        subgroup.filter_changed.connect(lambda: self.filter_changed.emit())
        subgroup.remove_requested.connect(lambda g=subgroup: self._remove_subgroup(g))
        self.subgroups_container.addWidget(subgroup)
        self.filter_changed.emit()

    def _remove_subgroup(self, subgroup: FilterGroup) -> None:
        subgroup.setParent(None)
        subgroup.deleteLater()
        self.filter_changed.emit()

    def to_spec(self) -> dict:
        # Collect subgroup specs
        sub_specs: list[dict] = []
        for i in range(self.subgroups_container.count()):
            item = self.subgroups_container.itemAt(i)
            w = item.widget() if item is not None else None
            if isinstance(w, FilterGroup):
                sub_specs.append(w.to_spec())
        return {
            "op": self.op_combo.currentText(),
            "rules": [r.to_spec() for r in self._rows],
            "groups": sub_specs,
            "enabled": self._enabled,
        }

    def apply_spec(self, spec: dict) -> None:
        """Apply a specification to this group."""
        # Set operator
        op = spec.get("op", "AND")
        idx = self.op_combo.findText(op)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)

        # Set enabled state
        self._enabled = spec.get("enabled", True)
        self.enabled_chk.setChecked(self._enabled)

        # Clear existing rows
        for r in list(self._rows):
            self._remove_row(r)

        # Add rows from spec
        for rule_spec in spec.get("rules", []):
            row = FilterRow(self._columns)
            row.apply_spec(rule_spec)
            row.filter_changed.connect(lambda: self.filter_changed.emit())
            row.remove_requested.connect(lambda r=row: self._remove_row(r))
            self._rows.append(row)
            self.rows_container.addWidget(row)

        if not self._rows:
            self._on_add_row()

        # Add subgroups from spec
        for group_spec in spec.get("groups", []):
            subgroup = FilterGroup(self._columns)
            subgroup.apply_spec(group_spec)
            subgroup.filter_changed.connect(lambda: self.filter_changed.emit())
            subgroup.remove_requested.connect(
                lambda g=subgroup: self._remove_subgroup(g)
            )
            self.subgroups_container.addWidget(subgroup)


class FilterRow(QWidget):
    """Single filter row: column + operator + value."""

    filter_changed = pyqtSignal()
    remove_requested = pyqtSignal()

    def __init__(self, columns: list[ColumnSpec]):
        super().__init__()
        self._columns = columns
        self._enabled = True
        self._setup_ui()

    def _setup_ui(self) -> None:
        g = QGridLayout(self)
        self._grid = g
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(6)

        # Enable/disable checkbox
        self.enabled_chk = QToolButton()
        self.enabled_chk.setText("✓")
        self.enabled_chk.setCheckable(True)
        self.enabled_chk.setChecked(True)
        self.enabled_chk.setToolTip("Enable/disable this filter rule")
        self.enabled_chk.setFixedSize(24, 24)
        self.enabled_chk.toggled.connect(self._on_enabled_changed)

        # Standard widget sizes
        widget_height = 24
        combo_width = 150
        edit_width = 200

        self.col_combo = QComboBox()
        self.col_combo.addItems([c.title for c in self._columns])
        self.col_combo.setFixedHeight(widget_height)
        self.col_combo.setMinimumWidth(combo_width)

        self.op_combo = QComboBox()
        self.op_combo.setFixedHeight(widget_height)
        self.op_combo.setMinimumWidth(100)

        # Editors; we'll swap based on type
        self.text_edit = QLineEdit()
        self.text_edit.setFixedHeight(widget_height)
        self.text_edit.setMinimumWidth(edit_width)

        self.int_edit = QSpinBox()
        self.int_edit.setRange(-2_147_483_648, 2_147_483_647)
        self.int_edit.setFixedHeight(widget_height)
        self.int_edit.setMinimumWidth(edit_width)

        self.float_edit = QDoubleSpinBox()
        self.float_edit.setRange(-1e12, 1e12)
        self.float_edit.setDecimals(4)
        self.float_edit.setFixedHeight(widget_height)
        self.float_edit.setMinimumWidth(edit_width)

        self.bool_combo = QComboBox()
        self.bool_combo.addItems(["True", "False"])
        self.bool_combo.setFixedHeight(widget_height)
        self.bool_combo.setMinimumWidth(edit_width)

        self.enum_combo = QComboBox()
        self.enum_combo.setFixedHeight(widget_height)
        self.enum_combo.setMinimumWidth(edit_width)

        self.remove_btn = QToolButton()
        self.remove_btn.setText("🗑")
        self.remove_btn.setFixedSize(24, 24)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit())

        g.addWidget(self.enabled_chk, 0, 0)
        g.addWidget(self.col_combo, 0, 1)
        g.addWidget(self.op_combo, 0, 2)
        g.addWidget(self.text_edit, 0, 3)
        g.addWidget(self.remove_btn, 0, 4)

        self.col_combo.currentIndexChanged.connect(self._on_column_changed)
        self.op_combo.currentIndexChanged.connect(lambda _: self.filter_changed.emit())
        self.text_edit.textChanged.connect(lambda _: self.filter_changed.emit())
        self.int_edit.valueChanged.connect(lambda _: self.filter_changed.emit())
        self.float_edit.valueChanged.connect(lambda _: self.filter_changed.emit())
        self.bool_combo.currentIndexChanged.connect(
            lambda _: self.filter_changed.emit()
        )
        self.enum_combo.currentIndexChanged.connect(
            lambda _: self.filter_changed.emit()
        )

        self._on_column_changed(0)

    def _on_enabled_changed(self, checked: bool) -> None:
        """Handle enable/disable checkbox."""
        self._enabled = checked
        # Only disable content, keep toggle active
        self.set_content_enabled(checked)
        self.filter_changed.emit()

    def set_content_enabled(self, enabled: bool) -> None:
        """Enable/disable row content while keeping the toggle active."""
        try:
            widgets = [
                self.col_combo,
                self.op_combo,
                self.text_edit,
                self.int_edit,
                self.float_edit,
                self.bool_combo,
                self.enum_combo,
                self.remove_btn,
            ]
            for w in widgets:
                try:
                    w.setEnabled(enabled)
                except Exception:
                    pass
        except Exception:
            pass

    def _on_column_changed(self, idx: int) -> None:
        spec = self._columns[idx]
        # Set operators per type
        if spec.key == "__any__" or spec.type == "text":
            ops = ["contains", "equals", "neq"]
        elif spec.type in ("int", "float"):
            ops = ["equals", "neq", "gt", "lt", "ge", "le"]
        elif spec.type == "bool":
            ops = ["is_true", "is_false"]
        elif spec.type == "enum":
            ops = ["equals", "in"]
        else:
            ops = ["contains"]

        self.op_combo.clear()
        self.op_combo.addItems(ops)

        # Swap editor
        def show(widget: QWidget) -> None:
            for w in [
                self.text_edit,
                self.int_edit,
                self.float_edit,
                self.bool_combo,
                self.enum_combo,
            ]:
                w.setVisible(False)
            widget.setVisible(True)
            # place widget in grid at column 3
            try:
                self._grid.addWidget(widget, 0, 3)
            except Exception:
                pass

        if spec.key == "__any__" or spec.type == "text":
            show(self.text_edit)
        elif spec.type == "int":
            show(self.int_edit)
        elif spec.type == "float":
            show(self.float_edit)
        elif spec.type == "bool":
            show(self.bool_combo)
        elif spec.type == "enum":
            self.enum_combo.clear()
            self.enum_combo.addItems(spec.enum_values or [])
            show(self.enum_combo)

        self.filter_changed.emit()

    def to_spec(self) -> dict:
        col = self._columns[self.col_combo.currentIndex()]
        op = self.op_combo.currentText()
        if col.type == "text" or col.key == "__any__":
            value: Any = self.text_edit.text()
        elif col.type == "int":
            value = int(self.int_edit.value())
        elif col.type == "float":
            value = float(self.float_edit.value())
        elif col.type == "bool":
            value = self.bool_combo.currentText() == "True"
        elif col.type == "enum":
            if op == "in":
                value = [self.enum_combo.currentText()]  # simplified
            else:
                value = self.enum_combo.currentText()
        else:
            value = None
        return {
            "key": col.key,
            "op": op,
            "value": value,
            "enabled": self._enabled,
        }

    def apply_spec(self, spec: dict) -> None:
        """Apply a specification to this row."""
        # Find column index by key
        key = spec.get("key", "")
        for idx, col in enumerate(self._columns):
            if col.key == key:
                self.col_combo.setCurrentIndex(idx)
                break

        # Set operator
        op = spec.get("op", "")
        op_idx = self.op_combo.findText(op)
        if op_idx >= 0:
            self.op_combo.setCurrentIndex(op_idx)

        # Set value based on type
        col = self._columns[self.col_combo.currentIndex()]
        value = spec.get("value")
        if col.type == "text" or col.key == "__any__":
            self.text_edit.setText(str(value or ""))
        elif col.type == "int":
            self.int_edit.setValue(int(value or 0))
        elif col.type == "float":
            self.float_edit.setValue(float(value or 0.0))
        elif col.type == "bool":
            bool_idx = 0 if value else 1
            self.bool_combo.setCurrentIndex(bool_idx)
        elif col.type == "enum":
            if isinstance(value, list) and value:
                enum_idx = self.enum_combo.findText(value[0])
                if enum_idx >= 0:
                    self.enum_combo.setCurrentIndex(enum_idx)
            else:
                enum_idx = self.enum_combo.findText(str(value or ""))
                if enum_idx >= 0:
                    self.enum_combo.setCurrentIndex(enum_idx)

        # Set enabled state
        self._enabled = spec.get("enabled", True)
        self.enabled_chk.setChecked(self._enabled)
