"""Net worth tab with category-over-time graph.

Snapshots are created during character refresh elsewhere; this tab focuses on
viewing historical data, filtering categories/locations, and inspecting values
over time across all characters.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import pyqtgraph as pg  # type: ignore
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from models.app import AssetLocationOption, NetWorthSnapshot
from services.character_service import CharacterService
from services.networth_service import NetWorthService
from ui.dialogs.select_asset_locations_dialog import SelectAssetLocationsDialog
from ui.signal_bus import get_signal_bus
from ui.styles import COLORS, AppStyles, GraphStyles

logger = logging.getLogger(__name__)


def format_isk_short(value: float, signed: bool = False) -> str:
    """Format ISK values into b/m/k strings without scientific notation."""

    magnitude = abs(value)
    if magnitude >= 1_000_000_000:
        body = f"{magnitude / 1_000_000_000:.2f}b"
    elif magnitude >= 1_000_000:
        body = f"{magnitude / 1_000_000:.2f}m"
    elif magnitude >= 1_000:
        body = f"{magnitude / 1_000:.2f}k"
    else:
        body = f"{magnitude:.0f}"

    if signed:
        prefix = "+" if value >= 0 else "-"
    else:
        prefix = "-" if value < 0 else ""
    return f"{prefix}{body}"


class ISKAxisItem(pg.AxisItem):
    """Axis implementation that formats ticks using ISK abbreviations."""

    def tickStrings(self, values, scale, spacing):
        return [format_isk_short(value) for value in values]


class NetworthTab(QWidget):
    """UI for managing net worth snapshots and viewing history graphs."""

    # Use unified GraphStyles for all graph-related styling
    CATEGORY_FIELDS: ClassVar[list[tuple[str, str]]] = GraphStyles.get_category_fields()
    COLOR_MAP: ClassVar[dict[str, str]] = GraphStyles.COLORS
    LINE_STYLE_MAP: ClassVar[dict[str, str]] = GraphStyles.LINE_STYLES
    SYMBOL_MAP: ClassVar[dict[str, str]] = GraphStyles.SYMBOLS

    def __init__(
        self,
        networth_service: NetWorthService,
        character_service: CharacterService,
        esi_client=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._networth = networth_service
        self._characters = character_service
        self._esi_client = esi_client
        self._background_tasks: set[asyncio.Task] = set()
        self._selected_character_id: int | None = None
        self._category_visibility: dict[str, bool] = {
            label: True for _, label in self.CATEGORY_FIELDS
        }
        self._category_visibility["PLEX"] = True  # Add PLEX to visibility tracking
        now = datetime.now(UTC)
        self._date_to: datetime | None = now
        self._date_from: datetime | None = now - timedelta(days=90)
        self._character_checkboxes: dict[int, QCheckBox] = {}
        self._active_location_ids: list[int] = []
        self._last_plot_cache: dict[str, Any] = {}
        self._snapshots_by_character: dict[int, list[Any]] = {}
        self._all_snapshots: list[Any] = []
        self._selected_location_metadata: dict[int, AssetLocationOption] = {}
        self._date_range_user_set: bool = False

        # Track selection updates from Characters tab and centralized character loading
        try:
            self._signal_bus.character_selected.connect(self._on_character_selected)
            self._signal_bus.characters_loaded.connect(self._on_characters_loaded)
        except Exception:
            pass

        self._setup_ui()

    def _setup_ui(self) -> None:
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # Main horizontal splitter: graph on left, settings panel on right
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left side: Graph container
        graph_container = QWidget()
        graph_layout = QVBoxLayout(graph_container)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(6)

        # PyQtGraph plot widget with custom axis and no default context menu
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("w")
        # Enable antialiasing for smoother lines
        self._plot_widget.setAntialiasing(True)
        plot_item = self._plot_widget.getPlotItem()
        self._y_axis = ISKAxisItem(orientation="left")
        self._y_axis.setLabel("ISK")
        self._x_axis = pg.DateAxisItem(orientation="bottom")
        self._x_axis.setLabel("Time")

        if plot_item is not None:
            plot_item.setAxisItems({"left": self._y_axis, "bottom": self._x_axis})
            plot_item.setTitle("Net Worth Components Over Time (All Characters)")
            plot_item.addLegend()
            plot_item.showGrid(x=True, y=True, alpha=0.3)
            plot_item.setMenuEnabled(False)
            view_box = plot_item.getViewBox()
            if view_box is not None and hasattr(view_box, "setMenuEnabled"):
                view_box.setMenuEnabled(False)
        else:
            self._plot_widget.setLabel("left", "ISK")
            self._plot_widget.setLabel("bottom", "Time")
            self._plot_widget.setTitle(
                "Net Worth Components Over Time (All Characters)"
            )
            self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        graph_layout.addWidget(self._plot_widget, stretch=1)

        # Summary bar container - always visible with modern styling
        self._summary_bar = QFrame()
        self._summary_bar.setFrameShape(QFrame.Shape.StyledPanel)
        self._summary_bar.setStyleSheet(f"""
            QFrame {{
            background-color: {COLORS.BG_LIGHT};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 6px;
            padding: 8px;
            }}
        """)
        summary_layout = QVBoxLayout(self._summary_bar)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        summary_layout.setSpacing(8)

        # Delta label for period changes - stacked vertically
        self._delta_label = QLabel("")
        self._delta_label.setStyleSheet(f"""
            QLabel {{
            color: {COLORS.TEXT_SECONDARY};
            font-size: 12px;
            font-weight: normal;
            }}
        """)
        self._delta_label.setTextFormat(Qt.TextFormat.RichText)
        self._delta_label.setWordWrap(True)
        summary_layout.addWidget(self._delta_label, stretch=0)

        # Hover label for point details - right side
        self._hover_label = QLabel("Hover over graph for details")
        self._hover_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS.TEXT_MUTED};
                font-size: 11px;
                font-weight: normal;
            }}
        """)
        self._hover_label.setTextFormat(Qt.TextFormat.RichText)
        self._hover_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._hover_label.setMinimumWidth(200)
        summary_layout.addWidget(self._hover_label, stretch=0)

        graph_layout.addWidget(self._summary_bar)

        splitter.addWidget(graph_container)

        # Right side: Settings panel
        settings_panel = self._create_settings_panel()
        splitter.addWidget(settings_panel)

        # Set splitter sizes (graph takes most space, panel ~250px)
        splitter.setStretchFactor(0, 1)  # Graph stretches
        splitter.setStretchFactor(1, 0)  # Panel doesn't stretch
        splitter.setSizes([800, 250])

        main.addWidget(splitter, stretch=1)

        # Wire signals with asyncSlot for proper async handling
        self.date_from_edit.dateChanged.connect(self._on_from_date_changed)
        self.date_to_edit.dateChanged.connect(self._on_to_date_changed)
        self.btn_refresh_graph.clicked.connect(self._on_refresh_graph)
        self.btn_select_locations.clicked.connect(self._on_select_locations_clicked)
        self.btn_clear_locations.clicked.connect(self._on_locations_cleared)
        self.btn_select_all_chars.clicked.connect(self._on_select_all_characters)
        self.btn_clear_chars.clicked.connect(self._on_clear_characters)

        # Hover handler for plot
        try:
            scene = self._plot_widget.scene()
            if scene is not None and hasattr(scene, "sigMouseMoved"):
                self._hover_proxy = pg.SignalProxy(
                    scene.sigMouseMoved,
                    rateLimit=60,
                    slot=self._on_plot_hover,
                )
            else:
                self._hover_proxy = None
            mouse_signal = getattr(scene, "sigMouseClicked", None)
            if mouse_signal is not None and hasattr(mouse_signal, "connect"):
                mouse_signal.connect(self._on_plot_clicked)
        except Exception:
            self._hover_proxy = None

        # Initial graph load - schedule as background task
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._plot())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            # Event loop not running yet; will be called via initial load
            pass

    def _create_settings_panel(self) -> QWidget:
        """Create the vertical settings panel on the right side."""
        # Use a scroll area to handle cases when window is too small
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumWidth(250)
        scroll.setMaximumWidth(300)

        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        panel.setStyleSheet(AppStyles.PANEL_DARK)
        panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 8, 8, 8)
        panel_layout.setSpacing(12)

        # Refresh button at top
        self.btn_refresh_graph = QPushButton("↻ Refresh Graph")
        panel_layout.addWidget(self.btn_refresh_graph)

        # === Characters Section ===
        panel_layout.addWidget(self._create_section_header("Characters"))

        char_buttons = QHBoxLayout()
        char_buttons.setSpacing(4)
        self.btn_select_all_chars = QPushButton("All")
        self.btn_clear_chars = QPushButton("None")
        self.btn_select_all_chars.setMaximumWidth(60)
        self.btn_clear_chars.setMaximumWidth(60)
        char_buttons.addWidget(self.btn_select_all_chars)
        char_buttons.addWidget(self.btn_clear_chars)
        char_buttons.addStretch()
        panel_layout.addLayout(char_buttons)

        # Scrollable character checkboxes
        self._character_scroll = QScrollArea()
        self._character_scroll.setWidgetResizable(True)
        self._character_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._character_scroll.setStyleSheet(
            AppStyles.SCROLL_AREA + AppStyles.CHECKBOX + AppStyles.SCROLLBAR
        )
        self._character_scroll.setMinimumHeight(80)
        self._character_scroll.setMaximumHeight(150)

        self._character_list_widget = QWidget()
        self._character_list_layout = QVBoxLayout(self._character_list_widget)
        self._character_list_layout.setContentsMargins(0, 0, 0, 0)
        self._character_list_layout.setSpacing(2)
        self._character_list_layout.addStretch()
        self._character_scroll.setWidget(self._character_list_widget)
        panel_layout.addWidget(self._character_scroll)

        # === Categories Section ===
        # Categories are now controlled via the legend in the graph.
        # Initialize category visibility tracking (all categories visible by default)
        self.category_checkboxes: dict[str, QCheckBox] = {}
        for _, label in self.CATEGORY_FIELDS:
            # Create checkbox but don't add to layout - keep for internal tracking
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet(AppStyles.CHECKBOX)
            # Don't connect to UI since we're removing the checkboxes from the panel
            self.category_checkboxes[label] = cb

        # === Date Range Section ===
        panel_layout.addWidget(self._create_section_header("Date Range"))

        # From date
        from_layout = QHBoxLayout()
        from_layout.setSpacing(4)
        from_label = QLabel("From:")
        from_label.setMinimumWidth(35)
        self.date_from_edit = QDateEdit()
        self.date_from_edit.setCalendarPopup(True)
        self.date_from_edit.setDisplayFormat("yyyy-MM-dd")
        self._configure_date_edit(self.date_from_edit)
        self._set_date_edit(self.date_from_edit, self._date_from)
        from_layout.addWidget(from_label)
        from_layout.addWidget(self.date_from_edit, stretch=1)
        panel_layout.addLayout(from_layout)

        # To date
        to_layout = QHBoxLayout()
        to_layout.setSpacing(4)
        to_label = QLabel("To:")
        to_label.setMinimumWidth(35)
        self.date_to_edit = QDateEdit()
        self.date_to_edit.setCalendarPopup(True)
        self.date_to_edit.setDisplayFormat("yyyy-MM-dd")
        self._configure_date_edit(self.date_to_edit)
        self._set_date_edit(self.date_to_edit, self._date_to)
        to_layout.addWidget(to_label)
        to_layout.addWidget(self.date_to_edit, stretch=1)
        panel_layout.addLayout(to_layout)

        # Quick date preset buttons
        presets_label = QLabel("Quick presets:")
        presets_label.setStyleSheet(f"color: {COLORS.TEXT_MUTED}; font-size: 11px;")
        panel_layout.addWidget(presets_label)

        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(4)
        for label, days in [
            ("7d", 7),
            ("30d", 30),
            ("90d", 90),
            ("1y", 365),
            ("All", None),
        ]:
            btn = QPushButton(label)
            btn.setMaximumWidth(45)
            btn.clicked.connect(lambda checked, d=days: self._on_date_preset(d))
            presets_layout.addWidget(btn)
        panel_layout.addLayout(presets_layout)

        # === Asset Locations Section ===
        panel_layout.addWidget(self._create_section_header("Asset Locations"))

        loc_buttons = QHBoxLayout()
        loc_buttons.setSpacing(4)
        self.btn_select_locations = QPushButton("Select…")
        self.btn_select_locations.setToolTip(
            "Choose which asset locations should contribute to the Assets series"
        )
        self.btn_clear_locations = QPushButton("Clear")
        loc_buttons.addWidget(self.btn_select_locations)
        loc_buttons.addWidget(self.btn_clear_locations)
        loc_buttons.addStretch()
        panel_layout.addLayout(loc_buttons)

        self.location_summary_label = QLabel("All locations")
        self.location_summary_label.setStyleSheet(
            f"color: {COLORS.TEXT_SECONDARY}; font-size: 11px;"
        )
        self.location_summary_label.setWordWrap(True)
        panel_layout.addWidget(self.location_summary_label)
        self._update_location_summary()

        # Add stretch at the end to push everything up
        panel_layout.addStretch()

        # Wrap panel in scroll area for small window support
        scroll.setWidget(panel)
        return scroll

    def _create_section_header(self, title: str) -> QLabel:
        """Create a styled section header label."""
        header = QLabel(title)
        header.setStyleSheet(AppStyles.LABEL_HEADER)
        return header

    def _on_date_preset(self, days: int | None) -> None:
        """Handle quick date preset button clicks."""
        # Presets are a user action; lock the auto-ranging behavior
        self._date_range_user_set = True
        now = datetime.now(UTC)
        self._date_to = now
        self._set_date_edit(self.date_to_edit, self._date_to)

        if days is None:
            # "All" - set to earliest possible date or clear minimum
            if self._all_snapshots:
                earliest = min(
                    s.snapshot_time
                    for s in self._all_snapshots
                    if hasattr(s, "snapshot_time")
                )
                self._date_from = earliest
            else:
                # Default to 1 year if no data yet
                self._date_from = now - timedelta(days=365)
        else:
            self._date_from = now - timedelta(days=days)

        self._set_date_edit(self.date_from_edit, self._date_from)
        self._schedule_plot_refresh()

    def _schedule_plot_refresh(self) -> None:
        try:
            asyncio.create_task(self._plot())
        except Exception:
            pass

    def _current_date_filters(self) -> tuple[datetime | None, datetime | None]:
        return self._date_from, self._date_to

    def _on_from_date_changed(self, qdate: QDate) -> None:
        self._date_range_user_set = True
        self._date_from = self._qdate_to_datetime(qdate, start_of_day=True)
        self._ensure_date_order()
        self._schedule_plot_refresh()

    def _on_to_date_changed(self, qdate: QDate) -> None:
        self._date_range_user_set = True
        self._date_to = self._qdate_to_datetime(qdate, start_of_day=False)
        self._ensure_date_order()
        self._schedule_plot_refresh()

    def _ensure_date_order(self) -> None:
        if (
            self._date_from is not None
            and self._date_to is not None
            and self._date_from > self._date_to
        ):
            self._date_to = self._date_from
            if hasattr(self, "date_to_edit"):
                self._set_date_edit(self.date_to_edit, self._date_to)

    def _on_category_toggle(self, _state: int) -> None:
        for label, cb in self.category_checkboxes.items():
            self._category_visibility[label] = cb.isChecked()
        self._schedule_plot_refresh()

    @asyncSlot()
    async def _on_select_locations_clicked(self) -> None:
        try:
            char_ids = await self._get_all_character_ids()
            if not char_ids:
                self._signal_bus.info_message.emit(
                    "No characters available to load asset locations."
                )
                return

            if not hasattr(self._networth, "list_asset_locations"):
                self._signal_bus.error_occurred.emit(
                    "Location picker is not available in this build."
                )
                return

            options = await self._networth.list_asset_locations(character_ids=char_ids)
            if not options:
                self._signal_bus.info_message.emit(
                    "No cached asset locations yet. Refresh assets first."
                )
                return

            dialog = SelectAssetLocationsDialog(
                options,
                preselected_ids=self._active_location_ids,
                parent=self,
            )
            if dialog.exec():
                selected_ids = dialog.selected_location_ids()
                selected_options = dialog.selected_location_options()
                self._active_location_ids = selected_ids
                self._update_location_summary(selected_options)
                await self._plot()
        except Exception:
            logger.exception("Failed to open asset location picker")
            self._signal_bus.error_occurred.emit(
                "Unable to load asset locations; see logs."
            )

    def _on_locations_cleared(self) -> None:
        if not self._active_location_ids:
            return
        self._active_location_ids = []
        self._selected_location_metadata.clear()
        self._update_location_summary()
        self._schedule_plot_refresh()

    def _update_location_summary(
        self, selected_options: list[AssetLocationOption] | None = None
    ) -> None:
        if selected_options is not None:
            self._selected_location_metadata = {
                opt.location_id: opt for opt in selected_options
            }

        if not getattr(self, "location_summary_label", None):
            return

        if not self._active_location_ids:
            self.location_summary_label.setText("All locations")
            return

        names: list[str] = []
        for loc_id in self._active_location_ids:
            opt = self._selected_location_metadata.get(loc_id)
            if opt:
                label = opt.display_name
                if opt.system_name and opt.system_name not in label:
                    label = f"{label} ({opt.system_name})"
                names.append(label)
            else:
                names.append(str(loc_id))

        preview = ", ".join(names[:3])
        if len(names) > 3:
            preview += f" +{len(names) - 3} more"

        self.location_summary_label.setText(
            f"{len(self._active_location_ids)} selected ({preview})"
        )

    def _rebuild_character_filters(self, characters: list) -> None:
        """Build checkbox filters for available characters in the vertical panel."""

        # Clear existing checkboxes from the layout
        try:
            # Remove all items except the stretch at the end
            while self._character_list_layout.count() > 1:
                item = self._character_list_layout.takeAt(0)
                widget = item.widget() if item else None
                if widget is not None:
                    widget.deleteLater()
        except Exception:
            pass

        self._character_checkboxes.clear()

        if not characters:
            return

        for ch in characters:
            cid = getattr(ch, "character_id", None)
            name = getattr(ch, "character_name", str(cid))
            if cid is None:
                continue

            cb = QCheckBox(name)
            cb.setChecked(True)
            cb.setStyleSheet(AppStyles.CHECKBOX)
            cb.setProperty("character_id", cid)
            cb.stateChanged.connect(
                lambda _state, c=cid: self._on_character_filter_changed()
            )
            self._character_checkboxes[int(cid)] = cb
            # Insert before the stretch
            self._character_list_layout.insertWidget(
                self._character_list_layout.count() - 1, cb
            )

    def _on_character_filter_changed(self) -> None:
        self._schedule_plot_refresh()

    def _on_select_all_characters(self) -> None:
        for cb in self._character_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._on_character_filter_changed()

    def _on_clear_characters(self) -> None:
        for cb in self._character_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._on_character_filter_changed()

    def _on_character_selected(self, character_id: int) -> None:
        self._selected_character_id = character_id
        # Selection no longer alters endpoint timers (removed)

    @asyncSlot()
    @asyncSlot()
    async def _on_refresh_graph(self) -> None:
        if self._date_range_user_set:
            await self._plot()
        else:
            await self._plot_and_set_date_bounds()

    async def _get_all_character_ids(self) -> list[int]:
        # Return only selected checkboxes - if none selected, return empty list
        # to show empty graph (per task tracking requirement)
        selected = [
            cid for cid, cb in self._character_checkboxes.items() if cb.isChecked()
        ]
        if self._character_checkboxes:
            # Checkboxes exist - return only selected (empty list shows empty graph)
            return selected
        # No checkboxes yet - fall back to all characters for initial load
        try:
            chars = await self._characters.get_authenticated_characters()
            return [c.character_id for c in chars]
        except Exception:
            logger.debug("Failed to query characters", exc_info=True)
            return []

    async def _load_all_snapshots(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> list[Any]:
        # Pull a reasonable number of snapshots per character and combine
        try:
            ids = await self._get_all_character_ids()
            all_snaps = []
            # Allow callers to override the date window (for auto-ranging)
            if start is None or end is None:
                start, end = self._current_date_filters()
            for cid in ids:
                snaps = await self._networth.get_networth_history(
                    cid,
                    limit=None,
                    start=start,
                    end=end,
                )
                all_snaps.extend(snaps)
            # Sort by time
            all_snaps.sort(key=lambda s: s.snapshot_time)
            self._all_snapshots = list(all_snaps)
            self._snapshots_by_character = defaultdict(list)
            for snap in all_snaps:
                try:
                    self._snapshots_by_character[int(snap.character_id)].append(snap)
                except Exception:
                    continue
            return all_snaps
        except Exception:
            logger.exception("Failed to load net worth snapshots")
            self._all_snapshots = []
            self._snapshots_by_character = defaultdict(list)
            return []

    async def _load_snapshot_groups_and_data(
        self, start: datetime | None = None, end: datetime | None = None
    ) -> tuple[list[dict], dict[int, list[NetWorthSnapshot]], dict[int, list[dict]]]:
        """Load snapshot groups and their associated character/PLEX data.

        Returns:
            Tuple of (groups list, char snapshots by group_id, plex snapshots by group_id)
        """
        try:
            # Load snapshot groups in range - ORDER BY ASC to process chronologically
            groups = await self._networth._repo.fetchall(
                """
                SELECT snapshot_group_id, account_id, refresh_source, created_at, label
                FROM networth_snapshot_groups
                WHERE (? IS NULL OR created_at >= ?)
                  AND (? IS NULL OR created_at <= ?)
                ORDER BY created_at ASC
                """,
                (
                    start.isoformat() if start else None,
                    start.isoformat() if start else None,
                    end.isoformat() if end else None,
                    end.isoformat() if end else None,
                ),
            )
            groups = [dict(g) for g in groups]

            # Load character snapshots for each group
            char_snaps_by_group: dict[int, list[NetWorthSnapshot]] = {}
            plex_snaps_by_group: dict[int, list[dict]] = {}

            for group in groups:
                group_id = int(group["snapshot_group_id"])

                # Get character snapshots for this group
                char_snaps = await self._networth._repo.fetchall(
                    """
                    SELECT snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
                           total_asset_value, wallet_balance, market_escrow, market_sell_value,
                           contract_collateral, contract_value, industry_job_value, plex_vault
                    FROM networth_snapshots
                    WHERE snapshot_group_id = ?
                    ORDER BY character_id
                    """,
                    (group_id,),
                )
                if char_snaps:
                    char_snaps_by_group[group_id] = [
                        NetWorthSnapshot(**dict(s)) for s in char_snaps
                    ]

                # Get PLEX snapshots for this group
                plex_snaps = await self._networth._repo.fetchall(
                    """
                    SELECT plex_snapshot_id, account_id, snapshot_group_id, snapshot_time,
                           plex_units, plex_unit_price, plex_total_value
                    FROM account_plex_snapshots
                    WHERE snapshot_group_id = ?
                    """,
                    (group_id,),
                )
                if plex_snaps:
                    plex_snaps_by_group[group_id] = [dict(p) for p in plex_snaps]
                    logger.debug(
                        "Loaded %d PLEX snapshots for group %d",
                        len(plex_snaps),
                        group_id,
                    )
                else:
                    logger.debug("No PLEX snapshots found for group %d", group_id)

            return groups, char_snaps_by_group, plex_snaps_by_group
        except Exception:
            logger.exception("Failed to load snapshot groups and data")
            return [], {}, {}

    async def _plot(self) -> None:
        """Plot net worth from snapshot groups with PLEX as separate series.

        Groups snapshots by snapshot_group_id for stable aggregation.
        Each graph point represents one snapshot group (Refresh All or Refresh Account).
        PLEX is displayed as a separate series.
        """
        try:
            # If the user hasn't locked the date range, query without an upper bound
            start, end = self._current_date_filters()
            query_end = end if self._date_range_user_set else None

            # Load both snapshot groups for graph and individual snapshots for editing
            (
                groups,
                char_snaps_by_group,
                plex_snaps_by_group,
            ) = await self._load_snapshot_groups_and_data(start, query_end)
            await self._load_all_snapshots(
                start=start, end=query_end
            )  # Keep for edit dialog compatibility

            # If the user hasn't manually set a date range, auto-extend to latest data
            if groups and not self._date_range_user_set:
                try:
                    latest_group_time = max(
                        datetime.fromisoformat(str(g["created_at"]))
                        for g in groups
                        if g.get("created_at")
                    )
                    if self._date_to is None or latest_group_time > self._date_to:
                        self._date_to = latest_group_time
                        self._set_date_edit(self.date_to_edit, self._date_to)
                except Exception:
                    logger.debug("Failed to auto-extend date range", exc_info=True)

            # Clear existing plot and legend
            self._plot_widget.clear()
            self._hover_label.setText("Hover over graph for details")

            # Properly clear and recreate legend
            plot_item = self._plot_widget.getPlotItem()
            if plot_item is not None:
                # Remove old legend completely
                if plot_item.legend is not None:
                    plot_item.legend.scene().removeItem(plot_item.legend)
                    plot_item.legend = None
                # Create fresh legend
                plot_item.addLegend()

            if not groups:
                logger.debug("No snapshot groups available to plot")
                self._last_plot_cache = {}
                return

            # Get character IDs for filtering
            ids = await self._get_all_character_ids()

            # Compute filtered assets if location filter is active
            filtered_assets: dict[int, float] = {}
            if self._active_location_ids:
                for cid in ids:
                    try:
                        filtered_assets[
                            cid
                        ] = await self._networth.calculate_assets_for_locations(
                            cid, include_locations=self._active_location_ids
                        )
                    except Exception:
                        logger.debug(
                            "Failed to compute filtered assets for %s",
                            cid,
                            exc_info=True,
                        )

            # Build aggregation per group
            # Keep track of group_ids in order to maintain timestamp-data alignment
            ordered_group_ids: list[int] = []
            group_timestamps: list[float] = []
            group_data: dict[int, dict[str, float]] = {}
            group_metadata: dict[int, dict[str, Any]] = {}

            for group in groups:
                group_id = int(group["snapshot_group_id"])
                try:
                    group_time = datetime.fromisoformat(str(group["created_at"]))
                except Exception:
                    logger.debug("Failed to parse group time for group %d", group_id)
                    continue

                # Initialize category buckets
                bucket_values: dict[str, float] = {
                    label: 0.0 for _, label in self.CATEGORY_FIELDS
                }
                bucket_values["PLEX"] = 0.0  # Add PLEX category

                # Get snapshot per character FROM THIS GROUP ONLY
                # For each character, get the snapshot from the current snapshot_group_id
                try:
                    char_snaps = await self._networth._repo.fetchall(
                        """
                        SELECT
                            snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
                            total_asset_value,
                            wallet_balance, market_escrow, market_sell_value,
                            contract_collateral, contract_value, industry_job_value, plex_vault
                        FROM networth_snapshots
                        WHERE snapshot_group_id = ?
                        ORDER BY character_id
                        """,
                        (group_id,),
                    )
                    char_snaps = [NetWorthSnapshot(**dict(s)) for s in char_snaps]
                except Exception:
                    logger.debug(
                        "Failed to get snapshots for group %d", group_id, exc_info=True
                    )
                    char_snaps = []

                # For characters not in this group, get their latest snapshot up to group_time
                char_snaps_by_id = {snap.character_id: snap for snap in char_snaps}
                chars_with_missing_snaps = [
                    cid for cid in ids if cid not in char_snaps_by_id
                ]

                if chars_with_missing_snaps:
                    try:
                        # Get latest snapshot for each missing character up to group_time
                        fallback_snaps = await self._networth._repo.fetchall(
                            f"""
                            SELECT
                                snapshot_id, character_id, account_id, snapshot_group_id, snapshot_time,
                                total_asset_value,
                                wallet_balance, market_escrow, market_sell_value,
                                contract_collateral, contract_value, industry_job_value, plex_vault
                            FROM (
                                SELECT ns.*,
                                       ROW_NUMBER() OVER (
                                           PARTITION BY ns.character_id
                                           ORDER BY ns.snapshot_time DESC
                                       ) as rn
                                FROM networth_snapshots ns
                                WHERE ns.character_id IN ({",".join("?" for _ in chars_with_missing_snaps)})
                                  AND ns.snapshot_time <= ?
                            ) t
                            WHERE rn = 1
                            """,
                            tuple(chars_with_missing_snaps + [group_time.isoformat()]),
                        )
                        for snap_row in fallback_snaps:
                            fallback_snap = NetWorthSnapshot(**dict(snap_row))
                            char_snaps.append(fallback_snap)
                            char_snaps_by_id[fallback_snap.character_id] = fallback_snap
                    except Exception:
                        logger.debug(
                            "Failed to get fallback snapshots for group %d",
                            group_id,
                            exc_info=True,
                        )

                # Aggregate character snapshots
                for snap in char_snaps:
                    for field, label in self.CATEGORY_FIELDS:
                        value = float(getattr(snap, field, 0.0) or 0.0)
                        if label == "Assets" and self._active_location_ids:
                            value = filtered_assets.get(
                                int(getattr(snap, "character_id", 0)), value
                            )
                        if not self._category_visibility.get(label, True):
                            value = 0.0
                        bucket_values[label] = bucket_values.get(label, 0.0) + value

                # Aggregate PLEX snapshots - get FROM THIS GROUP ONLY
                try:
                    plex_snaps = await self._networth._repo.fetchall(
                        """
                        SELECT plex_snapshot_id, account_id, snapshot_group_id, snapshot_time,
                               plex_units, plex_unit_price, plex_total_value
                        FROM account_plex_snapshots
                        WHERE snapshot_group_id = ?
                        ORDER BY account_id
                        """,
                        (group_id,),
                    )
                    plex_snaps = [dict(p) for p in plex_snaps]
                except Exception:
                    logger.debug(
                        "Failed to get PLEX snapshots for group %d",
                        group_id,
                        exc_info=True,
                    )
                    plex_snaps = []

                # For accounts missing PLEX snapshots in this group, get their latest up to group_time
                plex_snaps_by_account = {p.get("account_id"): p for p in plex_snaps}
                try:
                    # Get ALL account IDs that have any PLEX snapshots (not just current group)
                    all_plex_accounts = await self._networth._repo.fetchall(
                        """
                        SELECT DISTINCT account_id FROM account_plex_snapshots
                        WHERE account_id IS NOT NULL
                        """
                    )
                    all_plex_account_ids = [
                        int(row[0]) for row in all_plex_accounts if row[0] is not None
                    ]

                    # Find accounts with PLEX in current group
                    plex_group_accounts = set(p.get("account_id") for p in plex_snaps)

                    # Get fallback PLEX snapshots for accounts missing them
                    missing_plex_accounts = [
                        aid
                        for aid in all_plex_account_ids
                        if aid not in plex_group_accounts
                    ]

                    if missing_plex_accounts:
                        fallback_plex_snaps = await self._networth._repo.fetchall(
                            f"""
                            SELECT plex_snapshot_id, account_id, snapshot_group_id, snapshot_time,
                                   plex_units, plex_unit_price, plex_total_value
                            FROM (
                                SELECT aps.*,
                                       ROW_NUMBER() OVER (
                                           PARTITION BY aps.account_id
                                           ORDER BY aps.snapshot_time DESC
                                       ) as rn
                                FROM account_plex_snapshots aps
                                WHERE aps.account_id IN ({",".join("?" for _ in missing_plex_accounts)})
                                  AND aps.snapshot_time <= ?
                            ) t
                            WHERE rn = 1
                            """,
                            tuple(missing_plex_accounts + [group_time.isoformat()]),
                        )
                        for plex_row in fallback_plex_snaps:
                            plex_snap = dict(plex_row)
                            plex_snaps.append(plex_snap)
                except Exception:
                    logger.debug(
                        "Failed to get fallback PLEX snapshots for group %d",
                        group_id,
                        exc_info=True,
                    )

                plex_total = 0.0
                plex_count = 0
                for plex_snap in plex_snaps:
                    value = float(plex_snap.get("plex_total_value", 0.0) or 0.0)
                    plex_total += value
                    plex_count += 1
                    logger.debug(
                        "PLEX snap: account=%s, value=%.2f",
                        plex_snap.get("account_id"),
                        value,
                    )
                bucket_values["PLEX"] = plex_total
                if plex_total > 0:
                    logger.debug(
                        "Group %d PLEX total: %.2f (from %d snaps)",
                        group_id,
                        plex_total,
                        plex_count,
                    )

                # Calculate total value for this group to validate data
                group_total = sum(bucket_values.values())

                # Skip groups with zero or invalid total to prevent graph zero-drops
                # This handles deleted snapshots and incomplete data gracefully
                if group_total <= 0:
                    logger.debug(
                        "Skipping group %d with zero/invalid total (deleted or incomplete data)",
                        group_id,
                    )
                    continue

                # Only add valid groups to the plot data
                ordered_group_ids.append(group_id)
                group_timestamps.append(group_time.timestamp())
                group_data[group_id] = bucket_values
                group_metadata[group_id] = {
                    "group_id": group_id,
                    "account_id": group.get("account_id"),
                    "refresh_source": group.get("refresh_source"),
                    "label": group.get("label"),
                    "timestamp": group_time,
                    "char_count": len(char_snaps),
                    "plex_count": plex_count,
                    "plex_total": plex_total,
                }

            if not group_timestamps:
                self._last_plot_cache = {}
                return

            # Plot each category with different line styles
            self._last_plot_cache = {
                "timestamps": group_timestamps,
                "series": {},
                "group_metadata": group_metadata,
            }
            plotted_labels: list[str] = []

            # Plot asset-based categories
            for field, label in self.CATEGORY_FIELDS:
                if not self._category_visibility.get(label, True):
                    continue

                values = [group_data[gid][label] for gid in ordered_group_ids]
                if any(v > 0 for v in values):
                    color = self.COLOR_MAP.get(label, "#000000")
                    line_style = self.LINE_STYLE_MAP.get(label, "solid")
                    symbol = self.SYMBOL_MAP.get(label, "o")

                    style_map = {
                        "solid": Qt.PenStyle.SolidLine,
                        "dash": Qt.PenStyle.DashLine,
                        "dot": Qt.PenStyle.DotLine,
                        "dashdot": Qt.PenStyle.DashDotLine,
                    }
                    pen_style = style_map.get(line_style, Qt.PenStyle.SolidLine)

                    pen = pg.mkPen(color=color, width=1.5, style=pen_style)
                    self._plot_widget.plot(
                        group_timestamps,
                        values,
                        pen=pen,
                        name=label,
                        symbol=symbol,
                        symbolSize=6,
                        symbolBrush=color,
                        symbolPen=pg.mkPen(color=color, width=1),
                        antialias=True,
                    )
                    self._last_plot_cache["series"][label] = values
                    plotted_labels.append(label)

            # Plot PLEX as separate series (if visible)
            if self._category_visibility.get("PLEX", True):
                plex_values = [
                    group_data[gid].get("PLEX", 0.0) for gid in ordered_group_ids
                ]
                logger.debug("PLEX values for plot: %s", plex_values)
                logger.debug("Any PLEX > 0? %s", any(v > 0 for v in plex_values))
            else:
                plex_values = []
                logger.debug("PLEX visibility disabled, skipping")

            if plex_values and any(v > 0 for v in plex_values):
                plex_color = self.COLOR_MAP.get("PLEX", "#e377c2")
                plex_symbol = self.SYMBOL_MAP.get("PLEX", "star")
                plex_line_style = self.LINE_STYLE_MAP.get("PLEX", "dot")

                style_map = {
                    "solid": Qt.PenStyle.SolidLine,
                    "dash": Qt.PenStyle.DashLine,
                    "dot": Qt.PenStyle.DotLine,
                    "dashdot": Qt.PenStyle.DashDotLine,
                }
                pen_style = style_map.get(plex_line_style, Qt.PenStyle.DotLine)

                pen = pg.mkPen(color=plex_color, width=1.5, style=pen_style)
                self._plot_widget.plot(
                    group_timestamps,
                    plex_values,
                    pen=pen,
                    name="PLEX",
                    symbol=plex_symbol,
                    symbolSize=6,
                    symbolBrush=plex_color,
                    symbolPen=pg.mkPen(color=plex_color, width=1),
                    antialias=True,
                )
                logger.info("Plotted PLEX series with %d points", len(plex_values))
                self._last_plot_cache["series"]["PLEX"] = plex_values
                plotted_labels.append("PLEX")
            else:
                logger.debug("No PLEX values to plot")

            # Plot Total
            if plotted_labels:
                total_values = [
                    sum(group_data[gid].get(lbl, 0.0) for lbl in plotted_labels)
                    for gid in ordered_group_ids
                ]
                pen = pg.mkPen(color="#000000", width=2.5, style=Qt.PenStyle.SolidLine)
                self._plot_widget.plot(
                    group_timestamps,
                    total_values,
                    pen=pen,
                    name="Total",
                    symbol="s",
                    symbolSize=7,
                    symbolBrush="#000000",
                    antialias=True,
                )
                self._last_plot_cache["series"]["Total"] = total_values

            logger.info(
                "Networth graph completed: %d groups, %d series",
                len(ordered_group_ids),
                len(plotted_labels),
            )

            self._update_delta_label()

            # Re-add hover line
            if hasattr(self, "_hover_line"):
                try:
                    self._plot_widget.addItem(self._hover_line)
                except Exception:
                    self._hover_line = pg.InfiniteLine(
                        angle=90,
                        movable=False,
                        pen=pg.mkPen(
                            color="#FFD700", width=1.5, style=Qt.PenStyle.DashLine
                        ),
                    )
                    self._plot_widget.addItem(self._hover_line)
                    self._hover_line.hide()

        except Exception:
            logger.exception("Failed to plot net worth data from groups")

    def _find_nearest_snapshot(self, ts_float: float) -> Any | None:
        """Find the nearest snapshot to the provided timestamp.

        Prefers the currently selected character when available; otherwise falls
        back to the globally nearest snapshot.
        """

        def nearest(snaps: list[Any]) -> Any | None:
            if not snaps:
                return None
            return min(
                snaps,
                key=lambda s: abs(
                    getattr(s, "snapshot_time", datetime.min).timestamp() - ts_float
                ),
            )

        if self._selected_character_id is not None:
            snaps = self._snapshots_by_character.get(
                int(self._selected_character_id), []
            )
            candidate = nearest(snaps)
            if candidate is not None:
                return candidate

        return nearest(self._all_snapshots)

    def _on_plot_clicked(self, mouse_event) -> None:
        """Handle plot clicks: right-click for context menu, double-click to edit."""

        try:
            if not self._last_plot_cache:
                return

            scene_pos = getattr(mouse_event, "scenePos", lambda: None)()
            if scene_pos is None:
                return
            plot_item = getattr(self._plot_widget, "plotItem", None)
            view_box = getattr(plot_item, "vb", None)
            if view_box is None:
                return
            view_pt = view_box.mapSceneToView(scene_pos)
            if view_pt is None:
                return

            snapshot = self._find_nearest_snapshot(view_pt.x())
            if snapshot is None:
                return

            # Handle double-click: open edit dialog directly
            if mouse_event.double():
                self._launch_edit_dialog(snapshot)
                return

            # Handle right-click: show context menu
            if mouse_event.button() != Qt.MouseButton.RightButton:
                return

            menu = QMenu(self)
            edit_action = menu.addAction("Edit Snapshot…")
            delete_action = menu.addAction("Delete Snapshot")
            chosen = menu.exec(mouse_event.screenPos().toPoint())
            if chosen is None:
                return
            if chosen == edit_action:
                self._launch_edit_dialog(snapshot)
            elif chosen == delete_action:
                self._delete_snapshot(snapshot)
        except Exception:
            logger.debug("Plot click handling failed", exc_info=True)

    def _launch_edit_dialog(self, snapshot: Any) -> None:
        """Launch the edit dialog for a snapshot.

        Fetches authenticated characters asynchronously to populate the
        character selector in the dialog.
        """
        try:

            async def _show_dialog():
                try:
                    from ui.dialogs.edit_snapshot_dialog import EditSnapshotDialog

                    # Fetch authenticated characters for the dropdown
                    try:
                        characters = (
                            await self._characters.get_authenticated_characters()
                        )
                    except Exception:
                        logger.debug(
                            "Failed to fetch characters for edit dialog", exc_info=True
                        )
                        characters = []

                    # Build a map of character_id -> latest snapshot for each character
                    # at the same snapshot time (for edit dialog to switch between)
                    snapshots_by_char: dict[int, Any] = {}
                    target_time = getattr(snapshot, "snapshot_time", None)
                    if target_time:
                        for char_id, snaps in self._snapshots_by_character.items():
                            # Find snapshot closest to target_time for this character
                            closest = None
                            min_diff = float("inf")
                            for s in snaps:
                                snap_time = getattr(s, "snapshot_time", None)
                                if snap_time:
                                    diff = abs(
                                        (snap_time - target_time).total_seconds()
                                    )
                                    if diff < min_diff:
                                        min_diff = diff
                                        closest = s
                            if closest is not None:
                                snapshots_by_char[char_id] = closest

                    # Find group metadata for this snapshot
                    group_metadata = {}
                    if (
                        hasattr(snapshot, "snapshot_group_id")
                        and snapshot.snapshot_group_id
                    ):
                        group_meta_dict = self._last_plot_cache.get(
                            "group_metadata", {}
                        )
                        group_metadata = group_meta_dict.get(
                            snapshot.snapshot_group_id, {}
                        )

                    # Fetch accounts and PLEX snapshots for this group
                    accounts = {}
                    plex_snapshots_by_account = {}
                    try:
                        from utils.settings_manager import get_settings_manager

                        settings = get_settings_manager()
                        all_accounts = settings.get_accounts()
                        for account_id, account_data in all_accounts.items():
                            accounts[account_id] = account_data

                        # Load PLEX snapshots for this group
                        if (
                            hasattr(snapshot, "snapshot_group_id")
                            and snapshot.snapshot_group_id
                        ):
                            plex_snaps = await self._networth._repo.fetchall(
                                """
                                    SELECT plex_snapshot_id, account_id, snapshot_group_id, snapshot_time,
                                           plex_units, plex_unit_price, plex_total_value
                                    FROM account_plex_snapshots
                                    WHERE snapshot_group_id = ?
                                    ORDER BY account_id
                                    """,
                                (snapshot.snapshot_group_id,),
                            )
                            for plex_snap in plex_snaps:
                                plex_dict = dict(plex_snap)
                                plex_snapshots_by_account[plex_dict["account_id"]] = (
                                    plex_dict
                                )
                    except Exception:
                        logger.debug(
                            "Failed to load accounts/PLEX for edit dialog",
                            exc_info=True,
                        )

                    dlg = EditSnapshotDialog(
                        snapshot,
                        parent=self,
                        characters=characters,
                        snapshots_by_character=snapshots_by_char,
                        group_metadata=group_metadata,
                        networth_service=self._networth,
                        accounts=accounts,
                        plex_snapshots_by_account=plex_snapshots_by_account,
                    )
                    if dlg.exec():
                        updated = dlg.get_updated_snapshot()
                        try:
                            await self._networth.update_snapshot(updated)

                            # Save edited PLEX snapshots if any
                            edited_plex = dlg.get_edited_plex_snapshots()
                            for account_id, plex_data in edited_plex.items():
                                try:
                                    plex_id = plex_data.get("plex_snapshot_id")
                                    if plex_id:
                                        # Update existing PLEX snapshot
                                        await self._networth._repo.execute(
                                            """
                                            UPDATE account_plex_snapshots
                                            SET plex_units = ?, plex_unit_price = ?, plex_total_value = ?
                                            WHERE plex_snapshot_id = ?
                                            """,
                                            (
                                                plex_data["units"],
                                                plex_data["price"],
                                                plex_data["units"] * plex_data["price"],
                                                plex_id,
                                            ),
                                        )
                                        await self._networth._repo.commit()
                                        logger.info(
                                            "Updated PLEX snapshot %d for account %d",
                                            plex_id,
                                            account_id,
                                        )
                                except Exception:
                                    logger.exception(
                                        "Failed to update PLEX snapshot for account %d",
                                        account_id,
                                    )

                            await self._plot()
                            self._signal_bus.info_message.emit("Snapshot updated")
                        except Exception:
                            logger.exception("Failed to update snapshot")
                            self._signal_bus.error_occurred.emit(
                                "Failed to update snapshot; see logs."
                            )
                except Exception:
                    logger.debug("Failed to show edit dialog", exc_info=True)

            asyncio.create_task(_show_dialog())
        except Exception:
            logger.debug("Failed to launch edit dialog", exc_info=True)

    def _delete_snapshot(self, snapshot: Any) -> None:
        try:
            snapshot_id = getattr(snapshot, "snapshot_id", None)
            if snapshot_id is None:
                return

            async def _apply():
                try:
                    await self._networth.delete_snapshot(int(snapshot_id))
                    await self._plot()
                    self._signal_bus.info_message.emit("Snapshot deleted")
                except Exception:
                    logger.exception("Failed to delete snapshot")
                    self._signal_bus.error_occurred.emit(
                        "Failed to delete snapshot; see logs."
                    )

            # Track the task to ensure it completes
            task = asyncio.create_task(_apply())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception:
            logger.debug("Failed to delete snapshot", exc_info=True)

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle centrally-loaded characters and plot graph.

        Args:
            characters: List of CharacterInfo objects from central loader
        """
        logger.info(
            "Networth tab received %d characters, refreshing graph", len(characters)
        )
        try:
            self._rebuild_character_filters(characters)
        except Exception:
            logger.debug("Failed to rebuild character filters", exc_info=True)
        try:
            # Schedule graph refresh as background task
            task = asyncio.create_task(self._plot_and_set_date_bounds())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            logger.debug("Scheduled networth graph refresh task")
        except Exception as e:
            logger.error("Failed to schedule graph plotting: %s", e)

    async def _plot_and_set_date_bounds(self) -> None:
        """Plot the graph and update date selector bounds based on available data."""
        await self._plot()
        try:
            # Set the date_from selector to the earliest snapshot date
            if self._all_snapshots and not self._date_range_user_set:
                earliest = min(
                    s.snapshot_time
                    for s in self._all_snapshots
                    if hasattr(s, "snapshot_time")
                )
                if earliest:
                    # Update the from date selector minimum and value
                    self._date_from = earliest
                    self._set_date_edit(self.date_from_edit, earliest)
                    # Set minimum date to prevent selecting earlier than earliest entry
                    self.date_from_edit.setMinimumDate(
                        QDate(earliest.year, earliest.month, earliest.day)
                    )
            # Update the "to" date to the latest snapshot if user hasn't overridden
            if self._all_snapshots and not self._date_range_user_set:
                latest = max(
                    s.snapshot_time
                    for s in self._all_snapshots
                    if hasattr(s, "snapshot_time")
                )
                if latest:
                    self._date_to = latest
                    self._set_date_edit(self.date_to_edit, latest)
        except Exception:
            logger.debug("Failed to set date bounds", exc_info=True)

    def _on_plot_hover(self, evt):
        try:
            if not self._last_plot_cache:
                # Hide hover indicator when no data
                if hasattr(self, "_hover_line"):
                    self._hover_line.hide()
                self._hover_label.setText("Hover over graph for details")
                return
            pos = evt[0] if isinstance(evt, (list, tuple)) else evt
            if pos is None:
                return
            plot_item = getattr(self._plot_widget, "plotItem", None)
            view_box = getattr(plot_item, "vb", None)
            if view_box is None:
                return
            point = view_box.mapSceneToView(pos)
            if point is None:
                return
            x_val = point.x()
            timestamps = self._last_plot_cache.get("timestamps", [])
            if not timestamps:
                return
            # Find nearest timestamp index
            idx = min(range(len(timestamps)), key=lambda i: abs(timestamps[i] - x_val))
            ts = datetime.fromtimestamp(timestamps[idx], tz=UTC)

            # Show vertical crosshair line at nearest data point for visual feedback
            if not hasattr(self, "_hover_line"):
                self._hover_line = pg.InfiniteLine(
                    angle=90,
                    movable=False,
                    pen=pg.mkPen(
                        color="#FFD700", width=1.5, style=Qt.PenStyle.DashLine
                    ),
                )
                self._plot_widget.addItem(self._hover_line)
            self._hover_line.setPos(timestamps[idx])
            self._hover_line.show()

            # Build compact horizontal tooltip with color-coded values
            date_str = ts.strftime("%b %d, %H:%M")
            value_parts = []
            for label, values in self._last_plot_cache.get("series", {}).items():
                if idx < len(values):
                    color = self.COLOR_MAP.get(label, "#FFFFFF")
                    symbol = GraphStyles.format_series_indicator(label)
                    value_str = format_isk_short(values[idx])
                    value_parts.append(
                        f"{symbol} <span style='color:{color}'><b>{label}:</b> {value_str}</span>"
                    )
            # Join with separator for horizontal layout
            self._hover_label.setText(
                f"<b>{date_str}</b> &nbsp;— "
                + " &nbsp;| ".join(value_parts[:4])
                + (" ..." if len(value_parts) > 4 else "")
            )
        except Exception:
            logger.debug("Hover tooltip failed", exc_info=True)

    def _update_delta_label(self) -> None:
        """Show per-series delta (first → last) with colored symbol indicators."""
        series = self._last_plot_cache.get("series", {})
        timestamps = self._last_plot_cache.get("timestamps", [])

        if not series or not timestamps:
            self._delta_label.setText(
                f"<span style='color:{COLORS.TEXT_MUTED}'>No data for selected period</span>"
            )
            return

        # Build date range header
        try:
            start_date = datetime.fromtimestamp(timestamps[0], tz=UTC).strftime("%b %d")
            end_date = datetime.fromtimestamp(timestamps[-1], tz=UTC).strftime(
                "%b %d, %Y"
            )
            date_range = f"<b>Period:</b> {start_date} → {end_date}"
        except (ValueError, IndexError):
            date_range = ""

        parts: list[str] = []
        for label, values in series.items():
            if not values or len(values) < 2:
                continue
            start = values[0]
            end = values[-1]
            delta = end - start
            pct = (delta / start * 100) if start else None
            delta_txt = format_isk_short(delta, signed=True)

            # Color delta value based on positive/negative
            delta_color = COLORS.SUCCESS if delta >= 0 else COLORS.ERROR

            # Use GraphStyles colored symbol indicator (non-italic, standard font)
            symbol_html = GraphStyles.format_series_indicator(label)
            if pct is None:
                parts.append(
                    f"{symbol_html} <b>{label}:</b> "
                    f"<span style='color:{delta_color}'>{delta_txt}</span>"
                )
            else:
                parts.append(
                    f"{symbol_html} <b>{label}:</b> "
                    f"<span style='color:{delta_color}'>{delta_txt} ({pct:+.1f}%)</span>"
                )

        # Combine date range and deltas in a horizontal-friendly format
        if date_range and parts:
            self._delta_label.setText(
                f"{date_range} &nbsp;|&nbsp; " + " &nbsp;|&nbsp; ".join(parts)
            )
        elif parts:
            self._delta_label.setText(" &nbsp;|&nbsp; ".join(parts))
        else:
            self._delta_label.setText(
                f"<span style='color:{COLORS.TEXT_MUTED}'>Insufficient data for delta calculation</span>"
            )

    @staticmethod
    def _configure_date_edit(edit: QDateEdit) -> None:
        """Configure a QDateEdit widget with proper calendar popup behavior.

        Fixes issues with calendar popup clicking behavior and year/month changes.
        """
        # Ensure proper correction mode
        edit.setCorrectionMode(QDateEdit.CorrectionMode.CorrectToNearestValue)

        # Apply date edit styling
        edit.setStyleSheet(AppStyles.DATE_EDIT)

        # Get the calendar widget and configure it
        calendar = edit.calendarWidget()
        if calendar is not None:
            # Set grid visibility for clearer date selection
            calendar.setGridVisible(True)

            # Set vertical header format (don't show week numbers which can cause click issues)
            try:
                from PyQt6.QtWidgets import QCalendarWidget

                calendar.setVerticalHeaderFormat(
                    QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
                )
            except Exception:
                pass

            # Apply unified dark theme styling to calendar popup with enhanced year spinbox arrows
            calendar.setStyleSheet(AppStyles.CALENDAR_ENHANCED)

    @staticmethod
    def _set_date_edit(edit: QDateEdit, value: datetime | None) -> None:
        if value is None:
            return
        edit.blockSignals(True)
        edit.setDate(QDate(value.year, value.month, value.day))
        edit.blockSignals(False)

    @staticmethod
    def _qdate_to_datetime(qdate: QDate, *, start_of_day: bool) -> datetime:
        time_part = datetime.min.time() if start_of_day else datetime.max.time()
        return datetime.combine(qdate.toPyDate(), time_part, tzinfo=UTC)
