"""Market data provider for high-level market data access and caching."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Literal

from data.parsers.fuzzwork_csv import FuzzworkCSVParser
from models.app import FuzzworkMarketDataPoint

logger = logging.getLogger(__name__)


class FuzzworkProvider:
    """Provider for market data with caching and optimized query capabilities.

    This provider provides:
    - Primary cache: Direct type_id lookups (O(1))
    - Index hashmaps: Fast filtered queries (O(1) for common filters)
    - Memory management: Clear caches when needed
    """

    def __init__(self, parser: FuzzworkCSVParser):
        """Initialize the market data provider.

        Args:
            parser: FuzzworkCSVParser instance for loading market data.

        """
        self._parser = parser

        # Primary cache - type_id-based lookups
        self._market_data_cache: dict[int, FuzzworkMarketDataPoint] | None = None

        # Index hashmaps - for fast filtered queries
        # Format: dict[filter_value, set[type_id]] or set[type_id]
        self._types_by_region_index: dict[int, set[int]] = {}
        self._types_with_buy_orders_index: set[int] = set()
        self._types_with_sell_orders_index: set[int] = set()

        # Snapshot metadata
        self._snapshot_time: datetime | None = None

    def get_market_data(self, type_id: int) -> FuzzworkMarketDataPoint | None:
        """Get market data for a specific type.

        Args:
            type_id: The type ID to look up

        Returns:
            MarketDataPoint or None if not found

        """
        return self._load_market_data().get(type_id)

    def get_types_in_region(self, region_id: int) -> list[FuzzworkMarketDataPoint]:
        """Get all types that have market data in a specific region.

        Uses O(1) hashmap lookup for optimal performance.

        Args:
            region_id: The region ID to filter by

        Returns:
            List of MarketDataPoint objects in the region

        """
        cache = self._load_market_data()
        type_ids = self._types_by_region_index.get(region_id, set())
        return [cache[tid] for tid in type_ids]

    def get_types_with_buy_orders(self) -> list[FuzzworkMarketDataPoint]:
        """Get all types that have buy orders in any region.

        Uses O(1) hashmap lookup for optimal performance.

        Returns:
            List of MarketDataPoint objects with buy orders

        """
        cache = self._load_market_data()
        return [cache[tid] for tid in self._types_with_buy_orders_index]

    def get_types_with_sell_orders(self) -> list[FuzzworkMarketDataPoint]:
        """Get all types that have sell orders in any region.

        Uses O(1) hashmap lookup for optimal performance.

        Returns:
            List of MarketDataPoint objects with sell orders

        """
        cache = self._load_market_data()
        return [cache[tid] for tid in self._types_with_sell_orders_index]

    def get_all_market_data(self) -> list[FuzzworkMarketDataPoint]:
        """Get all market data points.

        Returns:
            List of all MarketDataPoint objects

        """
        return list(self._load_market_data().values())

    def filter_by_price_range(
        self,
        min_price: float,
        max_price: float,
        order_type: Literal["buy", "sell"],
        region_id: int | None = None,
    ) -> list[FuzzworkMarketDataPoint]:
        """Filter types by price range.

        Args:
            min_price: Minimum price threshold (inclusive)
            max_price: Maximum price threshold (inclusive)
            order_type: Type of orders to filter ("buy" or "sell")
            region_id: Optional region to filter by. If None, checks all regions.

        Returns:
            List of MarketDataPoint objects matching the criteria

        """
        cache = self._load_market_data()
        results: list[FuzzworkMarketDataPoint] = []

        for market_data in cache.values():
            # Filter by region if specified
            regions_to_check = (
                [market_data.region_data[region_id]]
                if region_id and region_id in market_data.region_data
                else market_data.region_data.values()
            )

            # Check if any region matches the price criteria
            match_found = False
            for region in regions_to_check:
                if order_type == "buy" and region.buy_stats:
                    price = region.buy_stats.weighted_average
                    if min_price <= price <= max_price:
                        match_found = True
                        break
                elif order_type == "sell" and region.sell_stats:
                    price = region.sell_stats.weighted_average
                    if min_price <= price <= max_price:
                        match_found = True
                        break

            if match_found:
                results.append(market_data)

        return results

    def get_snapshot_time(self) -> datetime | None:
        """Get the timestamp when market data was loaded.

        Returns:
            Datetime of snapshot or None if not loaded

        """
        return self._snapshot_time

    def clear_cache(self) -> None:
        """Clear all cached data to free memory."""
        logger.info("Clearing market data cache...")

        # Clear primary cache
        self._market_data_cache = None

        # Clear index hashmaps
        self._types_by_region_index = {}
        self._types_with_buy_orders_index = set()
        self._types_with_sell_orders_index = set()

        # Clear metadata
        self._snapshot_time = None

        logger.info("Market cache cleared")

    @property
    def is_loaded(self) -> bool:
        """Check if market data has been loaded.

        Returns:
            True if cache is populated

        """
        return self._market_data_cache is not None

    def get_cache_stats(self) -> dict[str, int | bool]:
        """Get statistics about cached market data.

        Returns:
            Dictionary with cache sizes and metadata

        """
        return {
            "types": len(self._market_data_cache) if self._market_data_cache else 0,
            "regions": len(self._types_by_region_index),
            "buy_orders": len(self._types_with_buy_orders_index),
            "sell_orders": len(self._types_with_sell_orders_index),
            "indices_built": len(self._types_by_region_index) > 0,
            "is_loaded": self.is_loaded,
        }

    def _load_market_data(self) -> dict[int, FuzzworkMarketDataPoint]:
        """Load and cache all market data from parser.

        Returns:
            Dictionary mapping type_id to MarketDataPoint

        """
        if self._market_data_cache is None:
            logger.info("Loading market data from parser...")
            self._market_data_cache = {}

            for market_data_point in self._parser.load_market_data():
                self._market_data_cache[market_data_point.type_id] = market_data_point
                # Store snapshot time from first data point
                if self._snapshot_time is None:
                    self._snapshot_time = market_data_point.snapshot_time

            logger.info(f"Loaded market data for {len(self._market_data_cache)} types")
            self._build_indices()
        return self._market_data_cache

    def _build_indices(self) -> None:
        """Build hashmap indices for fast lookups.

        Constructs all indices in a single O(n) pass over cached data.
        Must only be called after _market_data_cache is populated.
        """
        assert self._market_data_cache is not None, (
            "Market data cache must be loaded before building indices"
        )

        logger.debug("Building market data indices...")

        # Clear existing indices
        regions_index: dict[int, set[int]] = defaultdict(set)
        buy_orders_set: set[int] = set()
        sell_orders_set: set[int] = set()

        # Build all indices in single pass
        for type_id, market_data in self._market_data_cache.items():
            # Region index
            for region_id in market_data.region_data.keys():
                regions_index[region_id].add(type_id)

            # Buy/sell order indices
            if market_data.has_buy_orders():
                buy_orders_set.add(type_id)

            if market_data.has_sell_orders():
                sell_orders_set.add(type_id)

        # Assign built indices
        self._types_by_region_index = dict(regions_index)
        self._types_with_buy_orders_index = buy_orders_set
        self._types_with_sell_orders_index = sell_orders_set

        logger.debug("Market data indices built successfully")
