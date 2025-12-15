"""Asset tree view displaying assets organized hierarchically by location."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from data.repositories import prices
from services.asset_service import AssetService
from services.character_service import CharacterService
from services.location_service import LocationService
from ui.signal_bus import get_signal_bus
from utils.settings_manager import get_settings_manager

if TYPE_CHECKING:
    from models.app.asset_tree import AssetTreeNode

logger = logging.getLogger(__name__)


class AssetTreeTab(QWidget):
    """Asset tree view showing hierarchical organization by location."""

    def __init__(
        self,
        character_service: CharacterService,
        asset_service: AssetService,
        location_service: LocationService,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._character_service = character_service
        self._asset_service = asset_service
        self._location_service = location_service
        self._settings = get_settings_manager()
        self._background_tasks: set[asyncio.Task] = set()
        self._current_characters: list = []
        self._is_refreshing: bool = False  # Guard against concurrent refreshes

        # Get repository from asset service for price lookups
        self._repo = getattr(asset_service, "_repo", None)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup UI layout and widgets."""
        main_layout = QVBoxLayout(self)

        # Toolbar with trade hub and price type selection
        toolbar_layout = QHBoxLayout()

        # Trade hub dropdown
        toolbar_layout.addWidget(QLabel("Trade Hub:"))
        self._hub_combo = QComboBox()
        self._hub_combo.addItems(["Jita", "Amarr", "Dodixie", "Rens", "Hek"])
        # Load saved preference
        saved_hub = (
            self._settings.get_market_source_station() if self._settings else "jita"
        )
        index = self._hub_combo.findText(saved_hub.capitalize())
        if index >= 0:
            self._hub_combo.setCurrentIndex(index)
        self._hub_combo.currentTextChanged.connect(self._on_price_settings_changed)
        toolbar_layout.addWidget(self._hub_combo)

        # Price type selection
        toolbar_layout.addWidget(QLabel("Price:"))
        self._buy_checkbox = QCheckBox("Buy")
        self._sell_checkbox = QCheckBox("Sell")
        # Load saved preference
        saved_type = (
            self._settings.get_market_price_type() if self._settings else "sell"
        )
        if saved_type == "buy":
            self._buy_checkbox.setChecked(True)
        else:
            self._sell_checkbox.setChecked(True)

        # Make them mutually exclusive
        self._buy_checkbox.toggled.connect(
            lambda checked: self._sell_checkbox.setChecked(not checked)
            if checked
            else None
        )
        self._sell_checkbox.toggled.connect(
            lambda checked: self._buy_checkbox.setChecked(not checked)
            if checked
            else None
        )
        self._buy_checkbox.toggled.connect(self._on_price_settings_changed)
        self._sell_checkbox.toggled.connect(self._on_price_settings_changed)

        toolbar_layout.addWidget(self._buy_checkbox)
        toolbar_layout.addWidget(self._sell_checkbox)

        self._refresh_btn = QPushButton("Refresh")
        toolbar_layout.addWidget(self._refresh_btn)
        toolbar_layout.addStretch()

        main_layout.addLayout(toolbar_layout)

        # Tree widget
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Location", "Items", "Total Value (ISK)"])
        self._tree.setColumnCount(3)
        main_layout.addWidget(self._tree)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._signal_bus.characters_loaded.connect(self._on_characters_loaded)
        # Removed character_updated - it causes duplicates by rebuilding the entire tree
        # character_updated should not trigger full refresh, only characters_loaded
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

        # Listen to custom price changes
        self._signal_bus.custom_price_changed.connect(self._on_custom_price_changed)
        self._signal_bus.market_preferences_changed.connect(
            self._on_market_preferences_changed
        )

    def _on_custom_price_changed(self, type_id: int) -> None:
        """Refresh tree when custom price changes."""
        self._on_refresh_clicked()

    def _on_market_preferences_changed(self) -> None:
        """Refresh tree when market preferences change."""
        self._on_refresh_clicked()

    def _on_price_settings_changed(self) -> None:
        """Handle price settings change and trigger refresh."""
        # Save preferences
        if self._settings:
            hub = self._hub_combo.currentText().lower()
            self._settings.set_market_source_station(hub)

            price_type = "buy" if self._buy_checkbox.isChecked() else "sell"
            self._settings.set_market_price_type(price_type)

        # Trigger refresh
        self._on_refresh_clicked()

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle characters loaded signal."""
        self._current_characters = self._dedupe_characters(characters)
        self._on_refresh_clicked()

    def _dedupe_characters(self, characters: list) -> list:
        """Return a character list without duplicates by character_id."""
        seen: set[int] = set()
        unique: list = []
        for char in characters:
            cid = getattr(char, "character_id", None)
            if cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            unique.append(char)
        return unique

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        task = asyncio.create_task(self._do_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _do_refresh(self) -> None:
        """Async refresh of asset tree."""
        # Guard against concurrent refreshes (prevents duplication on tab switch)
        if self._is_refreshing:
            logger.debug("Asset tree refresh already in progress, skipping")
            return

        self._is_refreshing = True
        try:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Loading...")

            # Clear the tree
            self._tree.clear()

            if not self._current_characters:
                logger.warning("No characters loaded, cannot build asset tree")
                return

            # Load prices from database with user preferences
            snapshot_prices: dict[int, float] = {}
            custom_prices: dict[int, dict[str, float | None]] = {}

            if self._repo and self._settings:
                # Get price settings
                trade_hub = self._settings.get_market_source_station() or "jita"
                price_type = self._settings.get_market_price_type() or "sell"
                weighted_ratio = self._settings.get_market_weighted_buy_ratio() or 0.3

                # Map hub to region ID
                hub_to_region = {
                    "jita": 10000002,
                    "amarr": 10000043,
                    "dodixie": 10000032,
                    "rens": 10000030,
                    "hek": 10000042,
                }
                region_id = hub_to_region.get(trade_hub.lower(), 10000002)

                try:
                    snapshot_prices = await prices.get_latest_snapshot_prices(
                        self._repo,
                        region_id=region_id,
                        price_type=price_type,
                        weighted_buy_ratio=weighted_ratio,
                    )
                    logger.info(
                        "Loaded %d snapshot prices for asset tree (hub=%s, type=%s, region=%d)",
                        len(snapshot_prices),
                        trade_hub,
                        price_type,
                        region_id,
                    )
                except Exception as e:
                    logger.warning("Failed to load snapshot prices: %s", e)

                # Load all custom prices
                try:
                    for type_id in range(100000):  # Rough estimate, will be optimized
                        custom = self._settings.get_custom_price(type_id)
                        if custom:
                            custom_prices[type_id] = custom
                except Exception as e:
                    logger.debug("Error loading custom prices: %s", e)

            # Build tree for each character
            for char in self._current_characters:
                char_id = getattr(char, "character_id", None)
                # Try character_name first, then name, then fallback
                char_name = (
                    getattr(char, "character_name", None)
                    or getattr(char, "name", None)
                    or f"Character {char_id}"
                )

                if not char_id:
                    continue

                try:
                    # Get enriched assets for this character to apply prices
                    enriched_assets = await self._asset_service.get_all_enriched_assets(
                        character_id=char_id,
                        character_name=char_name,
                        resolve_locations=True,
                        refresh_locations=False,
                    )

                    # Apply prices to assets (custom > snapshot > base)
                    custom_count = 0
                    snapshot_count = 0
                    for asset in enriched_assets:
                        custom = custom_prices.get(asset.type_id)
                        if custom and custom.get("sell") is not None:
                            asset.market_value = custom["sell"]
                            custom_count += 1
                        elif asset.type_id in snapshot_prices:
                            asset.market_value = snapshot_prices[asset.type_id]
                            snapshot_count += 1

                    logger.debug(
                        "Applied prices for %s: %d custom, %d snapshot, %d total assets",
                        char_name,
                        custom_count,
                        snapshot_count,
                        len(enriched_assets),
                    )

                    # Build the tree from the repriced assets
                    tree_data = self._asset_service.build_asset_tree_from_assets(
                        enriched_assets
                    )

                    # Compute character totals from the built tree
                    total_value = sum(
                        root.get_total_value() for root in tree_data.get("roots", [])
                    )
                    total_items = sum(
                        root.get_item_count() for root in tree_data.get("roots", [])
                    )

                    logger.info(
                        "Character %s asset tree: %d items, %.2f ISK total value",
                        char_name,
                        total_items,
                        total_value,
                    )

                    # Create character root node
                    char_root = QTreeWidgetItem(
                        self._tree,
                        [
                            char_name,
                            str(total_items),
                            f"{total_value:,.2f}",
                        ],
                    )
                    char_root.setExpanded(False)

                    # Add location nodes
                    for root_node in tree_data.get("roots", []):
                        self._add_tree_node(char_root, root_node)

                except Exception as e:
                    logger.error(
                        "Failed to build asset tree for character %s: %s",
                        char_id,
                        e,
                        exc_info=True,
                    )
                    # Add error node
                    QTreeWidgetItem(self._tree, [char_name, "Error", str(e)])

            # Resize columns to fit content
            self._tree.resizeColumnToContents(0)
            self._tree.resizeColumnToContents(1)
            self._tree.resizeColumnToContents(2)
        except Exception as e:
            logger.error("Error refreshing asset tree: %s", e, exc_info=True)
            self._signal_bus.error_occurred.emit(str(e))
        finally:
            self._is_refreshing = False
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Refresh")

    def _add_tree_node(
        self, parent: QTreeWidgetItem, node: AssetTreeNode
    ) -> QTreeWidgetItem:
        """Add a tree node and its children recursively.

        Args:
            parent: Parent QTreeWidgetItem
            node: AssetTreeNode to add

        Returns:
            Created QTreeWidgetItem
        """
        # Create tree item with formatted ISK value
        item = QTreeWidgetItem(
            parent,
            [
                node.location_name,
                str(node.get_item_count()),
                f"{node.get_total_value():,.2f}",
            ],
        )

        # Add children recursively
        for child in node.children:
            self._add_tree_node(item, child)

        # Expand if it has children
        if node.children:
            item.setExpanded(False)

        return item
