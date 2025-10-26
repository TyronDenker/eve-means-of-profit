"""Main application class for EVE Means of Profit UI."""

import logging
import sys

from PyQt6.QtWidgets import QApplication

from src.data.managers import SDEManager
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

        # Create SDE manager
        logger.info("Initializing SDE Manager...")
        self._sde_manager = SDEManager()

        # Create main window
        logger.info("Creating main window...")
        self._main_window = MainWindow(self._sde_manager)

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
