"""Wallet transactions view displaying buy/sell market transaction history."""

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

from models.eve import EveTransaction
from services.location_service import LocationService
from services.wallet_service import WalletService
from ui.menus.context_menu_factory import ContextMenuFactory
from ui.signal_bus import get_signal_bus
from ui.widgets.advanced_table_widget import AdvancedTableView
from ui.widgets.filter_widget import ColumnSpec, FilterWidget
from utils.settings_manager import get_settings_manager

if TYPE_CHECKING:
    from data import SDEProvider

logger = logging.getLogger(__name__)


class TransactionsTab(QWidget):
    """Wallet transactions view with date range and type filtering."""

    def __init__(
        self,
        wallet_service: WalletService,
        location_service: LocationService,
        sde_provider: SDEProvider,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._wallet_service = wallet_service
        self._location_service = location_service
        self._sde = sde_provider
        self._background_tasks: set[asyncio.Task] = set()
        self._current_characters: list = []
        self._settings = get_settings_manager()
        self._context_menu_factory = ContextMenuFactory(self._settings)

        self._columns: list[tuple[str, str]] = [
            ("date", "Date"),
            ("type_name", "Item"),
            ("quantity", "Qty"),
            ("unit_price", "Unit Price"),
            ("total_value", "Total Value"),
            ("is_buy_str", "Type"),
            ("location_name", "Location"),
        ]

        self._filter_specs: list[ColumnSpec] = [
            ColumnSpec("date", "Date", "text"),
            ColumnSpec("type_name", "Item", "text"),
            ColumnSpec("quantity", "Qty", "int"),
            ColumnSpec("unit_price", "Unit Price", "float"),
            ColumnSpec("total_value", "Total Value", "float"),
            ColumnSpec("is_buy_str", "Type", "text"),
            ColumnSpec("location_name", "Location", "text"),
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
        """Async refresh of transaction data."""
        try:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Loading...")

            # Get start/end dates from UI
            start_dt = self._start_date_edit.dateTime().toPyDateTime()
            end_dt = self._end_date_edit.dateTime().toPyDateTime()

            # Fetch transactions for all characters
            all_transactions: list[EveTransaction] = []
            if self._current_characters:
                for char in self._current_characters:
                    char_id = getattr(char, "character_id", None)
                    if char_id:
                        try:
                            # Use date range query instead of days-based query
                            txs = await self._wallet_service.get_transactions_by_date_range(
                                character_id=char_id,
                                start_date=start_dt,
                                end_date=end_dt,
                            )
                            all_transactions.extend(txs)
                        except Exception as e:
                            logger.warning(
                                "Failed to fetch transactions for character %s: %s",
                                char_id,
                                e,
                            )

            # Sort by date descending (filtering already done by query)
            all_transactions.sort(key=lambda t: t.date, reverse=True)

            # Collect unique type IDs and location IDs for bulk resolution
            type_ids = {tx.type_id for tx in all_transactions}
            location_ids = {tx.location_id for tx in all_transactions}

            # Resolve type names from SDE
            type_names: dict[int, str] = {}
            for type_id in type_ids:
                eve_type = self._sde.get_type_by_id(type_id)
                if eve_type and eve_type.name:
                    type_names[type_id] = eve_type.name
                else:
                    type_names[type_id] = f"Type {type_id}"

            # Resolve location names using LocationService
            location_names: dict[int, str] = {}
            if location_ids and self._current_characters:
                # Use first character for structure access if needed
                char_id = getattr(self._current_characters[0], "character_id", None)
                if char_id:
                    try:
                        locations = await self._location_service.resolve_locations_bulk(
                            list(location_ids),
                            character_id=char_id,
                            refresh_stale=False,  # Use cached for speed
                        )
                        for loc_id, loc_info in locations.items():
                            location_names[loc_id] = (
                                loc_info.custom_name or loc_info.name
                            )
                    except Exception:
                        logger.warning(
                            "Failed to resolve locations for transactions",
                            exc_info=True,
                        )
                        # Fallback to ID-based names
                        for loc_id in location_ids:
                            if loc_id not in location_names:
                                location_names[loc_id] = f"Location {loc_id}"

            # Convert transactions to row data with enriched names
            self._rows_cache = [
                self._tx_to_row(tx, type_names, location_names)
                for tx in all_transactions
            ]
            self._table.set_rows(self._rows_cache)
            self._update_summary()
        except Exception as e:
            logger.error("Error refreshing transactions: %s", e, exc_info=True)
            self._signal_bus.error_occurred.emit(str(e))
        finally:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Refresh")

    def _tx_to_row(
        self,
        tx: EveTransaction,
        type_names: dict[int, str] | None = None,
        location_names: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        """Convert transaction to row dict for table."""
        total_value = tx.quantity * tx.unit_price

        # Use enriched names if available
        type_name = (
            type_names.get(tx.type_id, f"Type {tx.type_id}")
            if type_names
            else f"Type {tx.type_id}"
        )
        location_name = (
            location_names.get(tx.location_id, f"Location {tx.location_id}")
            if location_names
            else f"Location {tx.location_id}"
        )

        return {
            "date": tx.date.isoformat(),
            "type_name": type_name,
            "type_id": tx.type_id,  # Include for context menu custom price actions
            "quantity": f"{tx.quantity:,}",
            "unit_price": f"{tx.unit_price:,.2f}",
            "total_value": f"{total_value:,.2f}",
            "is_buy_str": "BUY" if tx.is_buy else "SELL",
            "location_name": location_name,
            "location_id": tx.location_id,  # Include for context menu
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
            self._summary_label.setText("No transactions")
            return

        total_txs = len(self._rows_cache)
        self._summary_label.setText(f"Total transactions: {total_txs}")

    def _build_context_menu(self, selected_rows: list[dict[str, Any]]):
        """Build context menu for selected rows."""
        return self._context_menu_factory.build_table_menu(
            self,
            selected_rows,
            self._columns,
            enable_copy=True,
            enable_custom_price=True,  # Allow setting custom prices for traded items
            enable_custom_location=True,  # Allow setting custom location names
            type_id_key="type_id",
            location_id_key="location_id",
        )
