"""Market price panel widget for detailed price information."""

import logging
from typing import ClassVar

from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core import MarketService, PriceAnalyzer
from utils.formatting import format_currency, format_number

logger = logging.getLogger(__name__)


class MarketPricePanel(QWidget):
    """Widget for displaying detailed market price information."""

    # Common EVE regions
    REGIONS: ClassVar[list[tuple[int, str]]] = [
        (10000002, "The Forge (Jita)"),
        (10000043, "Domain (Amarr)"),
        (10000032, "Sinq Laison (Dodixie)"),
        (10000030, "Heimatar (Rens)"),
        (10000042, "Metropolis (Hek)"),
    ]

    def __init__(
        self,
        market_service: MarketService | None = None,
        price_analyzer: PriceAnalyzer | None = None,
        parent=None,
    ):
        """Initialize the market price panel.

        Args:
            market_service: MarketService for market operations
            price_analyzer: PriceAnalyzer for price analysis
            parent: Parent widget

        """
        super().__init__(parent)
        self._market_service = market_service
        self._price_analyzer = price_analyzer
        self._current_type_id: int | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("<h3>Market Prices</h3>")
        layout.addWidget(title)

        # Region selector
        region_layout = QGridLayout()
        region_label = QLabel("Region:")
        self._region_combo = QComboBox()
        for region_id, region_name in self.REGIONS:
            self._region_combo.addItem(region_name, region_id)
        self._region_combo.currentIndexChanged.connect(self._on_region_changed)
        region_layout.addWidget(region_label, 0, 0)
        region_layout.addWidget(self._region_combo, 0, 1)
        layout.addLayout(region_layout)

        # Sell Orders Group
        self._sell_group = QGroupBox("Sell Orders")
        sell_layout = QGridLayout()

        self._sell_avg_label = QLabel("N/A")
        self._sell_min_label = QLabel("N/A")
        self._sell_max_label = QLabel("N/A")
        self._sell_median_label = QLabel("N/A")
        self._sell_volume_label = QLabel("N/A")
        self._sell_orders_label = QLabel("N/A")

        sell_layout.addWidget(QLabel("Weighted Average:"), 0, 0)
        sell_layout.addWidget(self._sell_avg_label, 0, 1)
        sell_layout.addWidget(QLabel("Minimum:"), 1, 0)
        sell_layout.addWidget(self._sell_min_label, 1, 1)
        sell_layout.addWidget(QLabel("Maximum:"), 2, 0)
        sell_layout.addWidget(self._sell_max_label, 2, 1)
        sell_layout.addWidget(QLabel("Median:"), 3, 0)
        sell_layout.addWidget(self._sell_median_label, 3, 1)
        sell_layout.addWidget(QLabel("Volume:"), 4, 0)
        sell_layout.addWidget(self._sell_volume_label, 4, 1)
        sell_layout.addWidget(QLabel("Orders:"), 5, 0)
        sell_layout.addWidget(self._sell_orders_label, 5, 1)

        self._sell_group.setLayout(sell_layout)
        layout.addWidget(self._sell_group)

        # Buy Orders Group
        self._buy_group = QGroupBox("Buy Orders")
        buy_layout = QGridLayout()

        self._buy_avg_label = QLabel("N/A")
        self._buy_min_label = QLabel("N/A")
        self._buy_max_label = QLabel("N/A")
        self._buy_median_label = QLabel("N/A")
        self._buy_volume_label = QLabel("N/A")
        self._buy_orders_label = QLabel("N/A")

        buy_layout.addWidget(QLabel("Weighted Average:"), 0, 0)
        buy_layout.addWidget(self._buy_avg_label, 0, 1)
        buy_layout.addWidget(QLabel("Minimum:"), 1, 0)
        buy_layout.addWidget(self._buy_min_label, 1, 1)
        buy_layout.addWidget(QLabel("Maximum:"), 2, 0)
        buy_layout.addWidget(self._buy_max_label, 2, 1)
        buy_layout.addWidget(QLabel("Median:"), 3, 0)
        buy_layout.addWidget(self._buy_median_label, 3, 1)
        buy_layout.addWidget(QLabel("Volume:"), 4, 0)
        buy_layout.addWidget(self._buy_volume_label, 4, 1)
        buy_layout.addWidget(QLabel("Orders:"), 5, 0)
        buy_layout.addWidget(self._buy_orders_label, 5, 1)

        self._buy_group.setLayout(buy_layout)
        layout.addWidget(self._buy_group)

        # Profit Analysis Group
        self._profit_group = QGroupBox("Profit Analysis")
        profit_layout = QGridLayout()

        self._spread_label = QLabel("N/A")
        self._spread_pct_label = QLabel("N/A")
        self._available_regions_label = QLabel("N/A")

        profit_layout.addWidget(QLabel("Spread (Buy-Sell):"), 0, 0)
        profit_layout.addWidget(self._spread_label, 0, 1)
        profit_layout.addWidget(QLabel("Spread %:"), 1, 0)
        profit_layout.addWidget(self._spread_pct_label, 1, 1)
        profit_layout.addWidget(QLabel("Available Regions:"), 2, 0)
        profit_layout.addWidget(self._available_regions_label, 2, 1)

        self._profit_group.setLayout(profit_layout)
        layout.addWidget(self._profit_group)

        layout.addStretch()

    def set_type_id(self, type_id: int | None) -> None:
        """Set the current type ID and update display.

        Args:
            type_id: Type ID to display prices for

        """
        self._current_type_id = type_id
        self._update_display()

    def _on_region_changed(self) -> None:
        """Handle region selection change."""
        self._update_display()

    def _get_current_region_id(self) -> int:
        """Get the currently selected region ID.

        Returns:
            Region ID

        """
        return self._region_combo.currentData()

    def _update_display(self) -> None:
        """Update the price display with current type and region."""
        if self._current_type_id is None or self._market_service is None:
            self._clear_display()
            return

        region_id = self._get_current_region_id()

        # Use MarketService to get detailed statistics
        stats = self._market_service.get_market_statistics(
            self._current_type_id, region_id
        )

        if not stats:
            self._clear_display()
            return

        # Update sell orders
        if "sell" in stats:
            sell = stats["sell"]
            self._sell_avg_label.setText(format_currency(sell["weighted_avg"]))
            self._sell_min_label.setText(format_currency(sell["min"]))
            self._sell_max_label.setText(format_currency(sell["max"]))
            self._sell_median_label.setText(format_currency(sell["median"]))
            self._sell_volume_label.setText(format_number(sell["volume"], decimals=0))
            self._sell_orders_label.setText(str(sell["orders"]))
        else:
            self._sell_avg_label.setText("No Data")
            self._sell_min_label.setText("No Data")
            self._sell_max_label.setText("No Data")
            self._sell_median_label.setText("No Data")
            self._sell_volume_label.setText("No Data")
            self._sell_orders_label.setText("No Data")

        # Update buy orders
        if "buy" in stats:
            buy = stats["buy"]
            self._buy_avg_label.setText(format_currency(buy["weighted_avg"]))
            self._buy_min_label.setText(format_currency(buy["min"]))
            self._buy_max_label.setText(format_currency(buy["max"]))
            self._buy_median_label.setText(format_currency(buy["median"]))
            self._buy_volume_label.setText(format_number(buy["volume"], decimals=0))
            self._buy_orders_label.setText(str(buy["orders"]))
        else:
            self._buy_avg_label.setText("No Data")
            self._buy_min_label.setText("No Data")
            self._buy_max_label.setText("No Data")
            self._buy_median_label.setText("No Data")
            self._buy_volume_label.setText("No Data")
            self._buy_orders_label.setText("No Data")

        # Update profit metrics using service-calculated spread
        if "spread" in stats:
            spread_data = stats["spread"]
            self._spread_label.setText(format_currency(spread_data["value"]))
            self._spread_pct_label.setText(f"{spread_data['percent']:.2f}%")
        else:
            self._spread_label.setText("N/A")
            self._spread_pct_label.setText("N/A")

        # Get available regions using market summary
        summary = self._market_service.get_market_summary(self._current_type_id)
        self._available_regions_label.setText(str(summary.get("total_regions", 0)))

    def _clear_display(self) -> None:
        """Clear all price displays."""
        self._sell_avg_label.setText("N/A")
        self._sell_min_label.setText("N/A")
        self._sell_max_label.setText("N/A")
        self._sell_median_label.setText("N/A")
        self._sell_volume_label.setText("N/A")
        self._sell_orders_label.setText("N/A")

        self._buy_avg_label.setText("N/A")
        self._buy_min_label.setText("N/A")
        self._buy_max_label.setText("N/A")
        self._buy_median_label.setText("N/A")
        self._buy_volume_label.setText("N/A")
        self._buy_orders_label.setText("N/A")

        self._spread_label.setText("N/A")
        self._spread_pct_label.setText("N/A")
        self._available_regions_label.setText("N/A")
