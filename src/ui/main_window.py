"""Main UI window for EVE Means of Profit application."""

import logging

from PyQt6.QtWidgets import QMainWindow, QTabWidget

from src.data.managers import SDEManager
from src.ui.widgets import BlueprintViewer, TypesBrowser

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, sde_manager: SDEManager):
        """Initialize the main window.

        Args:
            sde_manager: SDEManager instance for data access

        """
        super().__init__()
        self._sde_manager = sde_manager
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        self.setWindowTitle("EVE Means of Profit - Data Browser")
        self.setMinimumSize(1200, 800)

        # Create tab widget
        tabs = QTabWidget()

        # Types browser tab
        types_browser = TypesBrowser(self._sde_manager)
        tabs.addTab(types_browser, "Types Browser")

        # Blueprint viewer tab
        blueprint_viewer = BlueprintViewer(self._sde_manager)
        tabs.addTab(blueprint_viewer, "Blueprint Viewer")

        self.setCentralWidget(tabs)

        # Status bar
        self.statusBar().showMessage("Ready")

        logger.info("Main window initialized")
