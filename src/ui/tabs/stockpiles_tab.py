"""Stockpiles view for managing target inventory quantities per location."""

from __future__ import annotations

import asyncio
import logging

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from services.asset_service import AssetService
from ui.signal_bus import get_signal_bus

logger = logging.getLogger(__name__)


class StockpilesTab(QWidget):
    """Stockpiles view for defining and tracking target inventory quantities."""

    def __init__(
        self,
        asset_service: AssetService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._asset_service = asset_service
        self._background_tasks: set[asyncio.Task] = set()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup UI layout and widgets."""
        main_layout = QVBoxLayout(self)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        self._create_stockpile_btn = QPushButton("Create Stockpile")
        toolbar_layout.addWidget(self._create_stockpile_btn)

        self._add_target_btn = QPushButton("Add Target")
        self._add_target_btn.setEnabled(False)
        toolbar_layout.addWidget(self._add_target_btn)

        self._refresh_btn = QPushButton("Refresh")
        toolbar_layout.addWidget(self._refresh_btn)

        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)

        # Table widget for stockpiles
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            [
                "Stockpile",
                "Location",
                "Target Items",
                "Current Items",
                "Shortfall",
                "Status",
            ]
        )
        main_layout.addWidget(self._table)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._signal_bus.character_updated.connect(self._on_character_updated)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        self._create_stockpile_btn.clicked.connect(self._on_create_stockpile)
        self._add_target_btn.clicked.connect(self._on_add_target)

    def _on_character_updated(self, character_info: dict) -> None:
        """Handle character update signal."""
        self._on_refresh_clicked()

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        task = asyncio.create_task(self._do_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _do_refresh(self) -> None:
        """Async refresh of stockpiles."""
        try:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Loading...")

            # TODO: Get character ID from signal bus or main window
            # For now, just clear the table
            self._table.setRowCount(0)

        except Exception as e:
            logger.error("Error refreshing stockpiles: %s", e, exc_info=True)
            self._signal_bus.error_occurred.emit(str(e))
        finally:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Refresh")

    def _on_create_stockpile(self) -> None:
        """Handle create stockpile button click."""
        logger.info("Create stockpile clicked")
        # TODO: Open create stockpile dialog

    def _on_add_target(self) -> None:
        """Handle add target button click."""
        logger.info("Add target clicked")
        # TODO: Open add target dialog
