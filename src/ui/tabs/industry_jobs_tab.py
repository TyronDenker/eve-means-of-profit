"""Industry jobs view displaying active and completed manufacturing/research/invention jobs."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.eve import EveIndustryJob
from services.character_service import CharacterService
from services.industry_service import IndustryService
from services.location_service import LocationService
from ui.menus.context_menu_factory import ContextMenuFactory
from ui.signal_bus import get_signal_bus
from ui.widgets.advanced_table_widget import AdvancedTableView
from ui.widgets.filter_widget import ColumnSpec, FilterWidget
from utils.settings_manager import get_settings_manager

if TYPE_CHECKING:
    from data import SDEProvider

logger = logging.getLogger(__name__)

# Activity type mappings
ACTIVITY_NAMES = {
    1: "Manufacturing",
    3: "Research Time Efficiency",
    4: "Research Material Efficiency",
    5: "Copy",
    7: "Reverse Engineering",
    8: "Invention",
    9: "Reaction",
}


class IndustryJobsTab(QWidget):
    """Industry jobs view with activity and status filtering."""

    def __init__(
        self,
        industry_service: IndustryService,
        character_service: CharacterService,
        location_service: LocationService,
        sde_provider: SDEProvider,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._industry_service = industry_service
        self._character_service = character_service
        self._location_service = location_service
        self._sde = sde_provider
        self._background_tasks: set[asyncio.Task] = set()
        self._current_characters: list = []
        self._character_names: dict[int, str] = {}  # Cache for character name lookups
        self._settings = get_settings_manager()
        self._context_menu_factory = ContextMenuFactory(self._settings)

        self._columns: list[tuple[str, str]] = [
            ("job_id", "Job ID"),
            ("installer_name", "Installer"),
            ("activity_name", "Activity"),
            ("product_name", "Product"),
            ("facility_name", "Facility"),
            ("status", "Status"),
            ("runs", "Runs"),
            ("cost", "Cost"),
            ("end_date", "Ends"),
            ("remaining_time", "Time Left"),
        ]

        self._filter_specs: list[ColumnSpec] = [
            ColumnSpec("job_id", "Job ID", "int"),
            ColumnSpec("installer_name", "Installer", "text"),
            ColumnSpec("activity_name", "Activity", "text"),
            ColumnSpec("product_name", "Product", "text"),
            ColumnSpec("facility_name", "Facility", "text"),
            ColumnSpec("status", "Status", "text"),
            ColumnSpec("runs", "Runs", "int"),
            ColumnSpec("cost", "Cost", "float"),
        ]

        self._setup_ui()
        self._connect_signals()
        self._rows_cache: list[dict[str, Any]] = []
        self._jobs_cache: list[EveIndustryJob] = []  # Cache for countdown updates

        # Setup countdown timer (1 second interval for accurate updates)
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)  # 1 second
        self._countdown_timer.timeout.connect(self._update_countdowns)
        # Timer will be started/stopped based on active jobs presence

    def _setup_ui(self) -> None:
        """Setup UI layout and widgets."""
        main_layout = QVBoxLayout(self)

        # Filter controls
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Activity:"))
        self._activity_combo = QComboBox()
        self._activity_combo.addItem("All", -1)
        for activity_id, name in ACTIVITY_NAMES.items():
            self._activity_combo.addItem(name, activity_id)
        self._activity_combo.currentIndexChanged.connect(self._on_activity_changed)
        filter_layout.addWidget(self._activity_combo)

        filter_layout.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItem("All", None)
        self._status_combo.addItem("Active", "active")
        self._status_combo.addItem("Paused", "paused")
        self._status_combo.addItem("Ready", "ready")
        self._status_combo.addItem("Delivered", "delivered")
        self._status_combo.addItem("Cancelled", "cancelled")
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        filter_layout.addWidget(self._status_combo)

        self._refresh_btn = QPushButton("Refresh")
        filter_layout.addWidget(self._refresh_btn)
        filter_layout.addStretch()

        main_layout.addLayout(filter_layout)

        # Filter widget
        self._filter_widget = FilterWidget(self._filter_specs)
        self._filter_widget.filter_changed.connect(self._on_filter_changed)
        main_layout.addWidget(self._filter_widget)

        # Table view
        self._table = AdvancedTableView()
        self._table.setup(self._columns)
        self._table.set_context_menu_builder(self._build_context_menu)
        main_layout.addWidget(self._table)

        # Summary label
        self._summary_label = QLabel("Loading...")
        main_layout.addWidget(self._summary_label)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._signal_bus.characters_loaded.connect(self._on_characters_loaded)
        self._signal_bus.character_updated.connect(self._on_character_updated)
        self._signal_bus.industry_jobs_refreshed.connect(self._on_jobs_refreshed)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle characters loaded signal."""
        self._current_characters = self._dedupe_characters(characters)
        self._on_refresh_clicked()

    def _on_character_updated(self, character_info: dict) -> None:
        """Handle character update signal."""
        self._on_refresh_clicked()

    def _on_jobs_refreshed(self, character_id: int) -> None:
        """Refresh when jobs finish syncing."""
        # Only refresh if we have characters loaded; this avoids redundant calls
        if self._current_characters:
            self._on_refresh_clicked()

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        task = asyncio.create_task(self._do_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _do_refresh(self) -> None:
        """Async refresh of industry jobs."""
        try:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Loading...")

            # Get activity and status filters
            activity_id = self._activity_combo.currentData()
            status = self._status_combo.currentData()

            # Fetch jobs for all characters
            all_jobs: list[EveIndustryJob] = []
            if self._current_characters:
                for char in self._current_characters:
                    char_id = getattr(char, "character_id", None)
                    if char_id:
                        try:
                            # Get jobs based on filters
                            if activity_id and activity_id != -1:
                                jobs = (
                                    await self._industry_service.get_jobs_by_activity(
                                        character_id=char_id, activity_id=activity_id
                                    )
                                )
                            elif status:
                                jobs = await self._industry_service.get_jobs_by_status(
                                    character_id=char_id, status=status
                                )
                            else:
                                jobs = await self._industry_service.get_active_jobs(
                                    character_id=char_id
                                )
                            all_jobs.extend(jobs)
                        except Exception as e:
                            logger.warning(
                                "Failed to fetch jobs for character %s: %s",
                                char_id,
                                e,
                            )

            # Build character name cache from authenticated characters
            try:
                authenticated_chars = (
                    await self._character_service.get_authenticated_characters(
                        use_cache_only=True
                    )
                )
                for char in authenticated_chars:
                    if hasattr(char, "character_id") and hasattr(
                        char, "character_name"
                    ):
                        self._character_names[char.character_id] = char.character_name
            except Exception:
                logger.debug("Failed to build character name cache", exc_info=True)

            # Collect unique facility IDs for location resolution
            facility_ids = {job.facility_id for job in all_jobs}
            facility_names: dict[int, str] = {}
            if facility_ids and self._current_characters:
                # Use first character for structure access if needed
                char_id = getattr(self._current_characters[0], "character_id", None)
                if char_id:
                    try:
                        locations = await self._location_service.resolve_locations_bulk(
                            list(facility_ids),
                            character_id=char_id,
                            refresh_stale=False,  # Use cached for speed
                        )
                        for loc_id, loc_info in locations.items():
                            facility_names[loc_id] = (
                                loc_info.custom_name or loc_info.name
                            )
                    except Exception:
                        logger.warning(
                            "Failed to resolve facilities for jobs", exc_info=True
                        )

            # Convert jobs to row data with enriched names
            self._jobs_cache = all_jobs  # Store for countdown updates
            self._rows_cache = [
                self._job_to_row(job, facility_names) for job in all_jobs
            ]

            self._table.set_rows(self._rows_cache)
            self._update_summary()

            # Start/stop countdown timer based on active jobs
            self._manage_countdown_timer()
        except Exception as e:
            logger.error("Error refreshing industry jobs: %s", e, exc_info=True)
            self._signal_bus.error_occurred.emit(str(e))
        finally:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Refresh")

    def _job_to_row(
        self, job: EveIndustryJob, facility_names: dict[int, str] | None = None
    ) -> dict[str, Any]:
        """Convert industry job to row dict for table."""
        activity_name = ACTIVITY_NAMES.get(
            job.activity_id, f"Activity {job.activity_id}"
        )
        now = datetime.now(UTC)
        remaining = job.end_date - now
        remaining_str = (
            str(remaining).split(".")[0]
            if remaining.total_seconds() > 0
            else "Complete"
        )

        # Resolve installer name from character cache
        installer_name = self._character_names.get(
            job.installer_id, f"Character {job.installer_id}"
        )

        # Resolve product name from SDE (if manufacturing)
        product_name = "-"
        if job.product_type_id:
            product_type = self._sde.get_type_by_id(job.product_type_id)
            if product_type and product_type.name:
                product_name = product_type.name
            else:
                product_name = f"Type {job.product_type_id}"
        else:
            # For research/invention, show blueprint type
            blueprint_type = self._sde.get_type_by_id(job.blueprint_type_id)
            if blueprint_type and blueprint_type.name:
                product_name = blueprint_type.name

        # Resolve facility name
        facility_name = (
            facility_names.get(job.facility_id, f"Facility {job.facility_id}")
            if facility_names
            else f"Facility {job.facility_id}"
        )

        return {
            "job_id": str(job.job_id),
            "installer_name": installer_name,
            "activity_name": activity_name,
            "product_name": product_name,
            "facility_name": facility_name,
            "status": job.status.title(),
            "runs": str(job.runs),
            "cost": f"{job.cost:,.2f}",
            "end_date": job.end_date.isoformat(),
            "remaining_time": remaining_str,
        }

    def _on_activity_changed(self, index: int) -> None:
        """Handle activity filter change."""
        self._on_refresh_clicked()

    def _on_status_changed(self, index: int) -> None:
        """Handle status filter change."""
        self._on_refresh_clicked()

    def _on_filter_changed(self, filter_spec: dict) -> None:
        """Handle filter changes."""
        # Apply filter to cached rows
        filtered_rows = self._apply_filters(self._rows_cache, filter_spec)
        self._table.set_rows(filtered_rows)
        self._update_summary()

    def _dedupe_characters(self, characters: list) -> list:
        """Return list without duplicate character_ids."""
        seen: set[int] = set()
        unique: list = []
        for char in characters:
            cid = getattr(char, "character_id", None)
            if cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            unique.append(char)
        return unique

    def _apply_filters(
        self, rows: list[dict[str, Any]], filter_spec: dict
    ) -> list[dict[str, Any]]:
        """Apply filters to rows."""
        # Simple implementation - filter widget handles complex logic
        return rows

    def _update_summary(self) -> None:
        """Update summary label."""
        if not self._rows_cache:
            self._summary_label.setText("No jobs")
            return

        total_jobs = len(self._rows_cache)
        total_cost = sum(
            float(row["cost"].replace(",", "")) for row in self._rows_cache
        )
        self._summary_label.setText(
            f"Total jobs: {total_jobs} | Total cost: {total_cost:,.2f} ISK"
        )

    def _build_context_menu(self, selected_rows: list[dict[str, Any]]):
        """Build context menu for selected rows."""
        return self._context_menu_factory.build_table_menu(
            self,
            selected_rows,
            self._columns,
            enable_copy=True,
            enable_custom_price=False,  # Jobs don't have prices to customize
            enable_custom_location=False,  # Job facilities are read-only
        )

    def _manage_countdown_timer(self) -> None:
        """Start or stop countdown timer based on active/paused jobs presence."""
        # Check if we have any jobs that need countdown updates
        has_active = any(job.status in ("active", "paused") for job in self._jobs_cache)

        if has_active and not self._countdown_timer.isActive():
            self._countdown_timer.start()
            logger.debug("Started countdown timer for %d jobs", len(self._jobs_cache))
        elif not has_active and self._countdown_timer.isActive():
            self._countdown_timer.stop()
            logger.debug("Stopped countdown timer (no active jobs)")

    def _update_countdowns(self) -> None:
        """Update Time Left column for all jobs without resetting view (called every 1 second).

        Uses update_rows_by_key to mutate only the changed columns (remaining_time, status)
        while preserving selection, sort order, and filter state.
        """
        if not self._jobs_cache or not self._rows_cache:
            return

        try:
            now = datetime.now(UTC)
            updates: dict[str, dict[str, Any]] = {}  # {job_id: {field: value, ...}}
            status_changes = []

            for job in self._jobs_cache:
                old_status = job.status
                job_id_str = str(job.job_id)

                # Compute remaining time
                remaining = job.end_date - now
                remaining_seconds = remaining.total_seconds()

                # Update status if job just completed
                if old_status in ("active", "paused") and remaining_seconds <= 0:
                    # Mark as ready (job finished but not delivered)
                    job.status = "ready"
                    status_changes.append((job.job_id, "ready"))

                # Format remaining time (clamp negative to 0)
                if remaining_seconds > 0:
                    # Format as HH:MM:SS
                    hours = int(remaining_seconds // 3600)
                    minutes = int((remaining_seconds % 3600) // 60)
                    seconds = int(remaining_seconds % 60)

                    if hours > 0:
                        remaining_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        remaining_str = f"{minutes:02d}:{seconds:02d}"
                elif job.status == "paused":
                    remaining_str = "Paused"
                else:
                    remaining_str = "Complete"

                # Prepare update if changed
                row_updates: dict[str, Any] = {}
                for row in self._rows_cache:
                    if row.get("job_id") == job_id_str:
                        if row.get("remaining_time") != remaining_str:
                            row_updates["remaining_time"] = remaining_str
                        if row.get("status") != job.status.title():
                            row_updates["status"] = job.status.title()
                        if row_updates:
                            updates[job_id_str] = row_updates
                        break

            # Update table rows using new API (preserves selection)
            if updates:
                self._table.update_rows_by_key("job_id", updates)

            # Preserve selection by job IDs
            selected_job_ids = set()
            sel_model = self._table.selectionModel()
            if sel_model is not None:
                for idx in sel_model.selectedIndexes():
                    row_idx = idx.row()
                    if row_idx < len(self._rows_cache):
                        job_id = self._rows_cache[row_idx].get("job_id")
                        if job_id:
                            selected_job_ids.add(job_id)

            # Reapply selection after updates
            if selected_job_ids:
                self._table.select_rows_by_key("job_id", selected_job_ids)

            # Log status changes
            if status_changes:
                logger.info(
                    "Industry jobs completed: %s",
                    ", ".join(f"#{job_id}" for job_id, _ in status_changes),
                )

            # Stop timer if no more active jobs
            if not any(job.status in ("active", "paused") for job in self._jobs_cache):
                self._countdown_timer.stop()
                logger.debug("All jobs completed, stopped countdown timer")

        except Exception as e:
            logger.error("Error updating countdowns: %s", e, exc_info=True)

    def cleanup(self) -> None:
        """Cleanup resources when tab is closed."""
        # Stop countdown timer
        if hasattr(self, "_countdown_timer"):
            self._countdown_timer.stop()

        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
