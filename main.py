"""Main application class for EVE Means of Profit UI."""

import logging
import sys

from PyQt6.QtWidgets import QApplication

from src.core import (
    BlueprintService,
    ManufacturingService,
    MarketService,
    PriceAnalyzer,
    TypeService,
)
from src.data.loaders.fuzzwork_csv import FuzzworkCSVLoader
from src.data.loaders.sde_jsonl import SDEJsonlLoader
from src.data.managers import MarketDataManager, SDEManager
from src.ui.main_window import MainWindow

logger = logging.getLogger(__name__)


class EVEProfitApp:
    """Main application class."""

    def __init__(self):
        """Initialize the application."""
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Create Qt application
        self._app = QApplication(sys.argv)
        self._app.setApplicationName("EVE Means of Profit")
        self._app.setOrganizationName("EVE Tools")

        # ============================================================
        # Dependency Injection - Layer 1: Data Loaders
        # ============================================================
        logger.info("Initializing data loaders...")
        self._sde_loader = SDEJsonlLoader()
        self._market_loader = FuzzworkCSVLoader()

        # ============================================================
        # Dependency Injection - Layer 2: Data Managers
        # ============================================================
        logger.info("Initializing data managers...")
        self._sde_manager = SDEManager(loader=self._sde_loader)
        self._market_manager = MarketDataManager(loader=self._market_loader)

        # ============================================================
        # Dependency Injection - Layer 3: Core Services
        # ============================================================
        logger.info("Initializing core services...")
        self._market_service = MarketService(self._market_manager)
        self._price_analyzer = PriceAnalyzer(self._market_manager)
        self._type_service = TypeService(self._sde_manager, self._market_manager)
        self._blueprint_service = BlueprintService(
            self._sde_manager, self._market_manager
        )
        self._manufacturing_service = ManufacturingService(
            self._sde_manager, self._market_manager
        )

        # ============================================================
        # Dependency Injection - Layer 4: UI Components
        # ============================================================
        logger.info("Creating main window...")
        self._main_window = MainWindow(
            sde_manager=self._sde_manager,
            market_manager=self._market_manager,
            market_service=self._market_service,
            price_analyzer=self._price_analyzer,
            type_service=self._type_service,
            blueprint_service=self._blueprint_service,
            manufacturing_service=self._manufacturing_service,
        )

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code

        """
        logger.info("Starting application...")
        self._main_window.show()
        return self._app.exec()


def main() -> int:
    """Application entry point.

    Returns:
        Exit code

    """
    app = EVEProfitApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
