"""Main application class for EVE Means of Profit UI."""

import logging
import sys

from PyQt6.QtWidgets import QApplication

from core import (
    BlueprintService,
    ManufacturingService,
    MarketService,
    PriceAnalyzer,
    TypeService,
)
from data.parsers.fuzzwork_csv import FuzzworkCSVParser
from data.parsers.sde_jsonl import SDEJsonlParser
from data.providers import MarketDataProvider, SDEProvider
from ui.main_window import MainWindow

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
        # Dependency Injection - Layer 1: Data Parsers
        # ============================================================
        logger.info("Initializing data parsers...")
        self._sde_parser = SDEJsonlParser()
        self._market_parser = FuzzworkCSVParser()

        # ============================================================
        # Dependency Injection - Layer 2: Data Providers
        # ============================================================
        logger.info("Initializing data providers...")
        self._sde_provider = SDEProvider(parser=self._sde_parser)
        self._market_provider = MarketDataProvider(parser=self._market_parser)

        # ============================================================
        # Dependency Injection - Layer 3: Core Services
        # ============================================================
        logger.info("Initializing core services...")
        self._market_service = MarketService(self._market_provider)
        self._price_analyzer = PriceAnalyzer(self._market_provider)
        self._type_service = TypeService(self._sde_provider, self._market_provider)
        self._blueprint_service = BlueprintService(
            self._sde_provider, self._market_provider
        )
        self._manufacturing_service = ManufacturingService(
            self._sde_provider, self._market_provider
        )

        # ============================================================
        # Dependency Injection - Layer 4: UI Components
        # ============================================================
        logger.info("Creating main window...")
        self._main_window = MainWindow(
            sde_provider=self._sde_provider,
            market_provider=self._market_provider,
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
