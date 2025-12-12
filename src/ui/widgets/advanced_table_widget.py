"""Advanced table widget with sorting, column reorder/show/hide, and filtering.

Wraps QTableView with a model built from list[dict] rows and integrates with
FilterWidget by accepting a predicate function. Provides context menu hooks.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtWidgets import QHeaderView, QMenu, QTableView, QWidget

from ui.styles import COLORS, AppStyles

logger = logging.getLogger(__name__)


class DictTableModel(QAbstractTableModel):
    def __init__(self, columns: list[tuple[str, str]], rows: list[dict[str, Any]]):
        super().__init__()
        self._columns = columns  # list of (key, title)
        self._rows = rows

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return len(self._rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return len(self._columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        key = self._columns[index.column()][0]
        row = self._rows[index.row()]
        val = row.get(key)
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            # Format numeric values with thousand separators
            if val is not None and isinstance(val, (int, float)):
                if isinstance(val, float):
                    # Format floats with 2 decimal places and thousand separators
                    return f"{val:,.2f}"
                # Format integers with thousand separators
                return f"{val:,}"
            return val
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._columns[section][1]
        return section + 1

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder):
        key = self._columns[column][0]
        reverse = order == Qt.SortOrder.DescendingOrder
        try:
            self.layoutAboutToBeChanged.emit()
            self._rows.sort(
                key=lambda r: (r.get(key) is None, r.get(key)), reverse=reverse
            )
            self.layoutChanged.emit()
        except Exception:
            pass

    def set_rows(self, rows: list[dict[str, Any]]):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def row_at(self, i: int) -> dict[str, Any]:
        return self._rows[i]


class AdvancedTableView(QTableView):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSortingEnabled(True)
        header = self.horizontalHeader()
        if header is not None:
            try:
                header.setStretchLastSection(False)
                header.setSectionsMovable(True)
                header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                header.customContextMenuRequested.connect(self._on_header_context_menu)
                # Compact header height
                header.setDefaultSectionSize(80)
                header.setMinimumSectionSize(40)
            except Exception:
                pass
        # Allow selecting individual cells for better copy support
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._model: DictTableModel | None = None
        self._full_rows: list[dict[str, Any]] = []
        self._predicate: Callable[[dict[str, Any]], bool] | None = None
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Make rows more compact for dense data visualization
        vert_header = self.verticalHeader()
        if vert_header is not None:
            vert_header.setDefaultSectionSize(18)  # Very compact row height
            vert_header.setMinimumSectionSize(14)  # Allow even smaller if needed
            vert_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        # Apply compact styling to reduce internal padding
        self.setStyleSheet(
            f"""
            QTableView {{
                font-size: 11px;
                gridline-color: {COLORS.BORDER_DARK};
                background-color: {COLORS.BG_LIGHT};
                color: {COLORS.TEXT_SECONDARY};
            }}
            QTableView::item {{
                padding: 1px 4px;
            }}
            QHeaderView::section {{
                font-size: 11px;
                padding: 2px 4px;
                background-color: {COLORS.BG_MEDIUM};
                color: {COLORS.TEXT_SECONDARY};
                border: 1px solid {COLORS.BORDER_DARK};
            }}
        """
            + AppStyles.SCROLLBAR
        )
        # Reduce padding and margins for a tighter look
        self.setItemDelegate(self.itemDelegate())
        self.customContextMenuRequested.connect(self._on_context_menu)
        self._context_menu_builder: Callable[[list[dict[str, Any]]], QMenu] | None = (
            None
        )

    def setup(self, columns: list[tuple[str, str]]) -> None:
        self._model = DictTableModel(columns, [])
        self.setModel(self._model)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._full_rows = rows
        self._apply_filter()

    def set_predicate(self, pred: Callable[[dict[str, Any]], bool] | None) -> None:
        self._predicate = pred
        self._apply_filter()

    def _apply_filter(self) -> None:
        if not self._model:
            return
        if self._predicate:
            filtered = [r for r in self._full_rows if self._predicate(r)]
            # Log warning if filter removes all rows but there were rows to filter
            if len(self._full_rows) > 0 and len(filtered) == 0:
                logger.warning(
                    "Filter removed all %d rows - check filter settings",
                    len(self._full_rows),
                )
        else:
            filtered = self._full_rows
        self._model.set_rows(filtered)

    def set_context_menu_builder(
        self, builder: Callable[[list[dict[str, Any]]], QMenu]
    ) -> None:
        self._context_menu_builder = builder

    def _on_context_menu(self, pos) -> None:
        if not self._context_menu_builder:
            return
        sel = self.selectionModel()
        selected_rows: list[dict[str, Any]] = []
        if self._model and sel is not None:
            try:
                # Prefer row selections when available
                row_indexes = sel.selectedRows()
                if not row_indexes:
                    # Fallback: collect unique rows from selected cell indexes
                    cell_indexes = sel.selectedIndexes()
                    unique_rows = sorted({i.row() for i in cell_indexes})
                    for r in unique_rows:
                        selected_rows.append(self._model.row_at(r))
                else:
                    for idx in row_indexes:
                        selected_rows.append(self._model.row_at(idx.row()))
            except Exception:
                pass
        menu = self._context_menu_builder(selected_rows)
        if menu:
            vp = self.viewport()
            global_pos = vp.mapToGlobal(pos) if vp is not None else None
            if global_pos is not None:
                try:
                    menu.exec(global_pos)
                except Exception:
                    pass

    def _on_header_context_menu(self, pos) -> None:
        """Show context menu for column visibility and autofit with persistent toggles."""
        if not self._model:
            return
        header = self.horizontalHeader()
        if header is None:
            return
        menu = QMenu(self)

        # Add Autofit option
        autofit_action = menu.addAction("Autofit Columns")
        if autofit_action is not None:
            autofit_action.triggered.connect(self._autofit_columns)

        # Persistent column toggles using QWidgetAction with embedded checkbox
        from PyQt6.QtWidgets import QCheckBox, QWidgetAction

        menu.addSeparator()
        for col in range(self._model.columnCount()):
            col_name = (
                self._model.headerData(
                    col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
                )
                or f"Column {col}"
            )
            try:
                action = QWidgetAction(menu)
                checkbox = QCheckBox(col_name, menu)
                checkbox.setChecked(not self.isColumnHidden(col))
                checkbox.setStyleSheet(AppStyles.CHECKBOX)

                def on_toggle(state: int, c=col):
                    try:
                        # Hide when unchecked; show when checked
                        hidden = state != int(Qt.CheckState.Checked.value)
                        self.setColumnHidden(c, hidden)
                        # Force a viewport update to reflect visibility change immediately
                        vp = self.viewport()
                        if vp is not None:
                            vp.update()
                    except Exception as e:
                        logger.warning("Column toggle failed (col=%s): %s", c, e)

                checkbox.stateChanged.connect(on_toggle)
                action.setDefaultWidget(checkbox)
                menu.addAction(action)
            except Exception:
                # Fallback to regular action if QWidgetAction fails
                logger.debug("QWidgetAction failed for column %s, using fallback", col)
                act = menu.addAction(col_name)
                if act is not None:
                    act.setCheckable(True)
                    act.setChecked(not self.isColumnHidden(col))
                    act.toggled.connect(
                        lambda checked, c=col: self.setColumnHidden(c, not checked)
                    )

        try:
            menu.exec(header.mapToGlobal(pos))
        except Exception:
            logger.debug("Failed to execute column menu", exc_info=True)

    def _autofit_columns(self) -> None:
        """Auto-fit all visible columns to their content."""
        header = self.horizontalHeader()
        if header is None:
            return
        for col in range(self._model.columnCount() if self._model else 0):
            if not self.isColumnHidden(col):
                self.resizeColumnToContents(col)
