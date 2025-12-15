"""Wallet journal view displaying ISK flow ledger for characters."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import (
    QDateTimeEdit,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.eve import EveJournalEntry
from services.character_service import CharacterService
from services.wallet_service import WalletService
from ui.menus.context_menu_factory import ContextMenuFactory
from ui.signal_bus import get_signal_bus
from ui.widgets.advanced_table_widget import AdvancedTableView
from ui.widgets.filter_widget import ColumnSpec, FilterWidget
from utils.settings_manager import get_settings_manager

if TYPE_CHECKING:
    from data import SDEProvider

logger = logging.getLogger(__name__)


class JournalTab(QWidget):
    """Wallet journal view with date range filtering and type filtering."""

    def __init__(
        self,
        wallet_service: WalletService,
        character_service: CharacterService,
        sde_provider: SDEProvider,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._wallet_service = wallet_service
        self._character_service = character_service
        self._sde = sde_provider
        self._background_tasks: set[asyncio.Task] = set()
        self._current_characters: list = []
        self._character_names: dict[int, str] = {}  # Cache for character name lookups
        self._settings = get_settings_manager()
        self._context_menu_factory = ContextMenuFactory(self._settings)

        self._columns: list[tuple[str, str]] = [
            ("date", "Date"),
            ("ref_type", "Type"),
            ("amount", "Amount"),
            ("balance", "Balance"),
            ("description", "Description"),
        ]

        self._filter_specs: list[ColumnSpec] = [
            ColumnSpec("date", "Date", "text"),
            ColumnSpec("ref_type", "Type", "text"),
            ColumnSpec("amount", "Amount", "float"),
            ColumnSpec("balance", "Balance", "float"),
            ColumnSpec("description", "Description", "text"),
        ]

        self._setup_ui()
        self._connect_signals()
        self._rows_cache: list[dict[str, Any]] = []

    def _setup_ui(self) -> None:
        """Setup UI layout and widgets."""
        main_layout = QVBoxLayout(self)

        # Date range filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("From:"))

        self._start_date_edit = QDateTimeEdit()
        self._start_date_edit.setDateTime(
            QDateTime.fromMSecsSinceEpoch(
                int((datetime.now(UTC) - timedelta(days=30)).timestamp() * 1000)
            )
        )
        self._start_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        filter_layout.addWidget(self._start_date_edit)

        filter_layout.addWidget(QLabel("To:"))
        self._end_date_edit = QDateTimeEdit()
        self._end_date_edit.setDateTime(QDateTime.currentDateTime())
        self._end_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        filter_layout.addWidget(self._end_date_edit)

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
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle characters loaded signal."""
        self._current_characters = characters
        self._on_refresh_clicked()

    def _on_character_updated(self, character_info: dict) -> None:
        """Handle character update signal."""
        self._on_refresh_clicked()

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        task = asyncio.create_task(self._do_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _do_refresh(self) -> None:
        """Async refresh of journal data."""
        try:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Loading...")

            # Get start/end dates from UI
            start_dt = self._start_date_edit.dateTime().toPyDateTime()
            end_dt = self._end_date_edit.dateTime().toPyDateTime()

            # Fetch journal entries for all characters
            all_entries: list[EveJournalEntry] = []
            if self._current_characters:
                for char in self._current_characters:
                    char_id = getattr(char, "character_id", None)
                    if char_id:
                        try:
                            # Use date range query instead of days-based query
                            entries = (
                                await self._wallet_service.get_journal_by_date_range(
                                    character_id=char_id,
                                    start_date=start_dt,
                                    end_date=end_dt,
                                )
                            )
                            all_entries.extend(entries)
                        except Exception as e:
                            logger.warning(
                                "Failed to fetch journal for character %s: %s",
                                char_id,
                                e,
                            )

            # Sort by date descending (filtering already done by query)
            all_entries.sort(key=lambda e: e.date, reverse=True)

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

            # Convert entries to row data
            self._rows_cache = [self._entry_to_row(entry) for entry in all_entries]
            self._table.set_rows(self._rows_cache)
            self._update_summary()
        except Exception as e:
            logger.error("Error refreshing journal: %s", e, exc_info=True)
            self._signal_bus.error_occurred.emit(str(e))
        finally:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Refresh")

    def _entry_to_row(self, entry: EveJournalEntry) -> dict[str, Any]:
        """Convert journal entry to row dict for table."""
        # Enrich description with character names if available
        description = entry.description or ""

        # Try to enrich first party reference
        if entry.first_party_id and entry.first_party_id in self._character_names:
            description = description.replace(
                str(entry.first_party_id), self._character_names[entry.first_party_id]
            )

        # Try to enrich second party reference if present
        if entry.second_party_id and entry.second_party_id in self._character_names:
            description = description.replace(
                str(entry.second_party_id), self._character_names[entry.second_party_id]
            )

        return {
            "date": entry.date.isoformat(),
            "ref_type": entry.ref_type.replace("_", " ").title(),
            "amount": f"{entry.amount:,.2f}",
            "balance": f"{entry.balance:,.2f}",
            "description": description,
            "context_id": entry.context_id or 0,  # For context menu
            "context_id_type": entry.context_id_type or "",  # For context menu
        }

    def _on_filter_changed(self, filter_spec: dict) -> None:
        """Handle filter changes."""
        # Apply filter to cached rows
        filtered_rows = self._apply_filters(self._rows_cache, filter_spec)
        self._table.set_rows(filtered_rows)
        self._update_summary()

    def _apply_filters(
        self, rows: list[dict[str, Any]], filter_spec: dict
    ) -> list[dict[str, Any]]:
        """Apply filters to rows."""
        # Simple implementation - filter widget handles complex logic
        return rows

    def _update_summary(self) -> None:
        """Update summary label."""
        if not self._rows_cache:
            self._summary_label.setText("No entries")
            return

        total_entries = len(self._rows_cache)
        self._summary_label.setText(f"Total entries: {total_entries}")

    def _build_context_menu(self, selected_rows: list[dict[str, Any]]):
        """Build context menu for selected rows.

        Supports copy and custom location actions for journal entries
        with context references (e.g., contract IDs).
        """
        return self._context_menu_factory.build_table_menu(
            self,
            selected_rows,
            self._columns,
            enable_copy=True,
            enable_custom_price=False,  # Journal entries don't have prices
            enable_custom_location=True,  # Context IDs can reference locations
            location_id_key="context_id",  # Use context_id for location references
        )
