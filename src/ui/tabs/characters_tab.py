"""Characters tab with update timers and refresh functionality."""

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from data.clients import ESIClient
from models.app.character_info import CharacterInfo
from services.asset_service import AssetService
from services.character_service import CharacterService
from services.contract_service import ContractService
from services.industry_service import IndustryService
from services.market_service import MarketService
from services.networth_service import NetWorthService
from services.wallet_service import WalletService
from ui.signal_bus import get_signal_bus
from ui.styles import COLORS, AppStyles
from ui.widgets import CharacterItemWidget
from ui.widgets.account_group_widget import AccountGroupWidget, EmptyAccountWidget
from ui.widgets.flow_layout import FlowLayout
from utils.progress_callback import (
    CancelToken,
)
from utils.settings_manager import get_settings_manager

if TYPE_CHECKING:
    from data import FuzzworkProvider

logger = logging.getLogger(__name__)


class CharactersTab(QWidget):
    """Tab displaying characters with update timers and refresh functionality."""

    def __init__(
        self,
        esi_client: ESIClient,
        character_service: CharacterService,
        asset_service: AssetService,
        wallet_service: WalletService,
        market_service: MarketService,
        contract_service: ContractService,
        industry_service: IndustryService,
        networth_service: NetWorthService | None = None,
        fuzzwork_provider: "FuzzworkProvider | None" = None,
        parent=None,
    ):
        """Initialize characters tab.

        Args:
            character_service: Service for character operations
            esi_client: ESI client for cache info
            asset_service: Service for asset operations
            wallet_service: Service for wallet operations
            market_service: Service for market operations
            contract_service: Service for contract operations
            industry_service: Service for industry operations
            networth_service: Service for networth operations
            fuzzwork_provider: Provider for market data
            parent: Parent widget
        """
        super().__init__(parent)
        self._character_service = character_service
        self._esi_client = esi_client
        self._asset_service = asset_service
        self._wallet_service = wallet_service
        self._market_service = market_service
        self._contract_service = contract_service
        self._industry_service = industry_service
        self._networth_service = networth_service
        self._fuzzwork_provider = fuzzwork_provider
        self._settings = get_settings_manager()
        self._signal_bus = get_signal_bus()
        self._background_tasks: set[asyncio.Task] = set()
        self._selected_character_id: int | None = None
        self._pending_account_layout_refresh: bool = False

        # Cancellation token for refresh operations
        self._cancel_token: CancelToken | None = None
        self._refresh_in_progress: bool = False

        # Cache endpoint timers across widget recreations (persists when switching tabs)
        self._endpoint_timer_cache: dict[int, dict[str, float | None]] = {}

        self._timers_checkbox_prev_state = True  # Remember last state for timers toggle
        self._setup_ui()
        self._connect_signals()
        # Cache of last loaded characters for refresh after drag/drop
        self._last_loaded_characters: list[CharacterInfo] = []

    def _setup_ui(self) -> None:
        """Setup user interface."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Left side: Character list and controls
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(5)

        # Top buttons row with modern styling
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)

        self.add_character_btn = QPushButton("+ Character")
        self.add_character_btn.setMinimumHeight(32)
        self.add_character_btn.setMaximumWidth(120)
        self.add_character_btn.setStyleSheet(AppStyles.BUTTON_PRIMARY)
        self.add_character_btn.clicked.connect(self._on_add_character_clicked)
        buttons_row.addWidget(self.add_character_btn)

        self.new_account_btn = QPushButton("+ Account")
        self.new_account_btn.setMinimumHeight(32)
        self.new_account_btn.setMaximumWidth(120)
        self.new_account_btn.setStyleSheet(AppStyles.BUTTON_SECONDARY)
        self.new_account_btn.clicked.connect(self._on_new_account_clicked)
        buttons_row.addWidget(self.new_account_btn)

        # Global refresh button
        self.refresh_all_btn = QPushButton("↻ Refresh All")
        self.refresh_all_btn.setMinimumHeight(32)
        self.refresh_all_btn.setMaximumWidth(120)
        self.refresh_all_btn.setToolTip(
            "Refresh all characters and save fresh networth snapshots"
        )
        self.refresh_all_btn.setStyleSheet(AppStyles.BUTTON_WARNING)
        self.refresh_all_btn.clicked.connect(self._on_refresh_all_characters)
        buttons_row.addWidget(self.refresh_all_btn)

        buttons_row.addStretch()
        left_layout.addLayout(buttons_row)

        # View controls row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(12)

        self.timers_checkbox = QCheckBox("Show endpoint timers")
        # Restore saved state from settings
        self.timers_checkbox.setChecked(self._settings.get_show_endpoint_timers())
        self.timers_checkbox.setStyleSheet(AppStyles.CHECKBOX)
        self.timers_checkbox.stateChanged.connect(self._on_timers_toggle)
        controls_row.addWidget(self.timers_checkbox)

        self.listview_checkbox = QCheckBox("List view")
        # Restore saved state from settings
        self.listview_checkbox.setChecked(self._settings.get_list_view_enabled())
        self.listview_checkbox.setStyleSheet(AppStyles.CHECKBOX)
        self.listview_checkbox.stateChanged.connect(self._on_listview_toggle)
        controls_row.addWidget(self.listview_checkbox)

        controls_row.addStretch()
        left_layout.addLayout(controls_row)

        # Card view: Scroll area for account groups
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setStyleSheet(
            f"QScrollArea {{ background-color: {COLORS.BG_DARK}; }}"
            + AppStyles.SCROLLBAR
        )
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Main scroll content container
        self.scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(self.scroll_content)
        scroll_content_layout.setContentsMargins(0, 0, 0, 0)
        scroll_content_layout.setSpacing(8)

        # Container widget for account groups with characters
        self.accounts_container = QWidget()
        self.accounts_container.installEventFilter(self)
        self.accounts_layout = FlowLayout(self.accounts_container)
        self.accounts_layout.setContentsMargins(4, 4, 4, 4)
        self.accounts_layout.setHorizontalSpacing(8)
        self.accounts_layout.setVerticalSpacing(8)
        scroll_content_layout.addWidget(self.accounts_container)

        # Container for empty accounts (compact stacked display)
        self.empty_accounts_container = QWidget()
        self.empty_accounts_layout = QVBoxLayout(self.empty_accounts_container)
        self.empty_accounts_layout.setContentsMargins(4, 0, 4, 4)
        self.empty_accounts_layout.setSpacing(4)

        # Header for empty accounts section
        self.empty_accounts_header = QLabel("Empty Accounts (drop characters here)")
        self.empty_accounts_header.setStyleSheet(
            f"font-size: 11px; color: {COLORS.TEXT_DISABLED}; padding: 4px 0;"
        )
        self.empty_accounts_header.hide()
        self.empty_accounts_layout.addWidget(self.empty_accounts_header)

        # Flow-style layout for compact empty accounts
        self.empty_accounts_flow = QWidget()
        self.empty_accounts_flow_layout = QGridLayout(self.empty_accounts_flow)
        self.empty_accounts_flow_layout.setContentsMargins(0, 0, 0, 0)
        self.empty_accounts_flow_layout.setHorizontalSpacing(6)
        self.empty_accounts_flow_layout.setVerticalSpacing(4)
        self.empty_accounts_layout.addWidget(self.empty_accounts_flow)

        scroll_content_layout.addWidget(self.empty_accounts_container)
        scroll_content_layout.addStretch()

        self.scroll_area.setWidget(self.scroll_content)
        left_layout.addWidget(self.scroll_area)

        # List view: Table widget (hidden by default)
        self.list_table = QTableWidget()
        self.list_table.setColumnCount(12)
        self.list_table.setHorizontalHeaderLabels(
            [
                "Name",
                "Account",
                "Corporation",
                "Alliance",
                "Wallet",
                "Assets",
                "Escrow",
                "Sell Orders",
                "Contracts",
                "Collateral",
                "Industry",
                "Net Worth",
            ]
        )
        self.list_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.list_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.list_table.setAlternatingRowColors(True)
        self.list_table.setStyleSheet(AppStyles.TABLE + AppStyles.SCROLLBAR)
        # Make columns stretch to fill available space
        header = self.list_table.horizontalHeader()
        if header is not None:
            # Text columns stretch; numeric columns size to contents
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Name
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Account
            header.setSectionResizeMode(
                2, QHeaderView.ResizeMode.Stretch
            )  # Corporation
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Alliance
            for i in range(4, 12):  # Numeric columns
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        v_header = self.list_table.verticalHeader()
        if v_header is not None:
            v_header.setVisible(False)
        self.list_table.hide()
        left_layout.addWidget(self.list_table)

        # Track account group widgets (both full and empty)
        self.account_groups: dict[
            int | None, AccountGroupWidget | EmptyAccountWidget
        ] = {}
        self._account_group_widgets: list[AccountGroupWidget] = []
        self._empty_account_widgets: list[EmptyAccountWidget] = []
        self._account_columns: int = 1

        # Add left widget directly to main layout (no splitter/side panel)
        main_layout.addWidget(left_widget)

        # Endpoint timers are now in the networth tab
        # Endpoint timers moved to networth tab - no longer needed here
        # self.endpoint_timers: dict[str, EndpointTimer] = {}
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        # self.update_button: Removed (no longer used)
        # self.update_all_characters_button: Removed (no longer used)

    @asyncSlot()
    async def _on_update_all_characters(self) -> None:
        """Update all endpoints for all characters using parallel updates."""
        # Delegate to the parallel refresh implementation
        await self._on_refresh_all_characters()

    @asyncSlot(int)
    async def _on_refresh_character(self, character_id: int) -> None:
        """Refresh a single character's data using parallel endpoint updates.

        Single character refreshes do NOT create snapshot groups - they are lightweight
        updates that don't affect the networth graph.
        """
        # Create a cancel token for this operation
        self._cancel_token = CancelToken()
        self._refresh_in_progress = True

        try:
            # Get character name for display
            char_name = self._get_character_name(character_id)

            self._signal_bus.status_message.emit(f"Refreshing character {char_name}...")

            # Single character refreshes do NOT create snapshot groups
            snapshot_group_id = None

            # Run parallel endpoint updates
            results = await self._refresh_character_endpoints_parallel(
                character_id, char_name
            )

            # Check if cancelled
            if self._cancel_token and self._cancel_token.is_cancelled:
                self._signal_bus.status_message.emit("Refresh cancelled")
                return

            # Count successes and failures
            successes = sum(1 for r in results if r is True)
            failures = sum(1 for r in results if isinstance(r, Exception))

            # Persist networth snapshot without group ID
            if self._networth_service is not None:
                try:
                    await self._networth_service.save_networth_snapshot(
                        character_id, snapshot_group_id
                    )
                except Exception:
                    logger.debug(
                        "Failed to snapshot networth after refresh for %s",
                        character_id,
                        exc_info=True,
                    )

                char_widget = self._find_character_widget(character_id)
                if char_widget:
                    character = next(
                        (
                            c
                            for c in self._last_loaded_characters
                            if getattr(c, "character_id", 0) == character_id
                        ),
                        None,
                    )
                    if character:
                        await self._load_networth(character, char_widget)
                        # Publish endpoint timers now that endpoints have been fetched
                        self._publish_endpoint_timers(character_id)

            if failures > 0:
                self._signal_bus.status_message.emit(
                    f"{char_name}: {successes}/6 endpoints refreshed ({failures} failed)"
                )
            else:
                self._signal_bus.status_message.emit(
                    f"{char_name} refreshed successfully!"
                )

            # Broadcast updated characters so other tabs (assets/networth) refresh
            try:
                characters_for_signal = list(self._last_loaded_characters)
                if not characters_for_signal:
                    try:
                        characters_for_signal = (
                            await self._character_service.get_authenticated_characters()
                        )
                    except Exception:
                        characters_for_signal = []
                if characters_for_signal:
                    self._signal_bus.characters_loaded.emit(characters_for_signal)
            except Exception:
                logger.debug(
                    "Failed to broadcast characters_loaded after single refresh",
                    exc_info=True,
                )
        except Exception:
            logger.exception(f"Failed to refresh character {character_id}")
            self._signal_bus.error_occurred.emit(
                f"Failed to refresh character {character_id}"
            )
        finally:
            self._refresh_in_progress = False
            self._cancel_token = None
            self._request_account_relayout()

    async def _refresh_fuzzwork_data(self) -> bool:
        """Explicitly refresh Fuzzwork market data.

        This implements REQ-005 (Fuzzwork update gating): Updates occur only on
        explicit user-initiated refresh requests.

        Returns:
            True if refresh was successful or data was already current, False otherwise.
        """
        if self._fuzzwork_provider is None:
            logger.debug(
                "Fuzzwork provider not initialized, skipping market data refresh"
            )
            return False

        try:
            from data.clients import FuzzworkClient
            from data.parsers.fuzzwork_csv import FuzzworkCSVParser

            # Get the fuzzwork client (assume it's available via main window or create one)
            # For now, create a client instance to fetch data
            from utils.config import get_config

            config = get_config()
            cache_dir = config.app.user_data_dir / "fuzzwork"

            client = FuzzworkClient(cache_dir=cache_dir)

            self._signal_bus.status_message.emit("Checking for market data updates...")

            # Force check for updates (will download if ETag differs)
            csv_text = await client.fetch_aggregate_csv(
                force=False, check_etag=True, progress_callback=None
            )

            if csv_text:
                # Reload the provider with fresh data
                parser = FuzzworkCSVParser(csv_text)
                from data import FuzzworkProvider

                self._fuzzwork_provider = FuzzworkProvider(parser)

                # Also update networth service's provider reference if available
                if self._networth_service:
                    self._networth_service._fuzzwork = self._fuzzwork_provider

                logger.info("Fuzzwork market data refreshed successfully")
                self._signal_bus.status_message.emit("Market data updated")
                return True
            logger.debug("No Fuzzwork data available")
            return False

        except Exception:
            logger.debug("Failed to refresh Fuzzwork data", exc_info=True)
            return False

    async def _refresh_character_endpoints_parallel(
        self, character_id: int, char_name: str
    ) -> list[bool | BaseException]:
        """Run all endpoint updates in parallel for a character.

        Args:
            character_id: Character ID to refresh
            char_name: Character name for display

        Returns:
            List of results - True for success, BaseException for failure
        """
        endpoints = [
            ("assets", self._update_assets),
            ("wallet_journal", self._update_wallet_journal),
            ("wallet_transactions", self._update_wallet_transactions),
            ("market_orders", self._update_market_orders),
            ("contracts", self._update_contracts),
            ("industry_jobs", self._update_industry_jobs),
        ]

        total_endpoints = len(endpoints)
        completed = [0]  # Use list to allow mutation in nested function

        # Start progress widget via signal bus
        self._signal_bus.progress_start.emit(f"Refreshing {char_name}", total_endpoints)

        async def run_endpoint(name: str, func) -> bool | Exception:
            """Run a single endpoint (ESI client handles rate limiting)."""
            if self._cancel_token and self._cancel_token.is_cancelled:
                return Exception("Cancelled")

            try:
                # ESI client handles rate limiting internally via RateLimitTracker
                if self._cancel_token and self._cancel_token.is_cancelled:
                    return Exception("Cancelled")
                await func(character_id)

                # Update progress
                completed[0] += 1
                self._signal_bus.progress_update.emit(
                    completed[0],
                    f"Fetching {char_name} ({completed[0]}/{total_endpoints} endpoints)",
                )
                return True
            except Exception as e:
                logger.exception(
                    f"Failed to update {name} for character {character_id}"
                )
                completed[0] += 1
                self._signal_bus.progress_update.emit(
                    completed[0],
                    f"Fetching {char_name} ({completed[0]}/{total_endpoints} endpoints)",
                )
                return e

        try:
            results = await asyncio.gather(
                *[run_endpoint(name, func) for name, func in endpoints],
                return_exceptions=True,
            )

            # Complete progress
            failures = sum(1 for r in results if isinstance(r, Exception))
            if failures > 0:
                self._signal_bus.progress_complete.emit(
                    f"{char_name}: {total_endpoints - failures}/{total_endpoints} succeeded"
                )
            else:
                self._signal_bus.progress_complete.emit(f"{char_name} refreshed!")

            # Publish endpoint timers now that endpoints have been fetched
            # This allows the UI to show cache expiry indicators for this character
            self._publish_endpoint_timers(character_id)

            return list(results)
        except Exception:
            self._signal_bus.progress_error.emit(f"Failed to refresh {char_name}")
            raise

    def _get_character_name(self, character_id: int) -> str:
        """Get character name from ID."""
        for char in self._last_loaded_characters:
            if getattr(char, "character_id", 0) == character_id:
                return getattr(char, "name", f"Character {character_id}")
        return f"Character {character_id}"

    def _on_cancel_refresh(self) -> None:
        """Handle cancel button click from progress widget via signal bus."""
        if self._cancel_token:
            self._cancel_token.cancel()
            self._signal_bus.status_message.emit("Cancelling refresh operation...")

    @asyncSlot(object)
    async def _on_refresh_account(self, account_id: int | None) -> None:
        """Refresh all characters in an account with parallel endpoint updates."""
        # Create a cancel token for this operation
        self._cancel_token = CancelToken()
        self._refresh_in_progress = True

        try:
            # Step 1: Refresh Fuzzwork market data (explicit user request)
            await self._refresh_fuzzwork_data()

            # Get all character IDs for this account
            character_ids = []
            for card in self._get_account_character_cards(account_id):
                character_ids.append(card.character_id)

            if not character_ids:
                self._signal_bus.info_message.emit("No characters in this account.")
                return

            # Get account name from settings or use fallback
            account_name = "Unassigned"
            if account_id is not None:
                if hasattr(self._settings, "get_account_name"):
                    account_name = (
                        self._settings.get_account_name(account_id)
                        or f"Account {account_id}"
                    )
                else:
                    account_name = f"Account {account_id}"

            total_chars = len(character_ids)
            self._signal_bus.status_message.emit(
                f"Refreshing {total_chars} characters in {account_name}..."
            )

            # Start overall progress via signal bus
            self._signal_bus.progress_start.emit(
                f"Refreshing {account_name}", total_chars * 6
            )

            # Create snapshot group for the account
            snapshot_group_id = None
            if self._networth_service is not None:
                try:
                    snapshot_group_id = (
                        await self._networth_service.create_snapshot_group(
                            account_id,
                            refresh_source="account",
                            label="Account refresh",
                        )
                    )
                    # Create PLEX snapshots for the account
                    if snapshot_group_id and account_id:
                        logger.debug(
                            "Account Refresh: Creating PLEX snapshot for account %d",
                            account_id,
                        )
                        await self._create_account_plex_snapshots(
                            [account_id], snapshot_group_id
                        )
                except Exception:
                    logger.debug(
                        "Unable to create snapshot group for account %s",
                        account_id,
                        exc_info=True,
                    )

            completed_endpoints = 0
            total_successes = 0
            total_failures = 0

            # Refresh each character with parallel endpoints
            for idx, character_id in enumerate(character_ids):
                # Check for cancellation
                if self._cancel_token and self._cancel_token.is_cancelled:
                    self._signal_bus.status_message.emit("Refresh cancelled")
                    return

                char_name = self._get_character_name(character_id)

                # snapshot_group_id already created

                # Run parallel endpoint updates
                results = await self._refresh_character_endpoints_parallel_batch(
                    character_id, char_name, idx + 1, total_chars, completed_endpoints
                )

                # Count results
                char_successes = sum(1 for r in results if r is True)
                char_failures = sum(1 for r in results if isinstance(r, Exception))
                total_successes += char_successes
                total_failures += char_failures
                completed_endpoints += len(results)

                # Save networth snapshot
                if self._networth_service is not None:
                    try:
                        await self._networth_service.save_networth_snapshot(
                            character_id, snapshot_group_id
                        )
                    except Exception:
                        logger.debug(
                            "Failed to snapshot networth after refresh for %s",
                            character_id,
                            exc_info=True,
                        )

                # Update character widget
                char_widget = self._find_character_widget(character_id)
                if char_widget:
                    character = next(
                        (
                            c
                            for c in self._last_loaded_characters
                            if getattr(c, "character_id", 0) == character_id
                        ),
                        None,
                    )
                    if character:
                        await self._load_networth(character, char_widget)
                        # Publish endpoint timers now that endpoints have been fetched
                        self._publish_endpoint_timers(character_id)

            # Complete progress via signal bus
            if total_failures > 0:
                self._signal_bus.progress_complete.emit(
                    f"{account_name}: {total_failures} endpoint failures"
                )
                self._signal_bus.status_message.emit(
                    f"{account_name} refreshed with {total_failures} failures"
                )
            else:
                self._signal_bus.progress_complete.emit(f"{account_name} refreshed!")
                self._signal_bus.status_message.emit(
                    f"{account_name} refreshed successfully!"
                )

            # Broadcast updated characters
            try:
                characters_for_signal = list(self._last_loaded_characters)
                if characters_for_signal:
                    self._signal_bus.characters_loaded.emit(characters_for_signal)
            except Exception:
                logger.debug(
                    "Failed to broadcast characters_loaded after account refresh",
                    exc_info=True,
                )

        except Exception:
            logger.exception(f"Failed to refresh account {account_id}")
            self._signal_bus.progress_error.emit("Failed to refresh account")
            self._signal_bus.error_occurred.emit("Failed to refresh account")
        finally:
            self._refresh_in_progress = False
            self._cancel_token = None
            self._request_account_relayout()

    @asyncSlot()
    async def _on_refresh_all_characters(self) -> None:
        """Refresh all characters across all accounts with parallel endpoint updates."""
        # Create a cancel token for this operation
        self._cancel_token = CancelToken()
        self._refresh_in_progress = True

        try:
            # Step 1: Refresh Fuzzwork market data (explicit user request)
            await self._refresh_fuzzwork_data()

            character_ids = [
                getattr(ch, "character_id", 0)
                for ch in self._last_loaded_characters
                if getattr(ch, "character_id", 0)
            ]

            if not character_ids:
                self._signal_bus.info_message.emit("No characters to refresh.")
                return

            total_chars = len(character_ids)
            self._signal_bus.status_message.emit(
                f"Refreshing all {total_chars} characters..."
            )

            # Start overall progress via signal bus
            self._signal_bus.progress_start.emit(
                f"Refreshing {total_chars} characters", total_chars * 6
            )

            # Create snapshot group for all characters
            snapshot_group_id = None
            if self._networth_service is not None:
                try:
                    snapshot_group_id = (
                        await self._networth_service.create_snapshot_group(
                            None, refresh_source="refresh_all", label="Refresh all"
                        )
                    )
                    # Create PLEX snapshots for all affected accounts
                    if snapshot_group_id:
                        account_ids = set()
                        for character_id in character_ids:
                            if hasattr(self._settings, "get_account_for_character"):
                                account_id = self._settings.get_account_for_character(
                                    character_id
                                )
                                if account_id:
                                    account_ids.add(account_id)

                        # Also check for accounts with PLEX but no assigned characters
                        if hasattr(self._settings, "get_accounts"):
                            all_accounts = self._settings.get_accounts()
                            for acc_id, acc_data in all_accounts.items():
                                plex_units = acc_data.get("plex_units", 0)
                                if plex_units > 0:
                                    account_ids.add(acc_id)

                        logger.debug(
                            "Refresh All: Creating PLEX snapshots for accounts: %s",
                            list(account_ids),
                        )

                        if account_ids:
                            await self._create_account_plex_snapshots(
                                list(account_ids), snapshot_group_id
                            )
                        else:
                            logger.debug("No accounts found for PLEX snapshot creation")
                except Exception:
                    logger.debug(
                        "Unable to create snapshot group for refresh all",
                        exc_info=True,
                    )

            completed_endpoints = 0
            total_successes = 0
            total_failures = 0

            # Create semaphore for bounded concurrency (max 3 concurrent characters)
            semaphore = asyncio.Semaphore(3)
            completed_characters = [0]  # Track progress

            async def refresh_single_character(idx: int, character_id: int):
                """Refresh a single character with semaphore-based rate limiting."""
                async with semaphore:
                    if self._cancel_token and self._cancel_token.is_cancelled:
                        return None, []

                    char_name = self._get_character_name(character_id)

                    # Run parallel endpoint updates for this character
                    results = await self._refresh_character_endpoints_parallel_batch(
                        character_id,
                        char_name,
                        idx + 1,
                        total_chars,
                        completed_characters[0],
                    )

                    # Update completed endpoints count
                    completed_characters[0] += len(results)

                    # Save networth snapshot
                    if self._networth_service is not None:
                        try:
                            await self._networth_service.save_networth_snapshot(
                                character_id, snapshot_group_id
                            )
                        except Exception:
                            logger.debug(
                                "Failed to snapshot networth after refresh for %s",
                                character_id,
                                exc_info=True,
                            )

                    # Update character widget (schedule networth update as separate task)
                    char_widget = self._find_character_widget(character_id)
                    if char_widget:
                        character = next(
                            (
                                c
                                for c in self._last_loaded_characters
                                if getattr(c, "character_id", 0) == character_id
                            ),
                            None,
                        )
                        if character and self._networth_service:
                            # Schedule networth load as independent task to avoid nesting issues
                            async def update_widget_networth():
                                try:
                                    latest = await self._networth_service.get_latest_networth(
                                        character_id
                                    )
                                    if char_widget and not char_widget.isHidden():
                                        existing_timers = (
                                            char_widget._endpoint_timers.copy()
                                            if hasattr(char_widget, "_endpoint_timers")
                                            else {}
                                        )
                                        char_widget.set_networth(latest)
                                        if (
                                            existing_timers
                                            and char_widget._endpoint_timers
                                            != existing_timers
                                        ):
                                            char_widget.set_endpoint_timers(
                                                existing_timers
                                            )
                                        char_widget._networth_snapshot = latest
                                        char_widget.set_networth_visible(True)
                                except Exception:
                                    logger.debug(
                                        "Failed to update networth for character %s",
                                        character_id,
                                        exc_info=True,
                                    )

                            asyncio.create_task(update_widget_networth())

                            # Publish endpoint timers now that endpoints have been fetched
                            self._publish_endpoint_timers(character_id)

                    return character_id, results

            # Run all characters concurrently with semaphore limiting concurrency
            tasks = [
                refresh_single_character(idx, char_id)
                for idx, char_id in enumerate(character_ids)
            ]
            all_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Count successes and failures from all results
            for result in all_results:
                if isinstance(result, Exception):
                    total_failures += 6  # All endpoints failed for this character
                    logger.error("Character refresh failed completely: %s", result)
                elif result is not None:
                    char_id, endpoint_results = result
                    char_successes = sum(1 for r in endpoint_results if r is True)
                    char_failures = sum(
                        1 for r in endpoint_results if isinstance(r, Exception)
                    )
                    total_successes += char_successes
                    total_failures += char_failures

            # Complete progress via signal bus
            if total_failures > 0:
                self._signal_bus.progress_complete.emit(
                    f"Refreshed {total_chars} characters ({total_failures} endpoint failures)"
                )
                self._signal_bus.status_message.emit(
                    f"All characters refreshed with {total_failures} failures"
                )
            else:
                self._signal_bus.progress_complete.emit(
                    f"All {total_chars} characters refreshed!"
                )
                self._signal_bus.status_message.emit(
                    "All characters refreshed successfully!"
                )

            # Broadcast updated characters
            try:
                characters_for_signal = list(self._last_loaded_characters)
                if characters_for_signal:
                    self._signal_bus.characters_loaded.emit(characters_for_signal)
            except Exception:
                logger.debug(
                    "Failed to broadcast characters_loaded after refresh all",
                    exc_info=True,
                )

        except Exception:
            logger.exception("Failed to refresh all characters")
            self._signal_bus.progress_error.emit("Failed to refresh all characters")
            self._signal_bus.error_occurred.emit("Failed to refresh all characters")
        finally:
            self._refresh_in_progress = False
            self._cancel_token = None
            self._request_account_relayout()

    async def _refresh_character_endpoints_parallel_batch(
        self,
        character_id: int,
        char_name: str,
        char_index: int,
        total_chars: int,
        completed_endpoints: int,
    ) -> list[bool | BaseException]:
        """Run all endpoint updates in parallel for a character in batch mode.

        Args:
            character_id: Character ID to refresh
            char_name: Character name for display
            char_index: Current character index (1-based)
            total_chars: Total number of characters being refreshed
            completed_endpoints: Number of endpoints already completed

        Returns:
            List of results - True for success, BaseException for failure
        """
        endpoints = [
            ("assets", self._update_assets),
            ("wallet_journal", self._update_wallet_journal),
            ("wallet_transactions", self._update_wallet_transactions),
            ("market_orders", self._update_market_orders),
            ("contracts", self._update_contracts),
            ("industry_jobs", self._update_industry_jobs),
        ]

        total_all_endpoints = total_chars * len(endpoints)
        completed = [
            completed_endpoints
        ]  # Use list to allow mutation in nested function

        async def run_endpoint(name: str, func) -> bool | Exception:
            """Run a single endpoint (ESI client handles rate limiting)."""
            if self._cancel_token and self._cancel_token.is_cancelled:
                return Exception("Cancelled")

            try:
                # ESI client handles rate limiting internally via RateLimitTracker
                if self._cancel_token and self._cancel_token.is_cancelled:
                    return Exception("Cancelled")
                await func(character_id)

                # Update progress via signal bus
                completed[0] += 1
                self._signal_bus.progress_update.emit(
                    completed[0],
                    f"{char_name} ({char_index}/{total_chars}) - {completed[0]}/{total_all_endpoints}",
                )
                return True
            except Exception as e:
                logger.exception(
                    f"Failed to update {name} for character {character_id}"
                )
                completed[0] += 1
                self._signal_bus.progress_update.emit(
                    completed[0],
                    f"{char_name} ({char_index}/{total_chars}) - {completed[0]}/{total_all_endpoints}",
                )
                return e

        results = await asyncio.gather(
            *[run_endpoint(name, func) for name, func in endpoints],
            return_exceptions=True,
        )

        return list(results)

    async def _create_account_plex_snapshots(
        self, account_ids: list[int] | None, snapshot_group_id: int
    ) -> None:
        """Create PLEX snapshots for specified accounts.

        Args:
            account_ids: List of account IDs (None = skip)
            snapshot_group_id: Snapshot group to associate with
        """
        if not account_ids or not self._networth_service:
            return

        try:
            for account_id in account_ids:
                try:
                    plex_units = 0
                    plex_price = 0.0

                    # Get PLEX units from settings
                    if hasattr(self._settings, "get_account_plex_units"):
                        plex_units = int(
                            self._settings.get_account_plex_units(account_id) or 0
                        )

                    logger.debug(
                        "Account %d PLEX units from settings: %d",
                        account_id,
                        plex_units,
                    )

                    if plex_units > 0:
                        # Try to get PLEX price from market data
                        if self._fuzzwork_provider:
                            try:
                                market_data = self._fuzzwork_provider.get_market_data(
                                    44992
                                )
                                if market_data and market_data.region_data:
                                    for region_data in market_data.region_data.values():
                                        if region_data.sell_stats:
                                            plex_price = float(
                                                region_data.sell_stats.median
                                            )
                                            logger.debug(
                                                "Got PLEX price from market: %.2f ISK",
                                                plex_price,
                                            )
                                            break
                                if plex_price == 0.0:
                                    logger.warning(
                                        "No PLEX price available from Fuzzwork, using 0.0"
                                    )
                            except Exception:
                                logger.warning(
                                    "Failed to get PLEX price, using 0.0",
                                    exc_info=True,
                                )
                        else:
                            logger.warning(
                                "Fuzzwork provider not available for PLEX pricing"
                            )

                        # Save snapshot even if price is 0 (better than no snapshot)
                        await self._networth_service.save_account_plex_snapshot(
                            account_id, plex_units, plex_price, snapshot_group_id
                        )
                        logger.info(
                            "Created PLEX snapshot: account=%d, units=%d, price=%.2f, group=%d",
                            account_id,
                            plex_units,
                            plex_price,
                            snapshot_group_id,
                        )
                    else:
                        logger.debug(
                            "Skipping PLEX snapshot for account %d (no units configured)",
                            account_id,
                        )
                except Exception:
                    logger.debug(
                        "Failed to create PLEX snapshot for account %d",
                        account_id,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("Failed to create account PLEX snapshots", exc_info=True)

    def _find_character_widget(self, character_id: int):
        """Find the character widget for a given character ID."""
        for group in self.account_groups.values():
            for card in group.character_cards:
                if card.character_id == character_id:
                    return card.character_widget
        return None

    def _get_account_character_cards(self, account_id: int | None):
        """Get all character cards for a given account."""
        group = self.account_groups.get(account_id)
        if group:
            return group.character_cards
        return []

    def _connect_signals(self) -> None:
        """Connect signals."""
        self._signal_bus.character_selected.connect(self._on_character_selected)
        self._signal_bus.character_added.connect(self._on_character_added)
        self._signal_bus.character_removed.connect(self._on_character_removed)
        # Listen for centralized character loading
        self._signal_bus.characters_loaded.connect(self._on_characters_loaded)
        # Listen for account changes to refresh UI
        self._signal_bus.account_changed.connect(self._on_account_changed)
        # Listen for progress cancel signal from main window
        self._signal_bus.progress_cancel_requested.connect(self._on_cancel_refresh)

    @pyqtSlot()
    def _on_account_changed(self) -> None:
        """Handle account structure changes - refresh the UI."""
        logger.debug("Account changed signal received, refreshing UI")
        task = asyncio.create_task(self._refresh_after_reassign())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle centrally-loaded characters.

        Args:
            characters: List of CharacterInfo objects from central loader
        """
        logger.debug("Received %d characters from central loader", len(characters))
        try:
            self._last_loaded_characters = list(characters)
        except Exception:
            self._last_loaded_characters = characters
        task = asyncio.create_task(self._populate_characters(characters))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _populate_characters(self, characters: list):
        """Populate UI with characters grouped by account (async)."""
        try:
            # Clear existing account groups
            for group in self.account_groups.values():
                group.deleteLater()
            self.account_groups.clear()

            # Clear grid layout
            while self.accounts_layout.count():
                item = self.accounts_layout.takeAt(0)
                if item is None:
                    break
                try:
                    w = item.widget()
                except Exception:
                    w = None
                if w is not None:
                    w.setParent(self.accounts_container)

            # Clear empty accounts flow layout
            while self.empty_accounts_flow_layout.count():
                item = self.empty_accounts_flow_layout.takeAt(0)
                if item is None:
                    break
                try:
                    w = item.widget()
                except Exception:
                    w = None
                if w is not None:
                    w.deleteLater()

            self._account_group_widgets.clear()
            self._empty_account_widgets: list[EmptyAccountWidget] = []

            # Always hide list view table when repopulating cards
            self.list_table.hide()
            self.scroll_area.show()

            # Build grouping by account using settings
            accounts = self._settings.get_accounts()
            # Map char_id -> account_id
            char_to_acc: dict[int, int] = {}
            for acc_id, acc in accounts.items():
                for cid in acc.get("characters", []):
                    char_to_acc[int(cid)] = int(acc_id)

            # Bucket characters
            acc_buckets: dict[int | None, list] = {}
            for ch in characters:
                acc_id = char_to_acc.get(getattr(ch, "character_id", 0))
                acc_buckets.setdefault(acc_id, []).append(ch)

            # Separate accounts with characters from empty accounts
            all_account_ids = sorted(accounts.keys())
            accounts_with_chars = []
            empty_accounts = []

            for acc_id in all_account_ids:
                if acc_buckets.get(acc_id):
                    accounts_with_chars.append(acc_id)
                else:
                    empty_accounts.append(acc_id)

            # Create full AccountGroupWidget for accounts with characters
            for acc_id in accounts_with_chars:
                acc = accounts.get(acc_id, {})
                acc_name = acc.get("name") or f"Account {acc_id}"
                plex_units = int(acc.get("plex_units", 0))

                group = AccountGroupWidget(acc_id, acc_name, plex_units)
                group.character_dropped.connect(self._on_character_dropped)
                group.character_reordered.connect(self._on_character_reordered)
                group.character_clicked.connect(self._on_character_clicked)
                group.character_context_menu.connect(self._show_context_menu)
                group.account_refresh_requested.connect(self._on_refresh_account)

                # Get characters for this account
                chars_for_account = acc_buckets.get(acc_id, [])

                # Get saved character order for this account
                saved_order = self._settings.get_account_character_order(acc_id)

                # Sort characters according to saved order (if exists)
                if saved_order:
                    # Create a map of character_id -> character for quick lookup
                    char_map = {
                        getattr(ch, "character_id", 0): ch for ch in chars_for_account
                    }
                    # Build ordered list based on saved order, then append any missing ones
                    ordered_chars = []
                    for char_id in saved_order:
                        if char_id in char_map:
                            ordered_chars.append(char_map[char_id])
                            del char_map[char_id]
                    # Append any characters not in saved order (new additions)
                    ordered_chars.extend(char_map.values())
                    chars_for_account = ordered_chars

                for ch in chars_for_account:
                    char_widget = await self._create_character_widget(ch)
                    group.add_character(getattr(ch, "character_id", 0), char_widget)

                self._account_group_widgets.append(group)
                self.account_groups[acc_id] = group

            # Create compact EmptyAccountWidget for empty accounts
            for acc_id in empty_accounts:
                acc = accounts.get(acc_id, {})
                acc_name = acc.get("name") or f"Account {acc_id}"
                plex_units = int(acc.get("plex_units", 0))

                empty_widget = EmptyAccountWidget(acc_id, acc_name, plex_units)
                empty_widget.character_dropped.connect(self._on_character_dropped)
                empty_widget.account_refresh_requested.connect(self._on_refresh_account)
                self._empty_account_widgets.append(empty_widget)
                self.account_groups[acc_id] = empty_widget

            # Unassigned group if any characters are not assigned
            if None in acc_buckets:
                group = AccountGroupWidget(None, "Unassigned")
                group.character_dropped.connect(self._on_character_dropped)
                group.character_reordered.connect(self._on_character_reordered)
                group.character_clicked.connect(self._on_character_clicked)
                group.character_context_menu.connect(self._show_context_menu)
                group.account_refresh_requested.connect(self._on_refresh_account)

                for ch in acc_buckets.get(None, []):
                    char_widget = await self._create_character_widget(ch)
                    group.add_character(getattr(ch, "character_id", 0), char_widget)

                self._account_group_widgets.append(group)
                self.account_groups[None] = group

            # Add account groups to the flow layout
            for group in self._account_group_widgets:
                self.accounts_layout.addWidget(group)

            # Layout empty accounts in a grid (3 columns max for compact display)
            if self._empty_account_widgets:
                self.empty_accounts_header.show()
                col = 0
                row = 0
                max_cols = 3
                for empty_widget in self._empty_account_widgets:
                    self.empty_accounts_flow_layout.addWidget(empty_widget, row, col)
                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1
            else:
                self.empty_accounts_header.hide()

            self.accounts_container.updateGeometry()
        except Exception:
            logger.exception("Failed to populate characters")
            self._signal_bus.error_occurred.emit("Failed to populate characters")

    def _request_account_relayout(self) -> None:
        """Schedule a deferred account grid recalculation."""
        if self._pending_account_layout_refresh:
            return

        self._pending_account_layout_refresh = True

        def _trigger() -> None:
            self._pending_account_layout_refresh = False
            try:
                self._recalculate_account_columns(force=True)
            except Exception:
                logger.debug("Deferred account relayout failed", exc_info=True)

        try:
            QTimer.singleShot(0, _trigger)
        except Exception:
            self._pending_account_layout_refresh = False
            self._recalculate_account_columns(force=True)

    def _recalculate_account_columns(self, force: bool = False) -> None:
        """Reflow account cards safely using the FlowLayout.

        The FlowLayout already handles wrapping; this helper simply nudges
        geometry updates and tracks an approximate column count to avoid the
        AttributeError seen in deferred relayout callbacks.
        """
        try:
            container = getattr(self, "accounts_container", None)
            layout = getattr(self, "accounts_layout", None)
            if container is None or layout is None:
                return

            viewport = None
            try:
                viewport = self.scroll_area.viewport()
            except Exception:
                viewport = None

            available_width = (
                viewport.width() if viewport is not None else container.width()
            )
            if available_width <= 0:
                available_width = container.sizeHint().width() or 1

            try:
                spacing = layout.horizontalSpacing() or 0
            except Exception:
                spacing = 0

            try:
                max_card_width = max(
                    (w.sizeHint().width() for w in self._account_group_widgets),
                    default=240,
                )
            except Exception:
                max_card_width = 240

            calculated_columns = max(
                1, int(available_width / (max_card_width + spacing or 1))
            )

            if force or calculated_columns != getattr(self, "_account_columns", 1):
                self._account_columns = calculated_columns
                container.updateGeometry()
                container.adjustSize()
                try:
                    layout.setGeometry(container.geometry())
                except Exception:
                    pass
                container.update()
                try:
                    self.scroll_content.updateGeometry()
                except Exception:
                    pass
        except Exception:
            logger.debug("Failed to recalculate account columns", exc_info=True)

    def _get_endpoint_timers(self, character_id: int) -> dict[str, float | None]:
        """Look up cache expiry timers for endpoints feeding networth data."""
        timers: dict[str, float | None] = {}

        cache = getattr(self._esi_client, "cache", None)
        if cache is None:
            return timers

        def ttl(method: str, path: str, params: dict | None) -> float | None:
            try:
                return cache.time_to_expiry(method, path, params)
            except Exception:
                return None

        try:
            timers["assets"] = ttl(
                "GET", f"/characters/{character_id}/assets/", {"page": 1}
            )
            journal_ttl = ttl(
                "GET", f"/characters/{character_id}/wallet/journal/", {"page": 1}
            )
            transactions_ttl = ttl(
                "GET", f"/characters/{character_id}/wallet/transactions/", None
            )
            wallet_candidates = [
                value for value in (journal_ttl, transactions_ttl) if value is not None
            ]
            timers["wallet"] = max(wallet_candidates) if wallet_candidates else None
            timers["market_orders"] = ttl(
                "GET", f"/characters/{character_id}/orders/", None
            )
            timers["contracts"] = ttl(
                "GET", f"/characters/{character_id}/contracts/", {"page": 1}
            )
            timers["industry_jobs"] = ttl(
                "GET", f"/characters/{character_id}/industry/jobs/", {}
            )
        except Exception:
            logger.debug(
                "Failed to compute endpoint timers for character %s",
                character_id,
                exc_info=True,
            )

        return timers

    def _publish_endpoint_timers(self, character_id: int) -> dict[str, float | None]:
        """Compute and broadcast endpoint timers for a character.

        Timers are cached in memory to survive widget recreations.
        """
        timers = self._get_endpoint_timers(character_id)

        # Cache timers to preserve across widget recreations (tab switches)
        self._endpoint_timer_cache[character_id] = timers

        try:
            self._signal_bus.endpoint_timers_updated.emit(character_id, timers)
        except Exception:
            logger.debug("Failed to emit endpoint timers", exc_info=True)

        # Also update the character widget in-place if it exists
        try:
            widget = self._find_character_widget(character_id)
            if widget is not None:
                widget.set_endpoint_timers(timers)
        except Exception:
            logger.debug("Failed to set endpoint timers on widget", exc_info=True)

        return timers

    async def _create_character_widget(self, character):
        """Create and populate a character widget."""
        char_widget = CharacterItemWidget(character)
        # Connect refresh signal
        char_widget.refresh_requested.connect(self._on_refresh_character)
        # Apply initial view mode
        char_widget.set_view_mode(
            "list" if self.listview_checkbox.isChecked() else "card"
        )
        # Apply initial networth visibility
        char_widget.set_networth_visible(True)  # Always show networth
        # Refresh sizes from settings
        try:
            char_widget.refresh_sizes()
        except Exception:
            pass

        # Load images and networth asynchronously
        task = asyncio.create_task(self._load_images(character, char_widget))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        if self._networth_service is not None:
            task2 = asyncio.create_task(self._load_networth(character, char_widget))
            self._background_tasks.add(task2)
            task2.add_done_callback(self._background_tasks.discard)

        # Restore cached timers if available (from previous widget or refresh)
        # This prevents timers from resetting when switching tabs
        character_id = character.character_id
        if character_id in self._endpoint_timer_cache:
            cached_timers = self._endpoint_timer_cache[character_id]
            char_widget.set_endpoint_timers(cached_timers)
        else:
            # First time seeing this character - load timers from ESI cache
            self._publish_endpoint_timers(character_id)

        return char_widget

    async def _load_images(self, character, widget):
        portrait_sizes = [1024, 512, 256, 128, 64, 32]
        portrait = None
        for size in portrait_sizes:
            try:
                portrait = await self._character_service.get_character_portrait(
                    character.character_id, size
                )
                if portrait:
                    widget.set_portrait(portrait)
                    break
            except Exception:
                logger.debug(
                    f"Failed to load portrait size {size} for character %s",
                    character.character_id,
                )
        if character.corporation_id:
            try:
                logo = await self._character_service.get_corporation_logo(
                    character.corporation_id, 64
                )
                if logo:
                    widget.set_corp_logo(logo)
            except Exception:
                logger.debug(
                    "Failed to load corp logo for corp %s", character.corporation_id
                )
        if character.alliance_id:
            try:
                logo = await self._character_service.get_alliance_logo(
                    character.alliance_id, 64
                )
                if logo:
                    widget.set_alliance_logo(logo)
            except Exception:
                logger.debug(
                    "Failed to load alliance logo for alliance %s",
                    character.alliance_id,
                )

    async def _load_networth(self, character, widget):
        try:
            latest = (
                await self._networth_service.get_latest_networth(character.character_id)
                if self._networth_service is not None
                else None
            )

            # Preserve existing endpoint timers before updating networth
            existing_timers = (
                widget._endpoint_timers.copy()
                if hasattr(widget, "_endpoint_timers")
                else {}
            )

            # Set the networth data (this will recreate the display)
            widget.set_networth(latest)

            # Restore timers if they were lost during networth update
            if existing_timers and widget._endpoint_timers != existing_timers:
                widget.set_endpoint_timers(existing_timers)

            # Store snapshot reference for list view access
            widget._networth_snapshot = latest

            # Ensure networth is visible after data is loaded (always show in card mode)
            widget.set_networth_visible(True)

            # Refresh endpoint timers from ESI cache to ensure they're current
            # This will update the display with latest cache expiry times
            self._publish_endpoint_timers(character.character_id)

            try:
                widget.updateGeometry()
                parent_card = widget.parentWidget()
                if parent_card is not None:
                    parent_card.updateGeometry()
                    container = parent_card.parentWidget()
                    if container is not None and hasattr(container, "updateGeometry"):
                        container.updateGeometry()
            except Exception:
                logger.debug(
                    "Failed to propagate geometry updates for character %s",
                    character.character_id,
                    exc_info=True,
                )
            self._request_account_relayout()
        except Exception:
            logger.debug(
                "Failed to load latest networth for %s",
                character.character_id,
                exc_info=True,
            )

    def _on_timers_toggle(self, state: int) -> None:
        """Show/hide endpoint timers across character cards."""
        visible = state != 0
        try:
            # Save the state to settings
            self._settings.set_show_endpoint_timers(visible)

            if self.listview_checkbox.isChecked():
                visible = False
            for group in self.account_groups.values():
                for card in getattr(group, "character_cards", []):
                    try:
                        # Toggle endpoint timer visibility in the widget
                        if hasattr(card.character_widget, "set_timers_visible"):
                            card.character_widget.set_timers_visible(visible)
                        # Update card size constraints to account for timer visibility change
                        if hasattr(card, "update_size_constraints"):
                            card.update_size_constraints()
                    except Exception:
                        pass
        except Exception:
            logger.exception("Failed to toggle timers visibility")

    def _on_listview_toggle(self, state: int) -> None:
        """Switch between card and list views, and update UI accordingly."""
        is_list = state != 0
        try:
            # Save the state to settings
            self._settings.set_list_view_enabled(is_list)

            if is_list:
                # Remember timers checkbox state and disable it
                self._timers_checkbox_prev_state = self.timers_checkbox.isChecked()
                self.timers_checkbox.setEnabled(False)
                self.timers_checkbox.setChecked(False)
                # Hide card view, show list view
                self.scroll_area.hide()
                self.list_table.show()
                self._populate_list_table()
            else:
                # Restore timers checkbox state and enable it
                self.timers_checkbox.setEnabled(True)
                self.timers_checkbox.setChecked(self._timers_checkbox_prev_state)
                # Hide list view, show card view
                self.list_table.hide()
                self.scroll_area.show()
            # Update all widgets' view mode
            for group in self.account_groups.values():
                for card in getattr(group, "character_cards", []):
                    try:
                        card.character_widget.set_view_mode(
                            "list" if is_list else "card"
                        )
                        # Always show networth in card mode
                        card.character_widget.set_networth_visible(not is_list)
                        card.character_widget.refresh_sizes()
                        # Update card size constraints after view mode change
                        if hasattr(card, "update_size_constraints"):
                            card.update_size_constraints()
                    except Exception:
                        pass
        except Exception:
            logger.exception("Failed to toggle list view")

    def _populate_list_table(self):
        """Populate the QTableWidget with all characters as rows."""
        try:
            # Helper function for ISK formatting
            def safe_fmt(val):
                try:
                    x = float(val or 0.0)
                    if x >= 1_000_000_000:
                        return f"{x / 1_000_000_000:.2f}b"
                    if x >= 1_000_000:
                        return f"{x / 1_000_000:.2f}m"
                    if x >= 1_000:
                        return f"{x / 1_000:.2f}k"
                    return f"{x:.0f}"
                except Exception:
                    return "0"

            # Flatten all characters from all account groups
            all_chars = []
            for group in self.account_groups.values():
                for card in getattr(group, "character_cards", []):
                    widget = getattr(card, "character_widget", None)
                    if widget is not None:
                        ch = getattr(widget, "character", None)
                        if ch is not None:
                            all_chars.append((ch, widget))

            # Map character to account (name) using settings
            accounts = self._settings.get_accounts()
            char_to_acc: dict[int, int] = {}
            account_names: dict[int, str] = {}
            for acc_id, acc_data in accounts.items():
                try:
                    account_names[int(acc_id)] = (
                        acc_data.get("name") or f"Account {acc_id}"
                    )
                    for cid in acc_data.get("characters", []):
                        char_to_acc[int(cid)] = int(acc_id)
                except Exception:
                    continue

            self.list_table.setRowCount(len(all_chars))

            for row, (ch, widget) in enumerate(all_chars):
                # Name, Account, Corp, Alliance
                name = str(getattr(ch, "character_name", ""))
                account_id = char_to_acc.get(getattr(ch, "character_id", 0))
                account_name = (
                    account_names.get(account_id, "Unassigned")
                    if account_id is not None
                    else "Unassigned"
                )
                corp = str(getattr(ch, "corporation_name", ""))
                alliance = str(getattr(ch, "alliance_name", ""))

                # Try to get networth snapshot from widget (if loaded)
                snap = getattr(widget, "_networth_snapshot", None)
                wallet = assets = escrow = sell = contracts = collat = industry = (
                    networth_total
                ) = "-"

                if snap is not None:
                    wallet = safe_fmt(getattr(snap, "wallet_balance", 0))
                    assets = safe_fmt(getattr(snap, "total_asset_value", 0))
                    escrow = safe_fmt(getattr(snap, "market_escrow", 0))
                    sell = safe_fmt(getattr(snap, "market_sell_value", 0))
                    contracts = safe_fmt(getattr(snap, "contract_value", 0))
                    collat = safe_fmt(getattr(snap, "contract_collateral", 0))
                    industry = safe_fmt(getattr(snap, "industry_job_value", 0))
                    try:
                        total_val = getattr(snap, "total_net_worth", None)
                        if total_val is None:
                            total_val = (
                                float(getattr(snap, "wallet_balance", 0) or 0)
                                + float(getattr(snap, "market_escrow", 0) or 0)
                                + float(getattr(snap, "market_sell_value", 0) or 0)
                                + float(getattr(snap, "contract_collateral", 0) or 0)
                                + float(getattr(snap, "contract_value", 0) or 0)
                                + float(getattr(snap, "total_asset_value", 0) or 0)
                                + float(getattr(snap, "industry_job_value", 0) or 0)
                                + float(getattr(snap, "plex_vault", 0) or 0)
                            )
                        networth_total = safe_fmt(total_val)
                    except Exception:
                        networth_total = "-"

                # Fill table with proper alignment
                values = [
                    name,
                    account_name,
                    corp,
                    alliance,
                    wallet,
                    assets,
                    escrow,
                    sell,
                    contracts,
                    collat,
                    industry,
                    networth_total,
                ]
                for col, val in enumerate(values):
                    item = QTableWidgetItem(str(val))
                    item.setToolTip(str(val))
                    # Right-align numeric columns
                    if col >= 4:
                        item.setTextAlignment(
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                        )
                    self.list_table.setItem(row, col, item)

            logger.info(f"Populated list table with {len(all_chars)} characters")
        except Exception:
            logger.exception("Failed to populate list table")

    @pyqtSlot(dict)
    def _on_character_added(self, character_data):
        """Handle character added signal - trigger full refresh."""
        try:
            # Add to cached list and refresh UI
            character = CharacterInfo(**character_data)
            self._last_loaded_characters.append(character)
            task = asyncio.create_task(
                self._populate_characters(self._last_loaded_characters)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception:
            logger.exception("Failed to add character")

    @pyqtSlot(int)
    def _on_character_removed(self, character_id):
        """Handle character removed signal - trigger full refresh."""
        try:
            # Remove from cached list and refresh UI
            self._last_loaded_characters = [
                ch
                for ch in self._last_loaded_characters
                if getattr(ch, "character_id", 0) != character_id
            ]
            task = asyncio.create_task(
                self._populate_characters(self._last_loaded_characters)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception:
            logger.exception("Failed to remove character")

    def _show_context_menu(self, character_id: int, position):
        """Show context menu for character."""
        menu = QMenu(self)
        remove_action = QAction("Remove Character", self)
        remove_action.triggered.connect(
            lambda: asyncio.create_task(self._remove_character(character_id))
        )
        menu.addAction(remove_action)
        reauth_action = QAction("Re-authenticate", self)
        reauth_action.triggered.connect(
            lambda: self._signal_bus.info_message.emit(
                "Re-authentication not yet implemented"
            )
        )
        menu.addAction(reauth_action)
        # Manage accounts / PLEX vault
        from ui.dialogs.account_manager_dialog import AccountManagerDialog

        manage_accounts_action = QAction("Manage Accounts / PLEX Vault", self)

        def _open_accounts_dialog():
            # Build character names from loaded characters
            names: dict[int, str] = {}
            try:
                for ch in self._last_loaded_characters:
                    cid = getattr(ch, "character_id", 0)
                    name = getattr(ch, "character_name", str(cid))
                    names[int(cid)] = str(name)
            except Exception:
                pass
            AccountManagerDialog(
                self, character_id=character_id, character_names=names
            ).exec()

        manage_accounts_action.triggered.connect(_open_accounts_dialog)
        menu.addAction(manage_accounts_action)
        menu.exec(position)

    def _on_new_account_clicked(self) -> None:
        """Open the account manager dialog to create a new account."""
        from ui.dialogs.account_manager_dialog import AccountManagerDialog

        # Build id->name mapping from loaded characters
        names: dict[int, str] = {}
        try:
            for ch in self._last_loaded_characters:
                cid = getattr(ch, "character_id", 0)
                name = getattr(ch, "character_name", str(cid))
                names[int(cid)] = str(name)
        except Exception:
            pass

        dlg = AccountManagerDialog(self, character_id=None, character_names=names)
        dlg.exec()

    def _on_character_dropped(self, character_id: int, target_account_id):
        """Handle character drop onto account group."""
        # Get source account before reassigning
        source_account_id = self._settings.get_account_for_character(character_id)

        # Perform the reassignment
        self._handle_reassign(character_id, target_account_id)

        # Update UI incrementally without full repopulation
        self._update_character_assignment_ui(
            character_id, source_account_id, target_account_id
        )

    def _on_character_reordered(self, account_id: int, new_order: list[int]):
        """Handle character reordering within an account."""
        try:
            if account_id is not None:
                self._settings.set_account_character_order(account_id, new_order)
                logger.info(
                    f"Character order updated for account {account_id}: {new_order}"
                )
        except Exception:
            logger.exception("Failed to save character order")

    def _on_character_clicked(self, character_id: int):
        """Handle character click for selection."""
        self._signal_bus.character_selected.emit(character_id)

    def _handle_reassign(self, char_id: int, target_acc_id):
        """Reassign a character to the target account (or unassign if None)."""
        try:
            prev_acc = self._settings.get_account_for_character(int(char_id))
            if target_acc_id is None:
                if prev_acc is not None:
                    self._settings.unassign_character_from_account(
                        int(char_id), int(prev_acc)
                    )
                    self._signal_bus.status_message.emit(
                        f"Unassigned character {char_id} from account {prev_acc}"
                    )
                return
            ok = self._settings.assign_character_to_account(
                int(char_id), int(target_acc_id)
            )
            if not ok:
                self._signal_bus.error_occurred.emit(
                    "Account limit reached (max 3 characters)."
                )
                return
            if prev_acc is not None and int(prev_acc) != int(target_acc_id):
                self._settings.unassign_character_from_account(
                    int(char_id), int(prev_acc)
                )
            self._signal_bus.status_message.emit(
                f"Assigned character {char_id} to account {target_acc_id}"
            )
        except Exception:
            logger.exception("Failed to reassign character")

    async def _refresh_after_reassign(self):
        try:
            await self._populate_characters(self._last_loaded_characters)
        except Exception:
            logger.exception("Failed to refresh UI after reassignment")

    def _update_character_assignment_ui(
        self,
        character_id: int,
        source_account_id: int | None,
        target_account_id: int | None,
    ):
        """Incrementally update UI when a character is reassigned between accounts.

        This avoids full widget repopulation and eliminates flicker by moving the
        character widget from source to target account group in place.

        Args:
            character_id: The character being reassigned
            source_account_id: Previous account (None if unassigned)
            target_account_id: New account (None if unassigning)
        """
        try:
            # If source and target are the same, nothing to do
            if source_account_id == target_account_id:
                return

            # Find the source and target account group widgets
            source_group = self.account_groups.get(source_account_id)
            target_group = self.account_groups.get(target_account_id)

            # Remove character from source group
            if source_group is not None and hasattr(source_group, "remove_character"):
                source_group.remove_character(character_id)
                logger.debug(
                    f"Removed character {character_id} from account {source_account_id}"
                )

            # If target is None or doesn't have a widget yet, do full refresh
            # (this handles edge cases like moving to newly created unassigned group)
            if target_group is None or not hasattr(target_group, "add_character"):
                logger.debug("Target group not ready, falling back to full refresh")
                task = asyncio.create_task(
                    self._populate_characters(self._last_loaded_characters)
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
                return

            # Find the character widget for this character_id
            char_widget = None
            for ch in self._last_loaded_characters:
                if getattr(ch, "character_id", 0) == character_id:
                    # Create a new widget for the target group
                    task = asyncio.create_task(
                        self._add_character_to_group(ch, target_group, character_id)
                    )
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
                    break

            logger.info(
                f"Incrementally moved character {character_id} from account {source_account_id} to {target_account_id}"
            )
        except Exception:
            logger.exception(
                f"Failed to incrementally update character {character_id} assignment, falling back to full refresh"
            )
            # Fall back to full refresh on error
            task = asyncio.create_task(
                self._populate_characters(self._last_loaded_characters)
            )
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)

    async def _add_character_to_group(self, character, group, character_id: int):
        """Helper to asynchronously create and add a character widget to a group."""
        try:
            char_widget = await self._create_character_widget(character)
            group.add_character(character_id, char_widget)
        except Exception:
            logger.exception(f"Failed to add character {character_id} to group")

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802  # type: ignore[override]
        if obj is self.accounts_container and event.type() == QEvent.Type.Resize:
            self.accounts_layout.update()
        return super().eventFilter(obj, event)

    @asyncSlot()
    def _on_add_character_clicked(self) -> None:
        """Handle Add Character button click."""
        from ui.dialogs.auth_dialog import AuthDialog

        dialog = AuthDialog(self._character_service, self)
        dialog.exec()

    async def _remove_character(self, character_id):
        try:
            success = await self._character_service.remove_character(character_id)
            if success:
                self._signal_bus.character_removed.emit(character_id)
                self._signal_bus.status_message.emit(
                    f"Character {character_id} removed"
                )
            else:
                self._signal_bus.error_occurred.emit("Character not found")
        except Exception:
            logger.exception("Failed to remove character %s", character_id)
            self._signal_bus.error_occurred.emit("Failed to remove character")

    @pyqtSlot(int)
    def _on_character_selected(self, character_id: int) -> None:
        """Handle character selection.

        Args:
            character_id: Selected character ID
        """
        self._selected_character_id = character_id

    def _load_rate_limits(self, character_id: int) -> dict:
        """Load rate limit info for the selected character from rate_limits.json."""
        rate_limits_path = Path("data/esi/rate_limits.json")
        if not rate_limits_path.exists():
            return {}
        with open(rate_limits_path, encoding="utf-8") as f:
            data = json.load(f)
        groups = data.get("rate_limit_groups", {})
        # Map endpoint names to group keys
        group_map = {
            "Wallet Journal": f"char-wallet:{character_id}",
            "Wallet Transactions": f"char-wallet:{character_id}",
            "Contracts": f"char-contract:{character_id}",
            "Industry Jobs": f"char-industry:{character_id}",
            # Add more mappings if needed
        }
        result = {}
        for name, group_key in group_map.items():
            group = groups.get(group_key)
            if group:
                result[name] = group
        return result

    @asyncSlot()
    async def _on_update_all(self) -> None:
        """Update all endpoints for selected character using parallel updates."""
        if self._selected_character_id is None:
            self._signal_bus.info_message.emit("Please select a character first")
            return

        # Delegate to the parallel refresh implementation
        await self._on_refresh_character(self._selected_character_id)

    async def _update_assets(self, character_id: int) -> None:
        """Update assets for character.

        Ensures assets are fully persisted and locations are prepared for resolution.

        Args:
            character_id: Character ID
        """
        # Use the asset service's sync method which handles persistence properly
        try:
            count = await self._asset_service.sync_assets(
                character_id, use_cache=True, bypass_cache=False
            )
            logger.info(
                "Synced %d assets for character %d",
                count,
                character_id,
            )
        except Exception:
            logger.exception("Failed to sync assets for character %d", character_id)

    async def _update_wallet_journal(self, character_id: int) -> None:
        """Update wallet journal for character.

        Args:
            character_id: Character ID
        """
        await self._wallet_service.sync_journal(character_id)

    async def _update_wallet_transactions(self, character_id: int) -> None:
        """Update wallet transactions for character.

        Args:
            character_id: Character ID
        """
        await self._wallet_service.sync_transactions(character_id)

    async def _update_market_orders(self, character_id: int) -> None:
        """Update market orders for character.

        Args:
            character_id: Character ID
        """
        await self._market_service.sync_orders(character_id)

    async def _update_contracts(self, character_id: int) -> None:
        """Update contracts for character.

        Args:
            character_id: Character ID
        """
        await self._contract_service.sync_contracts(character_id)

    async def _update_industry_jobs(self, character_id: int) -> None:
        """Update industry jobs for character.

        Args:
            character_id: Character ID
        """
        await self._industry_service.sync_jobs(character_id, include_completed=False)
