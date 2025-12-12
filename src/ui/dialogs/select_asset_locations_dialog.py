"""Dialog that allows selecting asset locations via checkboxes."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from models.app import AssetLocationOption
from ui.styles import COLORS, AppStyles


class SelectAssetLocationsDialog(QDialog):
    """Checkbox-based selector for asset locations used in the Net Worth tab."""

    def __init__(
        self,
        options: list[AssetLocationOption],
        preselected_ids: list[int] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Select Asset Locations")
        self.resize(520, 480)

        self._options = options
        self._option_by_id: dict[int, AssetLocationOption] = {
            opt.location_id: opt for opt in options
        }
        self._suppress_item_signal = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Filter locations"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name, system, or ID")
        self.search_edit.setStyleSheet(AppStyles.LINE_EDIT)
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        button_row = QHBoxLayout()
        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setStyleSheet(AppStyles.BUTTON_SMALL)
        self.btn_select_none = QPushButton("Clear All")
        self.btn_select_none.setStyleSheet(AppStyles.BUTTON_SMALL)
        self.btn_select_all.clicked.connect(
            lambda: self._set_all_items(Qt.CheckState.Checked)
        )
        self.btn_select_none.clicked.connect(
            lambda: self._set_all_items(Qt.CheckState.Unchecked)
        )
        button_row.addWidget(self.btn_select_all)
        button_row.addWidget(self.btn_select_none)
        button_row.addStretch(1)
        layout.addLayout(button_row)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            AppStyles.LIST_WIDGET + AppStyles.SCROLLBAR + AppStyles.CHECKBOX
        )
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget, stretch=1)

        self.summary_label = QLabel("All locations selected")
        self.summary_label.setStyleSheet(f"color: {COLORS.TEXT_MUTED};")
        layout.addWidget(self.summary_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._populate_list(preselected_ids or [])
        self._update_summary()

    def _populate_list(self, preselected_ids: list[int]) -> None:
        preselected_set = {int(i) for i in preselected_ids}
        default_to_all = not preselected_set

        for opt in self._options:
            text = self._format_option(opt)
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, int(opt.location_id))
            searchable = self._build_search_text(opt)
            item.setData(Qt.ItemDataRole.UserRole + 1, searchable)
            checked = (
                Qt.CheckState.Checked
                if default_to_all or opt.location_id in preselected_set
                else Qt.CheckState.Unchecked
            )
            item.setCheckState(checked)
            tooltip_parts = [f"ID: {opt.location_id}"]
            if opt.system_name:
                tooltip_parts.append(f"System: {opt.system_name}")
            tooltip_parts.append(
                f"{opt.character_count} character(s), {opt.asset_count} stack(s)"
            )
            item.setToolTip(" | ".join(tooltip_parts))
            self.list_widget.addItem(item)

    @staticmethod
    def _format_option(opt: AssetLocationOption) -> str:
        prefix = opt.display_name
        if opt.system_name and opt.system_name not in prefix:
            prefix = f"{prefix} ({opt.system_name})"
        suffix = f"{opt.character_count} chars · {opt.asset_count} stacks"
        if opt.location_type:
            suffix = f"{opt.location_type.title()} · {suffix}"
        return f"{prefix}\n{suffix}"

    @staticmethod
    def _build_search_text(opt: AssetLocationOption) -> str:
        pieces = [opt.display_name.lower(), str(opt.location_id)]
        if opt.system_name:
            pieces.append(str(opt.system_name).lower())
        if opt.location_type:
            pieces.append(opt.location_type.lower())
        return " ".join(pieces)

    def _set_all_items(self, state: Qt.CheckState) -> None:
        self._suppress_item_signal = True
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is not None and item.checkState() != state:
                item.setCheckState(state)
        self._suppress_item_signal = False
        self._update_summary()

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        if self._suppress_item_signal:
            return
        self._update_summary()

    def _apply_filter(self, text: str) -> None:
        terms = [t for t in text.lower().split() if t]
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            searchable = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
            visible = all(term in searchable for term in terms)
            item.setHidden(not visible)

    def _gather_checked_ids(self) -> tuple[list[int], bool]:
        ids: list[int] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        all_selected = (
            self.list_widget.count() > 0 and len(ids) == self.list_widget.count()
        )
        return ids, all_selected

    def selected_location_ids(self) -> list[int]:
        ids, all_selected = self._gather_checked_ids()
        return [] if all_selected else ids

    def selected_location_options(self) -> list[AssetLocationOption]:
        ids, all_selected = self._gather_checked_ids()
        if all_selected:
            return []
        return [self._option_by_id[i] for i in ids if i in self._option_by_id]

    def _update_summary(self) -> None:
        ids, all_selected = self._gather_checked_ids()
        if all_selected or not self.list_widget.count():
            self.summary_label.setText("All locations selected")
            return
        if not ids:
            self.summary_label.setText(
                "No locations selected (entire Assets series will be empty)"
            )
            return
        names = [
            self._option_by_id[i].display_name for i in ids if i in self._option_by_id
        ]
        preview = ", ".join(names[:3])
        if len(names) > 3:
            preview += f" +{len(names) - 3} more"
        self.summary_label.setText(f"{len(ids)} selected ({preview})")
