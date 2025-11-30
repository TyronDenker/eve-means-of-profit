"""Characters tab with update timers and refresh functionality."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, pyqtSlot
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QProgressBar,
    QPushButton,
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
from services.wallet_service import WalletService
from ui.signal_bus import get_signal_bus
from ui.widgets import CharacterItemWidget, EndpointTimer


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
        self._signal_bus = get_signal_bus()
        self._background_tasks: set[asyncio.Task] = set()
        self._selected_character_id: int | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Left side: Character list (now integrated)
        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setIconSize(QSize(160, 300))
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setSpacing(10)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        main_layout.addWidget(self.list_widget, stretch=2)

        # Right side: Update controls
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        # Title
        self.title_label = QLabel("<h3>Endpoint Status</h3>")
        self.right_layout.addWidget(self.title_label)

        # Info label (placeholder)
        self.info_label = QLabel("Select a character to view endpoint timers")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: gray; font-style: italic;")
        self.right_layout.addWidget(self.info_label)

        # Endpoint timers container
        self.timers_widget = QWidget()
        self.timers_layout = QVBoxLayout(self.timers_widget)
        self.timers_layout.setContentsMargins(0, 10, 0, 0)
        self.timers_layout.setSpacing(5)

        self.endpoint_timers: dict[str, EndpointTimer] = {}
        endpoint_names = [
            "Assets",
            "Wallet Journal",
            "Wallet Transactions",
            "Market Orders",
            "Contracts",
            "Industry Jobs",
        ]

        for name in endpoint_names:
            timer = EndpointTimer(name)
            self.endpoint_timers[name] = timer
            self.timers_layout.addWidget(timer)

        self.timers_layout.addStretch()
        self.right_layout.addWidget(self.timers_widget)

        # Progress bar for updates
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.right_layout.addWidget(self.progress_bar)

        # Update all endpoints for selected character
        self.update_button = QPushButton("Update All Endpoints")
        self.update_button.setEnabled(False)
        self.update_button.clicked.connect(self._on_update_all)
        self.right_layout.addWidget(self.update_button)

        # Update all characters button
        self.update_all_characters_button = QPushButton("Update All Characters")
        self.update_all_characters_button.setEnabled(True)
        self.update_all_characters_button.clicked.connect(
            self._on_update_all_characters
        )
        self.right_layout.addWidget(self.update_all_characters_button)

        # Finalize right layout and add to main layout
        self.right_layout.addStretch()
        main_layout.addWidget(self.right_widget, stretch=1)
        # Initially hide endpoint timers and controls, show placeholder
        self._show_placeholder(True)

    @asyncSlot()
    async def _on_update_all_characters(self) -> None:
        """Update all endpoints for all characters."""
        try:
            # Get all character IDs from the integrated character list
            character_ids = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item:
                    cid = item.data(Qt.ItemDataRole.UserRole)
                    if cid:
                        character_ids.append(cid)

            if not character_ids:
                self._signal_bus.info_message.emit("No characters to update.")
                return

            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(len(character_ids) * 6)
            self.progress_bar.setValue(0)
            self.update_all_characters_button.setEnabled(False)
            self.update_button.setEnabled(False)

            self._signal_bus.status_message.emit(
                f"Updating all endpoints for {len(character_ids)} characters..."
            )

            updates = [
                ("assets", self._update_assets),
                ("wallet journal", self._update_wallet_journal),
                ("wallet transactions", self._update_wallet_transactions),
                ("market orders", self._update_market_orders),
                ("contracts", self._update_contracts),
                ("industry jobs", self._update_industry_jobs),
            ]

            progress = 0
            for character_id in character_ids:
                for name, update_func in updates:
                    try:
                        self._signal_bus.status_message.emit(
                            f"Updating {name} for character {character_id}..."
                        )
                        await update_func(character_id)
                        progress += 1
                        self.progress_bar.setValue(progress)
                    except Exception:
                        logger.exception(
                            f"Failed to update {name} for character {character_id}"
                        )
                        self._signal_bus.error_occurred.emit(
                            f"Failed to update {name} for character {character_id}. Check logs for details."
                        )

            self._signal_bus.status_message.emit("All characters updated successfully!")

            # Refresh timers for selected character
            self._update_endpoint_timers()

        except Exception:
            logger.exception("Failed to update all characters")
            self._signal_bus.error_occurred.emit("Failed to update all characters")
        finally:
            self.progress_bar.setVisible(False)
            self.update_all_characters_button.setEnabled(True)
            self.update_button.setEnabled(True)

    def _show_placeholder(self, show: bool) -> None:
        """Show or hide the placeholder info label and endpoint controls."""
        self.info_label.setVisible(show)
        self.title_label.setVisible(not show)
        self.timers_widget.setVisible(not show)
        self.progress_bar.setVisible(False if show else self.progress_bar.isVisible())
        self.update_button.setVisible(not show)

    def _connect_signals(self) -> None:
        """Connect signals."""
        self._signal_bus.character_selected.connect(self._on_character_selected)

    def load_initial_characters(self):
        task = asyncio.create_task(self._load_characters())
        if not hasattr(self, "_background_tasks"):
            self._background_tasks = set()
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _load_characters(self):
        try:
            characters = await self._character_service.get_authenticated_characters()
            for character in characters:
                await self._add_character(character)
        except Exception:
            logger.exception("Failed to load characters")
            self._signal_bus.error_occurred.emit("Failed to load characters")

    async def _add_character(self, character):
        item = QListWidgetItem(self.list_widget)
        item.setSizeHint(QSize(180, 320))
        item.setData(Qt.ItemDataRole.UserRole, getattr(character, "character_id", None))
        char_widget = CharacterItemWidget(character)
        item.setSizeHint(char_widget.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, char_widget)
        task = asyncio.create_task(self._load_images(character, char_widget))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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

    @pyqtSlot(dict)
    def _on_character_added(self, character_data):
        try:
            character = CharacterInfo(**character_data)
            task = asyncio.create_task(self._add_character(character))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except Exception:
            logger.exception("Failed to add character to list")

    @pyqtSlot(int)
    def _on_character_removed(self, character_id):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == character_id:
                self.list_widget.takeItem(i)
                break

    @pyqtSlot(QListWidgetItem)
    def _on_item_clicked(self, item):
        character_id = item.data(Qt.ItemDataRole.UserRole)
        if character_id:
            self._signal_bus.character_selected.emit(character_id)

    @pyqtSlot()
    def _show_context_menu(self, position):
        item = self.list_widget.itemAt(position)
        if not item:
            return
        character_id = item.data(Qt.ItemDataRole.UserRole)
        if not character_id:
            return
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
        menu.exec(self.list_widget.mapToGlobal(position))

    @asyncSlot()
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
        self.update_button.setEnabled(True)
        self._show_placeholder(False)
        self._update_endpoint_timers()

    @pyqtSlot()
    def _on_refresh_timers(self) -> None:
        """Refresh the endpoint timers display."""
        if self._selected_character_id is not None:
            self._update_endpoint_timers()
        else:
            self._signal_bus.info_message.emit("Please select a character first")

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

    def _update_endpoint_timers(self) -> None:
        """Update endpoint timer displays based on cache status and rate limits."""
        if self._selected_character_id is None:
            self._show_placeholder(True)
            return

        try:
            character_id = self._selected_character_id
            endpoints = {
                "Assets": f"/characters/{character_id}/assets/",
                "Wallet Journal": f"/characters/{character_id}/wallet/journal/",
                "Wallet Transactions": f"/characters/{character_id}/wallet/transactions/",
                "Market Orders": f"/characters/{character_id}/orders/",
                "Contracts": f"/characters/{character_id}/contracts/",
                "Industry Jobs": f"/characters/{character_id}/industry/jobs/",
            }

            for name, path in endpoints.items():
                timer = self.endpoint_timers.get(name)
                # Use params={"page": 1} for paginated endpoints to match cache key
                paginated = name in {"Assets", "Wallet Journal", "Contracts"}
                params = {"page": 1} if paginated else None
                ttl = self._esi_client.cache.time_to_expiry("GET", path, params=params)

                if ttl is None:
                    cached = self._esi_client.cache.get("GET", path, params=params)
                    if cached is None:
                        resolved_ttl = None
                    else:
                        resolved_ttl = None
                else:
                    resolved_ttl = ttl

                if timer is not None:
                    timer.set_expiry(resolved_ttl)

        except Exception:
            logger.exception("Failed to update endpoint timers")

    @asyncSlot()
    async def _on_update_all(self) -> None:
        """Update all endpoints for selected character."""
        if self._selected_character_id is None:
            self._signal_bus.info_message.emit("Please select a character first")
            return

        character_id = self._selected_character_id

        try:
            # Show progress
            self.progress_bar.setVisible(True)
            self.progress_bar.setMaximum(6)
            self.progress_bar.setValue(0)
            self.update_button.setEnabled(False)

            self._signal_bus.status_message.emit(
                f"Updating all endpoints for character {character_id}..."
            )

            # Update each endpoint
            updates = [
                ("assets", self._update_assets),
                ("wallet journal", self._update_wallet_journal),
                ("wallet transactions", self._update_wallet_transactions),
                ("market orders", self._update_market_orders),
                ("contracts", self._update_contracts),
                ("industry jobs", self._update_industry_jobs),
            ]

            for i, (name, update_func) in enumerate(updates, 1):
                try:
                    self._signal_bus.status_message.emit(f"Updating {name}...")
                    await update_func(character_id)
                    self.progress_bar.setValue(i)
                except Exception:
                    logger.exception(f"Failed to update {name}")
                    self._signal_bus.error_occurred.emit(
                        f"Failed to update {name}. Check logs for details."
                    )

            self._signal_bus.status_message.emit("All endpoints updated successfully!")

            # Refresh timers to show new cache status
            self._update_endpoint_timers()

        except Exception:
            logger.exception("Failed to update endpoints")
            self._signal_bus.error_occurred.emit("Failed to update endpoints")
        finally:
            self.progress_bar.setVisible(False)
            self.update_button.setEnabled(True)

    async def _update_assets(self, character_id: int) -> None:
        """Update assets for character.

        Args:
            character_id: Character ID
        """
        # Fetch data from ESI, respecting stale cache (like market orders)
        assets = await self._esi_client.assets.get_assets(
            character_id, use_cache=True, bypass_cache=False
        )
        logger.info(f"Fetched {len(assets)} assets for character {character_id}")

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
