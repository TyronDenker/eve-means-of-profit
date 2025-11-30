"""Main application window."""

import asyncio
import logging
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
)
from qasync import QEventLoop, asyncSlot

from data import SDEProvider
from data.clients import ESIClient
from data.parsers import SDEJsonlParser
from data.repositories import Repository
from services.asset_service import AssetService
from services.character_service import CharacterService
from services.contract_service import ContractService
from services.industry_service import IndustryService
from services.location_service import LocationService
from services.market_service import MarketService
from services.wallet_service import WalletService
from src.utils import global_config
from ui.dialogs.auth_dialog import AuthDialog
from ui.signal_bus import get_signal_bus
from ui.tabs import CharactersTab

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        """Initialize main window."""
        super().__init__()
        self._signal_bus = get_signal_bus()
        self._background_tasks: set[asyncio.Task] = set()

        # Import and initialize settings manager at the top
        from src.utils.settings_manager import get_settings_manager
        self._settings = get_settings_manager()

        # Initialize services
        self._esi_client = ESIClient()
        self._character_service = CharacterService()
        self._repository = Repository()

        # Initialize providers
        sde_data_path = str(global_config.sde.sde_dir_path)
        sde_parser = SDEJsonlParser(sde_data_path)
        self._sde_provider = SDEProvider(sde_parser)

        # Initialize business services
        self._location_service = LocationService(self._esi_client, self._sde_provider)
        self._asset_service = AssetService(
            self._sde_provider, self._location_service, self._repository
        )
        self._wallet_service = WalletService(self._esi_client, self._repository)
        self._market_service = MarketService(self._esi_client, self._repository)
        self._contract_service = ContractService(self._esi_client, self._repository)
        self._industry_service = IndustryService(self._esi_client, self._repository)

        self.setWindowTitle(f"{global_config.app.name} v{global_config.app.version}")
        # Use settings manager for window size if available, else fallback
        window_size = self._settings.get_ui_settings("main_window").col_widths if "main_window" in self._settings._settings.ui and self._settings.get_ui_settings("main_window").col_widths else [1000, 700]
        self.setMinimumSize(*window_size)

        self._setup_ui()
        self._connect_signals()

    @asyncSlot()
    async def initialize_async(self):
        """Async initialization for repository and other startup tasks."""
        await self._repository.initialize()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        # Create menu bar
        self._create_menu_bar()

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.setCentralWidget(self.tab_widget)

        # Create characters tab
        self.characters_tab = CharactersTab(
            character_service=self._character_service,
            esi_client=self._esi_client,
            asset_service=self._asset_service,
            wallet_service=self._wallet_service,
            market_service=self._market_service,
            contract_service=self._contract_service,
            industry_service=self._industry_service,
        )
        # Use tab name from config or settings manager if available
        tab_name = self._settings.get_ui_settings("characters_tab").column_order[0] if "characters_tab" in self._settings._settings.ui and self._settings.get_ui_settings("characters_tab").column_order else "Characters"
        self.tab_widget.addTab(self.characters_tab, tab_name)

        # Placeholder for future tabs
        # TODO: Add additional tabs (e.g., Assets, Market, Industry, etc.)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _create_menu_bar(self) -> None:
        """Create menu bar."""
        menubar = self.menuBar()
        if not menubar:
            return

        # File menu
        file_menu = menubar.addMenu("&File")
        if not file_menu:
            return

        add_char_action = QAction("&Add Character", self)
        add_char_action.setShortcut("Ctrl+N")
        add_char_action.triggered.connect(self._on_add_character)
        file_menu.addAction(add_char_action)

        remove_char_action = QAction("&Remove Character", self)
        remove_char_action.triggered.connect(self._on_remove_character)
        file_menu.addAction(remove_char_action)

        file_menu.addSeparator()

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        if not help_menu:
            return

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)

    def _connect_signals(self) -> None:
        """Connect signal bus signals to handlers."""
        self._signal_bus.status_message.connect(self._on_status_message)
        self._signal_bus.error_occurred.connect(self._on_error)
        self._signal_bus.info_message.connect(self._on_info)
        self._signal_bus.character_selected.connect(self._on_character_selected)

    def _on_add_character(self) -> None:
        """Handle add character action."""
        dialog = AuthDialog(self._character_service, self)
        dialog.exec()

    def _on_remove_character(self) -> None:
        """Handle remove character action."""
        self._signal_bus.info_message.emit(
            "Please right-click a character in the list to remove them"
        )

    def _on_about(self) -> None:
        """Show about dialog."""
        about_text = f"""
        <h2>{global_config.app.name}</h2>
        <p>Version {global_config.app.version}</p>
        <p>A fully featured EVE Online tool for asset tracking, manufacturing and trading analysis.</p>
        <p><b>Contact:</b></p>
        <ul>
        """

        if global_config.app.contact_github:
            about_text += f"<li>GitHub: {global_config.app.contact_github}</li>"
        if global_config.app.contact_discord:
            about_text += f"<li>Discord: {global_config.app.contact_discord}</li>"
        if global_config.app.contact_eve:
            about_text += f"<li>EVE: {global_config.app.contact_eve}</li>"

        about_text += "</ul>"

        QMessageBox.about(self, "About", about_text)

    def _on_status_message(self, message: str) -> None:
        """Handle status message.

        Args:
            message: Status message
        """
        self.status_bar.showMessage(message, 5000)

    def _on_error(self, message: str) -> None:
        """Handle error message.

        Args:
            message: Error message
        """
        self.status_bar.showMessage(f"Error: {message}", 10000)
        QMessageBox.critical(self, "Error", message)

    def _on_info(self, message: str) -> None:
        """Handle info message.

        Args:
            message: Info message
        """
        self.status_bar.showMessage(message, 5000)
        QMessageBox.information(self, "Information", message)

    def _on_character_selected(self, character_id: int) -> None:
        """Handle character selection.

        Args:
            character_id: Selected character ID
        """
        self.status_bar.showMessage(f"Selected character: {character_id}", 3000)
        logger.debug("Character selected: %s", character_id)

    @asyncSlot()
    async def closeEvent(self, event) -> None:  # noqa: N802
        """Handle window close event (Qt method override).

        Args:
            event: Close event
        """
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Cleanup services
        await self._character_service.close()
        await self._esi_client.close()

        event.accept()


def main_window() -> int:
    """Main entry point for the application.

    Returns:
        Exit code
    """
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, global_config.app.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("qasync").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(global_config.app.name)
    app.setApplicationVersion(global_config.app.version)

    # Setup async event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Schedule async initialization after window is shown
    QTimer.singleShot(0, window.initialize_async)
    QTimer.singleShot(0, window.characters_tab.load_initial_characters)

    # Run event loop
    with loop:
        return loop.run_forever()
