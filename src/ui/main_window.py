"""Main application window."""

import asyncio
import logging
import sys
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qasync import QEventLoop, asyncSlot

from data import FuzzworkProvider
from data.clients import FuzzworkClient
from data.parsers.fuzzwork_csv import FuzzworkCSVParser
from services.networth_service import NetWorthService
from ui.dialogs import PreferencesDialog
from ui.dialogs.auth_dialog import AuthDialog
from ui.signal_bus import get_signal_bus
from ui.styles import apply_dark_theme
from ui.tabs import (
    AssetsTab,
    AssetTreeTab,
    CharactersTab,
    IndustryJobsTab,
    IndustrySlotsTab,
    JournalTab,
    NetworthTab,
    StockpilesTab,
    TransactionsTab,
)
from ui.widgets import ProgressWidget
from utils import configure_container, get_container, global_config, setup_logging
from utils.progress_callback import ProgressPhase, ProgressUpdate
from utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        """Initialize main window."""
        super().__init__()

        # Initialize DI container and configure services
        configure_container()
        container = get_container()

        # Resolve core services from container
        self._signal_bus = get_signal_bus()
        self._settings = container.resolve("settings_manager")
        self._esi_client = container.resolve("esi_client")
        self._character_service = container.resolve("character_service")
        self._repository = container.resolve("repository")
        self._sde_provider = container.resolve("sde_provider")
        self._sde_client = container.resolve("sde_client")
        self._location_service = container.resolve("location_service")
        self._asset_service = container.resolve("asset_service")
        self._wallet_service = container.resolve("wallet_service")
        self._market_service = container.resolve("market_service")
        self._contract_service = container.resolve("contract_service")
        self._industry_service = container.resolve("industry_service")

        self._background_tasks: set[asyncio.Task] = set()

        # Fuzzwork client and provider - will be initialized async
        self._fuzzwork_client = FuzzworkClient()
        self._fuzzwork_provider: FuzzworkProvider | None = None
        self._fuzzwork_ready = False

        # NetWorthService initialized after fuzzwork_provider is ready
        self._networth_service: NetWorthService | None = None

        # Set up progress callback for SDE client
        self._sde_client.progress_callback = self._on_sde_progress

        self.setWindowTitle(f"{global_config.app.name} v{global_config.app.version}")
        # Use settings manager for window size if available, else fallback
        window_size = (
            self._settings.get_ui_settings("main_window").col_widths
            if "main_window" in self._settings._settings.ui
            and self._settings.get_ui_settings("main_window").col_widths
            else [1000, 700]
        )
        self.setMinimumSize(*window_size)

        self._setup_ui()
        self._connect_signals()

    @asyncSlot()
    async def initialize_async(self):
        """Three-phase async initialization for fast startup.

        Phase 0: Initialize critical data (SDE)
        Phase 1: Show cached data immediately (< 500ms)
        Phase 2: Start background updates (non-blocking)
        Phase 3: Data completes incrementally as background tasks finish
        """
        start_time = time.time()
        logger.info("PHASE 0 START - Initializing SDE")

        # PHASE 0: Initialize SDE (critical for other services)
        await self._phase0_initialize_sde()

        phase0_time = time.time() - start_time
        logger.info("PHASE 0 COMPLETE: %.2fs - SDE initialized", phase0_time)

        logger.info("PHASE 1 START - Loading cached data")

        # PHASE 1: Show cached data immediately
        await self._phase1_show_cached_data()

        phase1_time = time.time() - start_time
        logger.info(
            "PHASE 1 COMPLETE: %.2fs - UI visible with cached data", phase1_time
        )

        # PHASE 2: Start background updates (non-blocking)
        logger.info("PHASE 2 START - Starting background updates")
        await self._phase2_start_background_updates()
        logger.info("PHASE 2 STARTED - Background tasks running")

        # Enable tabs after all initialization is complete
        self.tab_widget.setEnabled(True)

    async def _phase0_initialize_sde(self) -> None:
        """Initialize SDE provider - critical for other services.

        SDE must be initialized before Phase 1 because LocationService,
        AssetService, and other data-dependent services require it.
        """
        try:
            # Check if SDE files exist, download if needed
            sde_files = list(self._sde_client.sde_dir.glob("*.jsonl"))
            if not sde_files:
                logger.info("SDE files not found - downloading initial SDE...")

                # Download latest SDE (progress shown via callback)
                success = await self._sde_client.download_sde()

                if not success:
                    logger.error("Failed to download initial SDE")
                    # Continue anyway - let services handle gracefully
                    return

            logger.info("Initializing SDE provider...")
            await self._sde_provider.initialize_async()
            logger.info("SDE provider initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize SDE: {e}", exc_info=True)
            if hasattr(self, "_progress_widget"):
                self._progress_widget.error("SDE initialization failed")
            # Continue anyway - services will handle missing SDE gracefully

    async def _phase1_show_cached_data(self):
        """Initialize cached data only - no network calls.

        Shows UI with cached data in < 500ms for fast perceived startup.
        """
        # Initialize repository (disk only, fast)
        await self._repository.initialize()

        # Get cached characters from service (use cache only, no ESI calls)
        try:
            characters = await self._character_service.get_authenticated_characters(
                use_cache_only=True
            )
            # Broadcast cached characters to all tabs for immediate display
            self._signal_bus.characters_loaded.emit(characters)
            logger.info(
                "Phase 1: Loaded %d cached characters for immediate display",
                len(characters),
            )
        except Exception as e:
            logger.warning("Phase 1: Failed to load cached characters: %s", e)
            # Emit empty list so UI initializes properly
            self._signal_bus.characters_loaded.emit([])

    async def _phase2_start_background_updates(self):
        """Start non-blocking async tasks for background updates.

        These tasks run in background without blocking UI interaction.
        SDE is already initialized in Phase 0 before this runs.
        """
        # 1. Check for SDE updates (quick check, download if needed)
        sde_update_task = asyncio.ensure_future(self._check_sde_updates())
        self._background_tasks.add(sde_update_task)
        sde_update_task.add_done_callback(lambda t: self._background_tasks.discard(t))

        # 2. Fuzzwork download (5-10 seconds typically)
        fuzzwork_task = asyncio.ensure_future(self._initialize_fuzzwork())
        self._background_tasks.add(fuzzwork_task)
        fuzzwork_task.add_done_callback(lambda t: self._background_tasks.discard(t))

        # 3. Refresh character data from ESI (network calls for fresh data)
        refresh_task = asyncio.ensure_future(self._refresh_characters_from_esi())
        self._background_tasks.add(refresh_task)
        refresh_task.add_done_callback(lambda t: self._background_tasks.discard(t))

    async def _refresh_characters_from_esi(self):
        """Fetch fresh character data from ESI in background.

        Updates the UI with fresh data as it arrives.
        """
        try:
            characters = await self._character_service.get_authenticated_characters(
                force_refresh=True
            )
            self._signal_bus.characters_loaded.emit(characters)
            logger.info("Phase 2: Refreshed %d characters from ESI", len(characters))
        except Exception as e:
            logger.warning("Phase 2: Failed to refresh characters from ESI: %s", e)

    async def _check_sde_updates(self) -> None:
        """Check for SDE updates and download if needed.

        This runs in the background on startup to ensure SDE is up to date.
        """
        try:
            logger.info("Checking for SDE updates...")
            needs_update, latest_build = await self._sde_client.check_for_updates()

            if needs_update:
                logger.info(f"SDE update available: {latest_build}")
                if hasattr(self, "_progress_widget"):
                    self._progress_widget.start_operation(
                        "Downloading SDE update...", total=100
                    )

                # Download the update
                success = await self._sde_client.download_sde(latest_build)

                if success:
                    logger.info("SDE updated successfully")
                    if hasattr(self, "_progress_widget"):
                        self._progress_widget.complete("SDE updated")

                    # Clear and rebuild SDE provider caches
                    self._sde_provider.clear_cache()
                    await self._sde_provider.initialize_async()
                else:
                    logger.warning("SDE update failed")
                    if hasattr(self, "_progress_widget"):
                        self._progress_widget.complete("SDE update failed")
            else:
                logger.info("SDE is up to date")

        except Exception as e:
            logger.error(f"Failed to check for SDE updates: {e}", exc_info=True)

    async def _initialize_fuzzwork(self) -> None:
        """Initialize fuzzwork data in background (non-blocking).

        Loads cached CSV if available. Does NOT trigger remote updates on startup.
        Updates occur only on explicit user-initiated refresh requests.
        """

        def progress_callback(update: ProgressUpdate) -> None:
            """Update progress widget with fuzzwork download progress."""
            if hasattr(self, "_progress_widget"):
                if update.total > 0:
                    percent = int((update.current / update.total) * 100)
                    self._progress_widget.update_progress(percent, update.message)
                else:
                    self._progress_widget.update_progress(0, update.message)

        try:
            # Show progress widget for fuzzwork download
            if hasattr(self, "_progress_widget"):
                self._progress_widget.start_operation(
                    "Loading market data...", total=100
                )

            # Fetch CSV data - do NOT check ETag or force download on startup
            # This ensures we only use cached data and don't trigger updates
            csv_text = await self._fuzzwork_client.fetch_aggregate_csv(
                force=False, check_etag=False, progress_callback=progress_callback
            )

            if csv_text:
                # Create provider with the CSV data
                if hasattr(self, "_progress_widget"):
                    self._progress_widget.update_progress(
                        90, "Processing market data..."
                    )
                parser = FuzzworkCSVParser(csv_text)
                self._fuzzwork_provider = FuzzworkProvider(parser)

                # Now create NetWorthService with the provider
                self._networth_service = NetWorthService(
                    esi_client=self._esi_client,
                    repository=self._repository,
                    fuzzwork_provider=self._fuzzwork_provider,
                    settings_manager=self._settings,
                    sde_provider=self._sde_provider,
                    location_service=self._location_service,
                )

                # Update the CharactersTab with the networth_service and fuzzwork_provider
                if hasattr(self, "characters_tab") and self.characters_tab:
                    self.characters_tab._networth_service = self._networth_service  # noqa: SLF001
                    self.characters_tab._fuzzwork_provider = self._fuzzwork_provider  # noqa: SLF001

                # Update the AssetsTab with the fuzzwork_provider
                if hasattr(self, "assets_tab") and self.assets_tab:
                    self.assets_tab._fuzzwork = self._fuzzwork_provider  # noqa: SLF001
                    try:
                        # Reprice assets now that market data is available
                        if hasattr(self.assets_tab, "on_fuzzwork_ready"):
                            self.assets_tab.on_fuzzwork_ready()
                    except Exception:
                        logger.debug(
                            "Failed to notify assets tab of fuzzwork readiness",
                            exc_info=True,
                        )

                # Replace networth placeholder with real tab
                if (
                    hasattr(self, "_networth_placeholder")
                    and self._networth_placeholder
                ):
                    networth_idx = self.tab_widget.indexOf(self._networth_placeholder)
                    if networth_idx >= 0:
                        self.tab_widget.removeTab(networth_idx)
                        self.networth_tab = NetworthTab(
                            networth_service=self._networth_service,
                            character_service=self._character_service,
                            esi_client=self._esi_client,
                        )
                        self.tab_widget.insertTab(
                            networth_idx, self.networth_tab, "Net Worth"
                        )
                        self._networth_placeholder = None

                self._fuzzwork_ready = True
                if hasattr(self, "_progress_widget"):
                    self._progress_widget.complete("Market data ready")
                logger.info("Fuzzwork provider initialized successfully")
            else:
                if hasattr(self, "_progress_widget"):
                    self._progress_widget.complete(
                        "Market data unavailable - some features limited"
                    )
                logger.warning("Fuzzwork CSV was empty or unavailable")

        except Exception as e:
            logger.error("Failed to initialize fuzzwork: %s", e, exc_info=True)
            if hasattr(self, "_progress_widget"):
                self._progress_widget.complete("Market data initialization failed")

    def _setup_ui(self) -> None:
        """Setup user interface."""
        # Create menu bar
        self._create_menu_bar()

        # Create central widget with layout for tabs (progress moved to status bar)
        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Create tab widget
        self.tab_widget = QTabWidget()
        central_layout.addWidget(self.tab_widget)

        # Disable tabs initially (will be enabled after SDE init)
        self.tab_widget.setEnabled(False)

        self.setCentralWidget(central_widget)

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
        tab_name = (
            self._settings.get_ui_settings("characters_tab").column_order[0]
            if "characters_tab" in self._settings._settings.ui  # noqa: SLF001
            and self._settings.get_ui_settings("characters_tab").column_order
            else "Characters"
        )
        self.tab_widget.addTab(self.characters_tab, tab_name)

        # Create assets tab
        self.assets_tab = AssetsTab(
            character_service=self._character_service,
            esi_client=self._esi_client,
            asset_service=self._asset_service,
            location_service=self._location_service,
            fuzzwork_provider=self._fuzzwork_provider,
        )
        self.tab_widget.addTab(self.assets_tab, "Assets")

        # Create journal tab
        self.journal_tab = JournalTab(
            wallet_service=self._wallet_service,
            character_service=self._character_service,
            sde_provider=self._sde_provider,
        )
        self.tab_widget.addTab(self.journal_tab, "Journal")

        # Create transactions tab
        self.transactions_tab = TransactionsTab(
            wallet_service=self._wallet_service,
            location_service=self._location_service,
            sde_provider=self._sde_provider,
        )
        self.tab_widget.addTab(self.transactions_tab, "Transactions")

        # Create industry jobs tab
        self.industry_jobs_tab = IndustryJobsTab(
            industry_service=self._industry_service,
            character_service=self._character_service,
            location_service=self._location_service,
            sde_provider=self._sde_provider,
        )
        self.tab_widget.addTab(self.industry_jobs_tab, "Industry Jobs")

        # Create asset tree tab
        self.asset_tree_tab = AssetTreeTab(
            character_service=self._character_service,
            asset_service=self._asset_service,
            location_service=self._location_service,
        )
        self.tab_widget.addTab(self.asset_tree_tab, "Asset Tree")

        # Create industry slots tab
        self.industry_slots_tab = IndustrySlotsTab(
            character_service=self._character_service,
            industry_service=self._industry_service,
            esi_client=self._esi_client,
        )
        self.tab_widget.addTab(self.industry_slots_tab, "Industry Slots")

        # Create stockpiles tab
        self.stockpiles_tab = StockpilesTab(
            asset_service=self._asset_service,
        )
        self.tab_widget.addTab(self.stockpiles_tab, "Stockpiles")

        # Create net worth tab (placeholder until fuzzwork is ready)
        # Will be replaced when NetWorthService is initialized
        self.networth_tab: NetworthTab | None = None
        self._networth_placeholder = QWidget()
        placeholder_layout = QVBoxLayout(self._networth_placeholder)
        placeholder_label = QLabel("Loading market data...")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_layout.addWidget(placeholder_label)
        self.tab_widget.addTab(self._networth_placeholder, "Net Worth")

        # Create status bar with progress widget
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Create progress widget (hidden by default, placed in status bar)
        self._progress_widget = ProgressWidget()
        self._progress_widget.cancel_clicked.connect(self._on_progress_cancel)
        self.status_bar.addPermanentWidget(self._progress_widget, stretch=1)

        # Add status label on the right
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

        # Add Preferences menu item
        preferences_action = QAction("&Preferences...", self)
        preferences_action.setShortcut("Ctrl+,")
        preferences_action.triggered.connect(self._on_preferences)
        file_menu.addAction(preferences_action)

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

        # Connect global progress signals
        self._signal_bus.progress_start.connect(self._on_progress_start)
        self._signal_bus.progress_update.connect(self._on_progress_update)
        self._signal_bus.progress_complete.connect(self._on_progress_complete)
        self._signal_bus.progress_error.connect(self._on_progress_error)
        self._signal_bus.progress_cancel_requested.connect(self._on_progress_cancel)

    def _on_progress_cancel(self) -> None:
        """Handle progress widget cancel button click."""
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        self._progress_widget.complete("Cancelled")
        logger.info("Background operation cancelled by user")

    def _on_sde_progress(self, update: ProgressUpdate) -> None:
        """Handle SDE progress updates.

        Args:
            update: Progress update from SDE client/provider
        """
        if hasattr(self, "_progress_widget"):
            message = update.message
            if update.detail:
                message = f"{update.message} - {update.detail}"

            # Initialize progress widget only on STARTING phase
            if update.phase == ProgressPhase.STARTING:
                total = int(update.total) if update.total > 0 else 100
                self._progress_widget.start_operation(message, total=total)
            elif update.phase == ProgressPhase.COMPLETE:
                self._progress_widget.complete(message)
            elif update.phase == ProgressPhase.ERROR:
                self._progress_widget.error(message)
            else:
                # FETCHING, PROCESSING, SAVING phases - update progress
                # Ensure current is an integer for setValue()
                current_value = int(update.current)
                self._progress_widget.update_progress(current_value, message)

    def _on_add_character(self) -> None:
        """Handle add character action."""
        dialog = AuthDialog(self._character_service, self)
        dialog.exec()

    def _on_remove_character(self) -> None:
        """Handle remove character action."""
        self._signal_bus.info_message.emit(
            "Please right-click a character in the list to remove them"
        )

    def _on_preferences(self) -> None:
        """Show preferences dialog."""
        dialog = PreferencesDialog(self._settings, self)
        dialog.exec()
        logger.info("Preferences dialog closed")

    def _on_about(self) -> None:
        """Show about dialog."""
        about_text = f"""
        <h2>{global_config.app.name}</h2>
        <p>Version {global_config.app.version}</p>
        <p>A fully featured EVE Online tool for asset tracking, manufacturing and trading analysis.</p>

        <p><b>Contact & Community:</b></p>
        """
        # Discord invite at the top
        if global_config.app.contact_discord_invite:
            about_text += f"<p>• Join our <a href='{global_config.app.contact_discord_invite}'>Discord community</a> for support, updates, and discussion!</p>"
        if global_config.app.contact_github:
            about_text += f"<p>• Project on <a href='{global_config.app.contact_github}'>GitHub</a></p>"
        if global_config.app.contact_discord:
            about_text += f"<p>• Discord: {global_config.app.contact_discord}</p>"
        if global_config.app.contact_eve:
            about_text += f"<p>• EVE: {global_config.app.contact_eve}</p>"

        about_text += """
        <hr>
        <p style='font-size:1.1em;'>
        <b>How you can help:</b><br>
        Donations and referrals help keep this project alive and free for everyone.<br>
        Your support covers development time, and enables new features.<br>
        Do you have coding skills? Contributions and pointers are welcome on GitHub!
        </p>
        """

        # Referral links/codes and ISK donation section
        referrals = global_config.app.referrals
        creator_name = global_config.app.contact_eve or "Tyron Denker"
        if referrals or creator_name:
            about_text += "<p><b>Support & Referral Options:</b></p>"
            # Compact Markee Dragon affiliate links and codes into a single item
            markee_link = referrals.get("markee_link")
            markee_code_1 = referrals.get("markee_code_1")
            markee_code_2 = referrals.get("markee_code_2")
            eve_referral = referrals.get("eve_referral")
            # Markee Dragon affiliate
            if markee_link:
                codes = []
                if markee_code_1:
                    codes.append(f"<b>{markee_code_1}</b>")
                if markee_code_2:
                    codes.append(f"<b>{markee_code_2}</b>")
                codes_str = " or ".join(codes) if codes else ""
                about_text += f"<p>• Shop at <a href='{markee_link}'>Markee Dragon Store</a> (affiliate, 3% discount with code {codes_str})</p>"
            # EVE referral
            if eve_referral:
                about_text += f"<p>• Sign up for EVE Online with <a href='{eve_referral}'>this referral link</a> for an extra 1M skill points.</p>"
            # Add ISK donation option in the same list
            if creator_name:
                about_text += f"<p>• <b>Support the creator in-game!</b> ISK Donations are more than welcome to <b>{creator_name}</b> in EVE Online. </p>"

        about_text += """
        <hr><p>EVE Means of Profit is and always will be free and open source.<br>
        Thank you for considering supporting this endeavour!</p>
        """

        # Show as rich text with clickable links
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About")
        msg_box.setTextFormat(Qt.TextFormat.RichText)
        msg_box.setText(about_text)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setStyleSheet(":link { color: #2980b9; } :visited { color: #8e44ad; }")
        msg_box.exec()

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

    def _on_progress_start(self, title: str, total: int) -> None:
        """Handle global progress start signal.

        Args:
            title: Operation title
            total: Total progress steps
        """
        self._progress_widget.start_operation(title, total)

    def _on_progress_update(self, current: int, message: str) -> None:
        """Handle global progress update signal.

        Args:
            current: Current progress value
            message: Status message
        """
        self._progress_widget.update_progress(current, message)

    def _on_progress_complete(self, message: str) -> None:
        """Handle global progress complete signal.

        Args:
            message: Completion message
        """
        self._progress_widget.complete(message)

    def _on_progress_error(self, message: str) -> None:
        """Handle global progress error signal.

        Args:
            message: Error message
        """
        self._progress_widget.error(message)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Handle window close event (Qt method override).

        Args:
            event: Close event
        """
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()

        # Schedule async cleanup
        async def cleanup():
            try:
                await self._character_service.close()
                await self._esi_client.close()
                if self._fuzzwork_client:
                    await self._fuzzwork_client.close()
            except Exception as e:
                logger.error("Error during cleanup: %s", e)

        # Run cleanup in the event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            task = asyncio.ensure_future(cleanup())
            self._background_tasks.add(task)
            task.add_done_callback(lambda t: self._background_tasks.discard(t))
        else:
            loop.run_until_complete(cleanup())

        event.accept()


def main_window() -> int:
    """Main entry point for the application.

    Returns:
        Exit code
    """
    # Setup logging with file rotation
    settings_manager = get_settings_manager()
    setup_logging(settings_manager=settings_manager)

    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("qasync").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(global_config.app.name)
    app.setApplicationVersion(global_config.app.version)

    # Apply dark theme globally
    apply_dark_theme(app)

    # Setup async event loop
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Schedule async initialization after window is shown
    QTimer.singleShot(0, window.initialize_async)

    # Run event loop
    with loop:
        return loop.run_forever()
