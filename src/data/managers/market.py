"""Market data manager for high-level market price access and caching."""

import logging
from collections import defaultdict

from src.data.loaders.fuzzwork_csv import FuzzworkCSVLoader
from src.models.eve import MarketPrice

logger = logging.getLogger(__name__)


class MarketDataManager:
    """Manager for market data with caching and optimized query capabilities.

    This manager provides:
    - Primary caches: Direct lookups by type/region/order type
    - Index hashmaps: Fast filtered queries
    - Price retrieval methods for buy/sell orders
    """

    def __init__(self, loader: FuzzworkCSVLoader):
        """Initialize the market data manager.

        Args:
            loader: FuzzworkCSVLoader instance for loading market data.

        """
        self._loader = loader

        # Primary cache - all market prices by composite key
        # Key format: (type_id, region_id, is_buy_order)
        self._prices_cache: dict[tuple[int, int, bool], MarketPrice] | None = None

        # Index hashmaps for fast queries
        # Type ID -> list of MarketPrice keys
        self._prices_by_type_index: dict[int, list[tuple[int, int, bool]]] = {}
        # Region ID -> list of MarketPrice keys
        self._prices_by_region_index: dict[int, list[tuple[int, int, bool]]] = {}

    def _load_prices(self) -> dict[tuple[int, int, bool], MarketPrice]:
        """Load and cache all market prices."""
        if self._prices_cache is None:
            logger.info("Loading market prices from Fuzzwork data...")
            self._prices_cache = {}

            for price in self._loader.load_market_prices():
                key = (price.type_id, price.region_id, price.is_buy_order)
                self._prices_cache[key] = price

            logger.info(f"Loaded {len(self._prices_cache)} market prices")
            self._build_indices()

        return self._prices_cache

    def _build_indices(self) -> None:
        """Build hashmap indices for fast lookups.

        Must only be called after _prices_cache is populated.
        """
        assert self._prices_cache is not None, (
            "Prices cache must be loaded before building indices"
        )

        logger.debug("Building market price indices...")

        # Clear and rebuild indices
        type_index: dict[int, list[tuple[int, int, bool]]] = defaultdict(list)
        region_index: dict[int, list[tuple[int, int, bool]]] = defaultdict(list)

        for key in self._prices_cache.keys():
            type_id, region_id, _ = key  # _ is is_buy_order

            # Build type index
            type_index[type_id].append(key)

            # Build region index
            region_index[region_id].append(key)

        # Assign built indices
        self._prices_by_type_index = dict(type_index)
        self._prices_by_region_index = dict(region_index)

        logger.debug(
            f"Market price indices built: {len(self._prices_by_type_index)} "
            f"types, {len(self._prices_by_region_index)} regions"
        )

    # Public query methods

    def get_price(
        self,
        type_id: int,
        region_id: int,
        is_buy_order: bool = False,
    ) -> MarketPrice | None:
        """Get a specific market price by type, region, and order type.

        Args:
            type_id: The type ID to look up
            region_id: The region ID to look up
            is_buy_order: True for buy orders, False for sell orders

        Returns:
            MarketPrice object or None if not found

        """
        key = (type_id, region_id, is_buy_order)
        return self._load_prices().get(key)

    def get_weighted_average(
        self,
        type_id: int,
        region_id: int | None = None,
        is_buy_order: bool = False,
    ) -> float | None:
        """Get the weighted average price for a type.

        Args:
            type_id: The type ID to look up
            region_id: Optional region ID. If None, averages all regions.
            is_buy_order: True for buy orders, False for sell orders

        Returns:
            Weighted average price or None if not found

        """
        if region_id is not None:
            price = self.get_price(type_id, region_id, is_buy_order)
            return price.weighted_average if price else None

        # Average across all regions
        prices = self.get_all_prices_for_type(type_id, is_buy_order=is_buy_order)
        if not prices:
            return None

        # Calculate volume-weighted average across all regions
        total_value = sum(p.weighted_average * p.volume for p in prices)
        total_volume = sum(p.volume for p in prices)

        return total_value / total_volume if total_volume > 0 else None

    def get_best_price(
        self,
        type_id: int,
        region_id: int | None = None,
        is_buy_order: bool = False,
    ) -> float | None:
        """Get the best price for a type.

        For buy orders, returns the highest buy price.
        For sell orders, returns the lowest sell price.

        Args:
            type_id: The type ID to look up
            region_id: Optional region ID. If None, searches all regions.
            is_buy_order: True for buy orders, False for sell orders

        Returns:
            Best price or None if not found

        """
        if region_id is not None:
            price = self.get_price(type_id, region_id, is_buy_order)
            return price.get_best_price() if price else None

        # Find best price across all regions
        prices = self.get_all_prices_for_type(type_id, is_buy_order=is_buy_order)
        if not prices:
            return None

        if is_buy_order:
            # Highest buy price
            return max(p.max_val for p in prices)
        # Lowest sell price
        return min(p.min_val for p in prices)

    def get_all_prices_for_type(
        self,
        type_id: int,
        region_id: int | None = None,
        is_buy_order: bool | None = None,
    ) -> list[MarketPrice]:
        """Get all market prices for a specific type.

        Args:
            type_id: The type ID to filter by
            region_id: Optional region ID to filter by
            is_buy_order: Optional order type filter (True/False/None for all)

        Returns:
            List of MarketPrice objects matching the criteria

        """
        prices_cache = self._load_prices()
        keys = self._prices_by_type_index.get(type_id, [])

        results = []
        for key in keys:
            _, key_region, key_is_buy = key

            # Apply filters
            if region_id is not None and key_region != region_id:
                continue
            if is_buy_order is not None and key_is_buy != is_buy_order:
                continue

            results.append(prices_cache[key])

        return results

    def get_all_prices_for_region(
        self, region_id: int, is_buy_order: bool | None = None
    ) -> list[MarketPrice]:
        """Get all market prices for a specific region.

        Args:
            region_id: The region ID to filter by
            is_buy_order: Optional order type filter (True/False/None for all)

        Returns:
            List of MarketPrice objects in the region

        """
        prices_cache = self._load_prices()
        keys = self._prices_by_region_index.get(region_id, [])

        if is_buy_order is None:
            return [prices_cache[key] for key in keys]

        return [
            prices_cache[key]
            for key in keys
            if key[2] == is_buy_order  # key[2] is is_buy_order
        ]

    def get_available_regions_for_type(self, type_id: int) -> list[int]:
        """Get list of region IDs where a type has market data.

        Args:
            type_id: The type ID to check

        Returns:
            List of region IDs with market data for this type

        """
        keys = self._prices_by_type_index.get(type_id, [])
        regions = {key[1] for key in keys}  # key[1] is region_id
        return sorted(regions)

    def has_market_data(self, type_id: int, region_id: int | None = None) -> bool:
        """Check if market data exists for a type.

        Args:
            type_id: The type ID to check
            region_id: Optional region ID to check

        Returns:
            True if market data exists

        """
        if region_id is None:
            return type_id in self._prices_by_type_index

        # Check specific region
        key_buy = (type_id, region_id, True)
        key_sell = (type_id, region_id, False)
        prices_cache = self._load_prices()

        return key_buy in prices_cache or key_sell in prices_cache

    def clear_cache(self) -> None:
        """Clear all cached data to free memory."""
        logger.info("Clearing market data cache...")

        self._prices_cache = None
        self._prices_by_type_index = {}
        self._prices_by_region_index = {}

        logger.info("Market data cache cleared")

    @property
    def is_loaded(self) -> bool:
        """Check if market data has been loaded.

        Returns:
            True if cache is populated

        """
        return self._prices_cache is not None

    def get_cache_stats(self) -> dict[str, int | bool]:
        """Get statistics about cached market data.

        Returns:
            Dictionary with cache sizes and status

        """
        return {
            "total_prices": len(self._prices_cache) if self._prices_cache else 0,
            "unique_types": len(self._prices_by_type_index),
            "unique_regions": len(self._prices_by_region_index),
            "is_loaded": self.is_loaded,
        }
