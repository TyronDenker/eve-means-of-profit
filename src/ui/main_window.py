"""Main UI window for EVE Means of Profit application."""

import logging

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from src.core import (
    BlueprintService,
    ManufacturingService,
    MarketService,
    PriceAnalyzer,
    TypeService,
)
from src.data.managers import SDEManager
from src.ui.widgets import ManufacturingWindow, TypesBrowser

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(
        self,
        sde_manager: SDEManager,
        market_service: MarketService | None = None,
        price_analyzer: PriceAnalyzer | None = None,
        type_service: TypeService | None = None,
        blueprint_service: BlueprintService | None = None,
        manufacturing_service: ManufacturingService | None = None,
    ):
        """Initialize the main window.

        Args:
            sde_manager: SDEManager instance for data access
            market_service: MarketService for market operations
            price_analyzer: PriceAnalyzer for price analysis
            type_service: TypeService for type operations
            blueprint_service: BlueprintService for blueprint calculations
            manufacturing_service: ManufacturingService for manufacturing

        """
        super().__init__()
        self._sde_manager = sde_manager
        self._market_service = market_service
        self._price_analyzer = price_analyzer
        self._type_service = type_service
        self._blueprint_service = blueprint_service
        self._manufacturing_service = manufacturing_service
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        self.setWindowTitle("EVE Means of Profit - Data Browser")
        self.setMinimumSize(1200, 800)

        # Create tab widget
        tabs = QTabWidget()

        # Types browser tab (pass services)
        types_browser = TypesBrowser(
            sde_manager=self._sde_manager,
            market_service=self._market_service,
            price_analyzer=self._price_analyzer,
        )
        tabs.addTab(types_browser, "Types Browser")

        # Manufacturing calculator tab (pass services)
        if self._manufacturing_service:
            manufacturing_widget = ManufacturingWindow(
                sde_manager=self._sde_manager,
                manufacturing_service=self._manufacturing_service,
            )
            tabs.addTab(manufacturing_widget, "Manufacturing Calculator")

        self.setCentralWidget(tabs)

        # Status bar
        status_bar = self.statusBar()
        if status_bar:
            status_bar.showMessage("Ready")

        logger.info("Main window initialized")
