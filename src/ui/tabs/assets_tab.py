"""Assets tab displaying all characters' assets with advanced filtering and list."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QLabel, QMenu, QVBoxLayout, QWidget

from data import FuzzworkProvider
from data.clients import ESIClient
from services.asset_service import AssetService
from services.character_service import CharacterService
from services.location_service import LocationService
from ui.dialogs.custom_location_dialog import CustomLocationDialog
from ui.dialogs.custom_overrides_dialog import CustomOverridesDialog
from ui.dialogs.custom_price_dialog import CustomPriceDialog
from ui.signal_bus import get_signal_bus
from ui.styles import COLORS
from ui.widgets.advanced_table_widget import AdvancedTableView
from ui.widgets.filter_widget import ColumnSpec, FilterWidget
from utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)

# Optional clipboard support
try:  # pragma: no cover - optional runtime dependency
    import pyperclip  # type: ignore
except Exception:  # pragma: no cover
    pyperclip = None  # type: ignore


class AssetsTab(QWidget):
    def __init__(
        self,
        character_service: CharacterService,
        esi_client: ESIClient,
        asset_service: AssetService,
        location_service: LocationService,
        fuzzwork_provider: FuzzworkProvider | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._character_service = character_service
        self._esi = esi_client
        self._assets = asset_service
        self._location_service = location_service
        self._fuzzwork = fuzzwork_provider
        self._settings = get_settings_manager()
        self._background_tasks: set[asyncio.Task] = set()

        self._columns: list[tuple[str, str]] = [
            ("group_name", "Group"),
            ("category_name", "Category"),
            ("owner_character_name", "Owner"),
            ("system_name", "System"),
            ("location_display", "Location"),
            ("type_name", "Name"),
            ("market_value", "Value (Unit)"),
            ("total_value", "Value (Total)"),
            ("quantity", "Count"),
            ("base_price", "Price (Base)"),
            ("volume", "Volume (Unit)"),
            ("total_volume", "Volume (Total)"),
        ]

        # Filter column specs (type-aware)
        self._filter_specs: list[ColumnSpec] = [
            ColumnSpec("group_name", "Group", "text"),
            ColumnSpec("category_name", "Category", "text"),
            ColumnSpec("owner_character_name", "Owner", "text"),
            ColumnSpec("system_name", "System", "text"),
            ColumnSpec("location_display", "Location", "text"),
            ColumnSpec("type_name", "Name", "text"),
            ColumnSpec("market_value", "Value (Unit)", "float"),
            ColumnSpec("total_value", "Value (Total)", "float"),
            ColumnSpec("quantity", "Count", "int"),
            ColumnSpec("base_price", "Price (Base)", "float"),
            ColumnSpec("volume", "Volume (Unit)", "float"),
            ColumnSpec("total_volume", "Volume (Total)", "float"),
        ]

        self._setup_ui()
        self._connect_signals()
        self._rows_cache: list[dict[str, Any]] = []  # Cache for real-time updates

    @staticmethod
    def _compute_location_display_from_row(row: dict[str, Any]) -> str:
        """Derive the display string for a location without altering user-supplied names."""
        for key in ("structure_name", "station_name", "planet_name"):
            val = row.get(key)
            if val:
                return str(val)

        # Fall back to system name if present. Do **not** reuse an existing
        # location_display value because older cached rows may still contain
        # a suffix such as "(System)" that we no longer want to append.
        if row.get("system_name"):
            return str(row.get("system_name"))

        return ""

    def _get_custom_location_data(self, location_id: int) -> dict[str, Any] | None:
        """Fetch custom overrides for a location from the location cache."""

        if not self._location_service:
            return None

        try:
            return self._location_service.get_custom_location_data(int(location_id))
        except Exception:
            logger.exception("Failed to fetch custom location data for %s", location_id)
            return None

    def _setup_ui(self) -> None:
        main = QVBoxLayout(self)
        main.setContentsMargins(8, 8, 8, 8)
        main.setSpacing(6)

        # Add last updated indicator at top
        self.last_updated_label = QLabel("Last Updated: Never")
        self.last_updated_label.setStyleSheet(
            f"color: {COLORS.TEXT_MUTED}; font-size: 10pt; font-style: italic;"
        )
        main.addWidget(self.last_updated_label)

        # Create the table **before** the filter widget so that any filter
        # signals emitted during FilterWidget construction (it emits immediately
        # after adding the initial group and loading persisted state) have a
        # target to attach to. This prevents AttributeError on self.table when
        # the filter_changed signal fires early.
        self.table = AdvancedTableView()
        self.table.setup(self._columns)
        self.table.set_context_menu_builder(self._build_context_menu)

        # Initialize filter spec storage (will be populated by _on_filter_changed)
        self._current_filter_spec: dict | None = None

        self.filter_widget = FilterWidget(self._filter_specs, settings_key="assets")
        self.filter_widget.filter_changed.connect(self._on_filter_changed)
        # FilterWidget loads the persisted filter inside its constructor, before
        # we attach our slot. Re-apply the current spec so the predicate is
        # active on startup (ensures default filter is applied to initial data).
        try:
            self._on_filter_changed(self.filter_widget.get_spec())
        except Exception:
            logger.debug("Failed to apply initial assets filter", exc_info=True)
        # Layout order: filter widget, then table
        main.addWidget(self.filter_widget)
        main.addWidget(self.table)

        # Set up keyboard shortcuts
        copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self.table)
        copy_shortcut.activated.connect(self._copy_selection)

        # Restore column visibility from settings
        self._restoring_state = False
        self._restore_column_state()

        # Save state when columns are manually resized or repositioned (debounced)
        header = self.table.horizontalHeader()
        if header:
            header.sectionResized.connect(self._on_section_resized)
            header.sectionMoved.connect(self._on_section_moved)
            # Enable column move preview
            header.setHighlightSections(True)
        # Debounce timer for column state persistence
        self._column_state_timer = QTimer(self)
        self._column_state_timer.setSingleShot(True)
        self._column_state_timer.setInterval(300)
        self._column_state_timer.timeout.connect(self._save_column_state)

    def _on_section_resized(
        self, logical_index: int, old_size: int, new_size: int
    ) -> None:
        """Handle column resize - do not save during programmatic restore."""
        if getattr(self, "_restoring_state", False):
            return
        try:
            self._column_state_timer.start()
        except Exception:
            self._save_column_state()

    def _on_section_moved(self) -> None:
        """Handle column move - debounce persistence."""
        if getattr(self, "_restoring_state", False):
            return
        try:
            self._column_state_timer.start()
        except Exception:
            self._save_column_state()

    def _connect_signals(self) -> None:
        """Connect signal bus signals for realtime updates."""
        self._signal_bus.custom_price_changed.connect(self._on_custom_price_changed)

        # Use wrapper with DIRECT connection to bypass Qt's signal queue corruption
        def location_changed_wrapper(loc_id):
            logger.debug("Signal wrapper received location_id=%s", loc_id)
            self._on_custom_location_changed(loc_id)

        # Force direct (blocking) connection to avoid signal queue corruption
        self._signal_bus.custom_location_changed.connect(location_changed_wrapper)
        self._signal_bus.character_added.connect(self._on_character_added)
        self._signal_bus.character_removed.connect(self._on_character_removed)
        # Listen for centralized character loading
        self._signal_bus.characters_loaded.connect(self._on_characters_loaded)
        logger.debug("Connected assets tab signals (id=%s)", id(self))

    def _on_filter_changed(self, spec: dict) -> None:
        if not getattr(self, "table", None):
            logger.debug("AssetsTab: table not ready, skipping predicate update")
            return
        # Store the current filter spec for combined filtering
        self._current_filter_spec = spec
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Apply advanced filter predicate."""
        if not getattr(self, "table", None):
            return

        # Build advanced filter predicate
        spec = getattr(self, "_current_filter_spec", None)
        advanced_pred = FilterWidget.build_predicate(spec) if spec else None

        def predicate(row: dict) -> bool:
            # Apply advanced filter
            if advanced_pred:
                return advanced_pred(row)
            return True

        try:
            self.table.set_predicate(predicate)
        except Exception:
            logger.exception("Failed to apply assets filter predicate")

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle centrally-loaded characters and load their assets.

        Args:
            characters: List of CharacterInfo objects from central loader
        """
        logger.info(
            "Assets tab received %d characters, loading cached assets", len(characters)
        )

        try:
            # Use ensure_future for safer task creation
            task = asyncio.ensure_future(self._load_assets_for_characters(characters))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception as e:
            logger.error("Failed to schedule asset loading: %s", e)
            self._signal_bus.error_occurred.emit("Failed to load assets")

    def _on_character_removed(self, character_id: int) -> None:
        """Remove asset rows for a deleted character to avoid stale data."""
        try:
            before = len(self._rows_cache)
            self._rows_cache = [
                row
                for row in self._rows_cache
                if int(row.get("owner_character_id", -1)) != int(character_id)
            ]
            if len(self._rows_cache) != before:
                self.table.set_rows(self._rows_cache)
                self._signal_bus.status_message.emit(
                    f"Removed assets for character {character_id}"
                )
        except Exception:
            logger.debug(
                "Failed to prune rows for removed character %s",
                character_id,
                exc_info=True,
            )

    async def _load_assets_for_characters(self, characters: list) -> None:
        """Load assets for characters (cache-only for fast startup).

        Args:
            characters: List of CharacterInfo objects
        """
        try:
            rows: list[dict[str, Any]] = []
            character_assets = []

            for char in characters:
                # Load from repository with location resolution
                # resolve_locations=True allows NPC stations to be resolved from SDE
                # refresh_locations=False prevents ESI calls for stale player structures
                enriched = await self._assets.get_all_enriched_assets(
                    char.character_id,
                    getattr(char, "character_name", str(char.character_id)),
                    resolve_locations=True,  # Resolve locations (SDE for NPC, cache for structures)
                    refresh_locations=False,  # Don't make ESI calls on startup
                )
                character_assets.append((char, enriched))

            # Now build rows with enriched assets (locations already resolved)
            for _char, enriched in character_assets:
                for ea in enriched:
                    # Apply fuzzwork and custom prices
                    if ea.market_value is None and self._fuzzwork:
                        fuzz_price = self._get_fuzzwork_price(ea.type_id)
                        if fuzz_price:
                            ea.market_value = fuzz_price

                    custom_price = self._settings.get_custom_price(ea.type_id)
                    if custom_price and custom_price.get("sell") is not None:
                        ea.market_value = custom_price["sell"]

                    # Apply custom location overrides (name/system) for cached startup
                    if ea.structure_id:
                        custom = self._get_custom_location_data(ea.structure_id)
                        if custom:
                            if custom.get("name"):
                                ea.structure_name = str(custom.get("name"))
                            sys_id = custom.get("system_id")
                            if sys_id is not None:
                                try:
                                    ea.system_id = int(sys_id)
                                    sde = getattr(
                                        self._assets, "_sde", None
                                    ) or getattr(self._assets, "_sde_provider", None)
                                    if sde:
                                        name = sde.get_solar_system_name(ea.system_id)
                                        if name:
                                            ea.system_name = name
                                except Exception:
                                    pass
                    elif ea.station_id:
                        custom = self._get_custom_location_data(ea.station_id)
                        if custom:
                            if custom.get("name"):
                                ea.station_name = str(custom.get("name"))
                            sys_id = custom.get("system_id")
                            if sys_id is not None:
                                try:
                                    ea.system_id = int(sys_id)
                                    sde = getattr(
                                        self._assets, "_sde", None
                                    ) or getattr(self._assets, "_sde_provider", None)
                                    if sde:
                                        name = sde.get_solar_system_name(ea.system_id)
                                        if name:
                                            ea.system_name = name
                                except Exception:
                                    pass

                    # Build row dict
                    row = ea.model_dump()
                    # Preserve original names/system for reliable revert when custom overrides are removed
                    try:
                        if ea.structure_id:
                            row["orig_structure_name"] = row.get("structure_name")
                        if ea.station_id:
                            row["orig_station_name"] = row.get("station_name")
                        row["orig_system_name"] = row.get("system_name")
                    except Exception:
                        pass
                    # Compute location_display using the resolved names (no suffix rewriting)
                    try:
                        row["location_display"] = (
                            self._compute_location_display_from_row(row)
                        )
                    except Exception:
                        pass
                    rows.append(row)

            self._rows_cache = rows
            self.table.set_rows(rows)

            self.last_updated_label.setText(
                f"Last Updated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} (cached data)"
            )
            logger.info("Loaded %d asset rows from cache", len(rows))

        except Exception:
            logger.exception("Failed to load assets for characters")
            self._signal_bus.error_occurred.emit("Failed to load assets")

    async def _load_assets_async(self) -> None:
        try:
            rows: list[dict[str, Any]] = []
            characters = await self._character_service.get_authenticated_characters()
            for char in characters:
                enriched = await self._assets.get_all_enriched_assets(
                    char.character_id,
                    getattr(char, "character_name", str(char.character_id)),
                    refresh_locations=False,  # Don't refresh locations on startup
                )

                # Request a sync from ESI to update repository, then read
                try:
                    await self._assets.sync_assets(
                        char.character_id, use_cache=True, bypass_cache=False
                    )
                except Exception:
                    logger.exception(
                        "Failed syncing assets for character %s",
                        char.character_id,
                    )
                    # Even if sync fails, show latest repository data
                enriched = await self._assets.get_all_enriched_assets(
                    char.character_id,
                    getattr(char, "character_name", str(char.character_id)),
                    refresh_locations=True,  # Refresh locations on explicit update
                )
                for enriched_asset in enriched:
                    # Apply fuzzwork price if no market_value set
                    if enriched_asset.market_value is None and self._fuzzwork:
                        fuzz_price = self._get_fuzzwork_price(enriched_asset.type_id)
                        if fuzz_price:
                            enriched_asset.market_value = fuzz_price

                    # Apply custom price from settings (overrides fuzzwork)
                    custom_price = self._settings.get_custom_price(
                        enriched_asset.type_id
                    )
                    if custom_price and custom_price.get("sell") is not None:
                        enriched_asset.market_value = custom_price["sell"]

                    # Apply custom location data (name and optional system override)
                    if enriched_asset.structure_id:
                        custom = self._get_custom_location_data(
                            enriched_asset.structure_id
                        )
                        if custom:
                            if custom.get("name"):
                                enriched_asset.structure_name = str(custom.get("name"))
                            sys_id = custom.get("system_id")
                            if sys_id is not None:
                                try:
                                    enriched_asset.system_id = int(sys_id)
                                    # Resolve system name via SDE for display
                                    sde = getattr(
                                        self._assets, "_sde", None
                                    ) or getattr(self._assets, "_sde_provider", None)
                                    if sde:
                                        name = sde.get_solar_system_name(
                                            enriched_asset.system_id
                                        )
                                        if name:
                                            enriched_asset.system_name = name
                                except Exception:
                                    pass
                    elif enriched_asset.station_id:
                        custom = self._get_custom_location_data(
                            enriched_asset.station_id
                        )
                        if custom:
                            if custom.get("name"):
                                enriched_asset.station_name = str(custom.get("name"))
                            sys_id = custom.get("system_id")
                            if sys_id is not None:
                                try:
                                    enriched_asset.system_id = int(sys_id)
                                    sde = getattr(
                                        self._assets, "_sde", None
                                    ) or getattr(self._assets, "_sde_provider", None)
                                    if sde:
                                        name = sde.get_solar_system_name(
                                            enriched_asset.system_id
                                        )
                                        if name:
                                            enriched_asset.system_name = name
                                except Exception:
                                    pass

                    row = enriched_asset.model_dump()
                    # Preserve original names/system for reliable revert when custom overrides are removed
                    try:
                        if enriched_asset.structure_id:
                            row["orig_structure_name"] = row.get("structure_name")
                        if enriched_asset.station_id:
                            row["orig_station_name"] = row.get("station_name")
                        row["orig_system_name"] = row.get("system_name")
                    except Exception:
                        pass
                    try:
                        row["location_display"] = (
                            self._compute_location_display_from_row(row)
                        )
                    except Exception:
                        pass
                    rows.append(row)
            self._rows_cache = rows
            self.table.set_rows(rows)
            self._signal_bus.status_message.emit(
                f"Loaded {len(rows)} assets across {len(characters)} characters"
            )
        except Exception:
            logger.exception("Failed to load assets")
            self._signal_bus.error_occurred.emit("Failed to load assets")

    def _build_context_menu(self, selected: list[dict[str, Any]]) -> QMenu:
        menu = QMenu(self)
        # Copy
        copy_menu = menu.addMenu("Copy")
        if copy_menu is not None:
            try:
                copy_menu.addAction("Copy Selection", lambda: self._copy_selection())
                copy_menu.addSeparator()
                copy_menu.addAction(
                    "Copy Name(s)", lambda: self._copy_fields(selected, "type_name")
                )
                copy_menu.addAction(
                    "Copy Location(s)",
                    lambda: self._copy_fields(selected, "location_display"),
                )
            except Exception:
                pass

        # Price submenu
        price_menu = menu.addMenu("Price")
        if price_menu is not None:
            try:
                price_menu.addAction(
                    "Set Custom Price...", lambda: self._on_set_price(selected)
                )
            except Exception:
                pass

        # Name submenu (location custom names)
        name_menu = menu.addMenu("Name")
        if name_menu is not None:
            try:
                name_menu.addAction(
                    "Set Custom Location Name...",
                    lambda: self._on_set_location_name(selected),
                )
            except Exception:
                pass

        # Custom overrides management
        menu.addSeparator()
        menu.addAction("Manage All Custom Overrides...", self._show_overrides_dialog)

        # Columns submenu placeholder (show/hide handled via view header context menu by Qt)
        menu.addSeparator()
        info_action = menu.addAction(f"Selection: {len(selected)} items")
        if info_action is not None:
            try:
                info_action.setEnabled(False)
            except Exception:
                pass
        return menu

    def _copy_fields(self, rows: list[dict[str, Any]], key: str) -> None:
        text = "\n".join(str(r.get(key, "")) for r in rows)
        if pyperclip:
            try:
                pyperclip.copy(text)  # type: ignore
                self._signal_bus.status_message.emit("Copied to clipboard")
                return
            except Exception:
                pass
        self._signal_bus.info_message.emit(text)

    def _copy_selection(self) -> None:
        """Copy selected cells to clipboard in Excel-compatible format."""
        try:
            selection_model = self.table.selectionModel()
            if not selection_model or not selection_model.hasSelection():
                return

            indexes = selection_model.selectedIndexes()
            if not indexes:
                return

            # Sort by row then column
            indexes.sort(key=lambda idx: (idx.row(), idx.column()))

            # Build text grid
            rows_data = []
            current_row = -1
            current_row_data = []

            model = self.table.model()
            if model is None:
                return

            for index in indexes:
                if index.row() != current_row:
                    if current_row_data:
                        rows_data.append(current_row_data)
                    current_row = index.row()
                    current_row_data = []

                # Get display data
                try:
                    data = model.data(index, Qt.ItemDataRole.DisplayRole)
                except Exception:
                    data = None
                current_row_data.append(str(data) if data is not None else "")

            if current_row_data:
                rows_data.append(current_row_data)

            # Join with tabs (Excel-compatible)
            text = "\n".join("\t".join(row) for row in rows_data)
            if pyperclip:
                try:
                    pyperclip.copy(text)  # type: ignore
                    self._signal_bus.status_message.emit(
                        f"Copied {len(rows_data)} row(s) to clipboard"
                    )
                    return
                except Exception:
                    pass
            # Fallback to showing text
            self._signal_bus.info_message.emit(text)
        except Exception as e:
            logger.warning("Failed to copy selection: %s", e)

    def _on_set_price(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        r = rows[0]
        type_id = int(r.get("type_id"))
        type_name = str(r.get("type_name"))
        dlg = CustomPriceDialog(type_id, type_name, self)
        dlg.exec()

    def _on_set_location_name(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        r = rows[0]
        # prefer structure or station id/name
        loc_id = int(
            r.get("structure_id") or r.get("station_id") or r.get("location_id")
        )
        curr_name = str(
            r.get("structure_name")
            or r.get("station_name")
            or r.get("location_display")
        )
        # Reuse the existing SDE provider to avoid reloading solar systems repeatedly
        sde = getattr(self._assets, "_sde", None) or getattr(
            self._assets, "_sde_provider", None
        )
        dlg = CustomLocationDialog(
            loc_id,
            curr_name,
            self,
            sde_provider=sde,
            location_service=self._location_service,
        )
        dlg.exec()

    def _on_custom_price_changed(self, type_id: int) -> None:
        """Update displayed prices when custom price changes or is removed."""
        custom = self._settings.get_custom_price(type_id)
        # Update cached rows for all matching type_ids
        for row in self._rows_cache:
            if row.get("type_id") == type_id:
                if custom and custom.get("sell") is not None:
                    # Apply custom unit price
                    row["market_value"] = custom["sell"]
                else:
                    # Custom removed: revert to fuzzwork or base price
                    fallback = self._get_fuzzwork_price(type_id)
                    if fallback is not None:
                        row["market_value"] = fallback
                    else:
                        base = row.get("base_price")
                        row["market_value"] = base if base is not None else None
                # Recompute total value
                qty = int(row.get("quantity") or 0)
                unit = row.get("market_value")
                if unit is None:
                    unit = row.get("base_price") or 0.0
                try:
                    unit_f = float(unit or 0.0)
                except Exception:
                    unit_f = 0.0
                row["total_value"] = unit_f * qty
        # Refresh table
        self.table.set_rows(self._rows_cache)

    def _on_custom_location_changed(self, location_id: int) -> None:
        """Update displayed location info when custom location data changes."""
        logger.debug(
            "Handler received location_id=%s (type=%s)",
            location_id,
            type(location_id).__name__,
        )
        # Fetch both name and optional system override
        custom_data = self._get_custom_location_data(location_id)
        logger.debug(
            "Retrieved custom_data for location %d: %s (type=%s)",
            location_id,
            custom_data,
            type(custom_data).__name__ if custom_data is not None else "None",
        )

        raw_name = custom_data.get("name") if custom_data else None
        custom_name = None
        if raw_name is not None:
            try:
                custom_name = str(raw_name).strip()
                if custom_name == "":
                    custom_name = None
            except Exception:
                custom_name = None
        custom_system_id = custom_data.get("system_id") if custom_data else None

        logger.debug(
            "Custom location changed: location_id=%d, name=%s, system_id=%s",
            location_id,
            custom_name,
            custom_system_id,
        )

        # Update cached rows and recompute display
        rows_updated = 0
        loc_id_int = None
        try:
            loc_id_int = int(location_id)
        except Exception:
            loc_id_int = location_id
        for row in self._rows_cache:
            affected = False

            # Be robust to type mismatches (str vs int) in cached rows
            def _eq_id(v):
                try:
                    return int(v) == loc_id_int
                except Exception:
                    return v == location_id

            is_structure = _eq_id(row.get("structure_id"))
            is_station = _eq_id(row.get("station_id"))
            is_generic = _eq_id(row.get("location_id"))
            if is_structure or is_station or is_generic:
                affected = True
                rows_updated += 1
                if custom_name is not None:
                    # Apply custom name to the source field (structure_name or station_name)
                    # location_display is computed from these, so no need to set it directly
                    if is_structure:
                        row["structure_name"] = custom_name
                    elif is_station:
                        row["station_name"] = custom_name
                else:
                    # Custom name removed: revert to original resolved name first, then fallback to location_service
                    try:
                        reverted = False
                        if is_structure and row.get("orig_structure_name") is not None:
                            row["structure_name"] = row.get("orig_structure_name")
                            reverted = True
                        elif is_station and row.get("orig_station_name") is not None:
                            row["station_name"] = row.get("orig_station_name")
                            reverted = True

                        if not reverted:
                            location_service = getattr(
                                self._assets, "_location_service", None
                            )
                            if location_service:
                                display = location_service.get_display_name(location_id)
                                if display:
                                    # Update the source field, not location_display
                                    if is_structure:
                                        row["structure_name"] = display
                                    elif is_station:
                                        row["station_name"] = display
                    except Exception:
                        pass

            # Apply system override if provided
            if affected and custom_system_id is not None:
                try:
                    sde = getattr(self._assets, "_sde", None) or getattr(
                        self._assets, "_sde_provider", None
                    )
                    if sde:
                        name = sde.get_solar_system_name(int(custom_system_id))
                        if name:
                            row["system_name"] = name
                except Exception:
                    pass
            elif affected and custom_system_id is None:
                # Custom system override removed: revert to original system name if available
                try:
                    orig_sys = row.get("orig_system_name")
                    if orig_sys is not None:
                        row["system_name"] = orig_sys
                        # System restored; continue
                except Exception:
                    pass

            if affected:
                try:
                    row["location_display"] = self._compute_location_display_from_row(
                        row
                    )
                except Exception:
                    pass

        logger.debug("Updated %d rows for location_id=%s", rows_updated, location_id)

        # Log location IDs in cache for debugging
        if rows_updated == 0 and self._rows_cache:
            cache_locs = set()
            for row in self._rows_cache[:5]:  # Sample first 5
                loc = (
                    row.get("structure_id")
                    or row.get("station_id")
                    or row.get("location_id")
                )
                if loc:
                    cache_locs.add(str(loc))
            logger.debug("Sample cached location IDs: %s", cache_locs)

        # Propagate to location service cache FIRST (ensures get_display_name returns updated value)
        try:
            location_service = getattr(self._assets, "_location_service", None)
            if location_service:
                # Always update cache with current custom name (or None)
                location_service.set_custom_location_data(location_id, name=custom_name)
                if custom_name:
                    logger.info(
                        "Set custom name for location %d: %s", location_id, custom_name
                    )
                else:
                    logger.info("Removed custom name for location %d", location_id)
                logger.debug(
                    "Updated location_service cache for location_id=%s", location_id
                )
        except Exception as e:
            logger.warning("Failed to update location_service cache: %s", e)

        # Force table refresh to show changes immediately
        if rows_updated > 0:
            logger.info("Refreshing table with %d updated rows", rows_updated)
            self.table.set_rows(self._rows_cache)
            # Force repaint to ensure UI updates
            try:
                vp = self.table.viewport()
                if vp is not None:
                    vp.update()
            except Exception:
                pass
        else:
            logger.debug("No rows updated for location %d", location_id)

        # NOW refresh ALL location names from location_service cache to ensure
        # the table shows updated custom names (all locations, not just the changed one)
        # NOTE: location_display is a computed field, so we must update structure_name/station_name
        try:
            location_service = getattr(self._assets, "_location_service", None)
            if location_service:
                names_updated = 0
                for row in self._rows_cache:
                    # Check structure_id first (most common for player assets)
                    if row.get("structure_id"):
                        loc_id = row["structure_id"]
                        try:
                            disp = location_service.get_display_name(int(loc_id))
                        except Exception:
                            try:
                                disp = location_service.get_display_name(loc_id)
                            except Exception:
                                disp = None
                        if disp:
                            row["structure_name"] = disp
                            # location_display will be recomputed from structure_name
                            names_updated += 1
                            try:
                                row["location_display"] = (
                                    self._compute_location_display_from_row(row)
                                )
                            except Exception:
                                pass
                    # Check station_id
                    elif row.get("station_id"):
                        loc_id = row["station_id"]
                        try:
                            disp = location_service.get_display_name(int(loc_id))
                        except Exception:
                            try:
                                disp = location_service.get_display_name(loc_id)
                            except Exception:
                                disp = None
                        if disp:
                            row["station_name"] = disp
                            # location_display will be recomputed from station_name
                            names_updated += 1
                            try:
                                row["location_display"] = (
                                    self._compute_location_display_from_row(row)
                                )
                            except Exception:
                                pass
                logger.debug(
                    "Refreshed %d location names from service cache", names_updated
                )
        except Exception as e:
            logger.warning("Failed to refresh location names from cache: %s", e)

        # ALWAYS set rows to trigger UI update (force repaint)
        self.table.set_rows(self._rows_cache)
        # Non-critical; continue silently
        pass

    def _get_fuzzwork_price(self, type_id: int) -> float | None:
        """Get sell price from fuzzwork data for Jita."""
        if not self._fuzzwork or not self._fuzzwork.is_loaded:
            return None
        market_data = self._fuzzwork.get_market_data(type_id)
        if not market_data or not market_data.region_data:
            return None
        # Prefer Jita (region 10000002)
        jita_data = market_data.region_data.get(10000002)
        if jita_data and jita_data.sell_stats:
            return jita_data.sell_stats.median
        # Fallback to any region with sell data
        for region_data in market_data.region_data.values():
            if region_data.sell_stats:
                return region_data.sell_stats.median
        return None

    def _restore_column_state(self) -> None:
        """Restore column visibility, order, and widths from settings."""
        ui_settings = self._settings.get_ui_settings("assets")
        if not ui_settings.visible_columns:
            return  # First run, use defaults

        # Restore column order if saved
        header = self.table.horizontalHeader()
        if header is None:
            return
        self._restoring_state = True
        if ui_settings.column_order:
            # Create mapping of column keys to logical indices
            key_to_logical = {key: idx for idx, (key, _) in enumerate(self._columns)}

            # Move columns to match saved visual order
            for visual_idx, col_key in enumerate(ui_settings.column_order):
                if col_key in key_to_logical:
                    logical_idx = key_to_logical[col_key]
                    current_visual = header.visualIndex(logical_idx)
                    if current_visual != visual_idx:
                        header.moveSection(current_visual, visual_idx)

        # Restore column widths if saved
        if ui_settings.col_widths:
            key_to_logical = {key: idx for idx, (key, _) in enumerate(self._columns)}
            for col_key, width in ui_settings.col_widths.items():
                if col_key in key_to_logical:
                    logical_idx = key_to_logical[col_key]
                    header.resizeSection(logical_idx, width)

        # Hide columns not in visible list
        for col_idx, (col_key, _col_title) in enumerate(self._columns):
            if col_key not in ui_settings.visible_columns:
                self.table.setColumnHidden(col_idx, True)
        self._restoring_state = False

    def _save_column_state(self) -> None:
        """Save column visibility, order, and widths to settings."""
        visible = []
        column_order = []
        col_widths = {}
        header = self.table.horizontalHeader()
        if header is None:
            return

        # Build visual order list (actual display order left to right)
        for visual_idx in range(len(self._columns)):
            logical_idx = header.logicalIndex(visual_idx)
            col_key, _ = self._columns[logical_idx]
            column_order.append(col_key)
            col_widths[col_key] = header.sectionSize(logical_idx)
            if not self.table.isColumnHidden(logical_idx):
                visible.append(col_key)

        self._settings.update_ui_settings(
            "assets",
            visible_columns=visible,
            column_order=column_order,
            col_widths=col_widths,
        )

    def refresh_assets(self) -> None:
        """Manually refresh assets from ESI (with authentication)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self._load_assets_async())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _on_character_added(self, character_data: dict) -> None:
        """Reload assets when a new character is added."""
        task = asyncio.create_task(self._load_assets_async())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _show_overrides_dialog(self) -> None:
        """Show the custom overrides management dialog."""
        # Get SDE provider from asset service for type/system name resolution
        sde = getattr(self._assets, "_sde", None) or getattr(
            self._assets, "_sde_provider", None
        )
        dlg = CustomOverridesDialog(
            self,
            sde_provider=sde,
            esi_client=self._esi,
            location_service=self._location_service,
        )
        dlg.exec()
