"""Net worth calculation and snapshot service.

Calculates character net worth from assets, wallet, market orders, contracts,
and industry jobs.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from data import FuzzworkProvider
from data.repositories import (
    Repository,
    assets,
    contracts,
    journal,
    market_orders,
    networth,
    prices,
)
from models.app import (
    FuzzworkMarketDataPoint,
    FuzzworkMarketStats,
    FuzzworkRegionMarketData,
    NetWorthSnapshot,
)

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class NetWorthService:
    """Calculate and track character net worth.

    Components:
    - Assets
    - Wallet balance
    - Market orders (escrow + sell exposure)
    - Contracts (collateral + price/reward)
    - Industry jobs
    """

    def __init__(
        self,
        esi_client: ESIClient,
        repository: Repository,
        fuzzwork_provider: FuzzworkProvider | None = None,
        settings_manager: Any | None = None,
    ) -> None:
        self._esi_client = esi_client
        self._repo = repository
        self._fuzzwork = fuzzwork_provider
        self._settings = settings_manager
        self._last_used_prices: dict[int, tuple[float, str]] = {}

    def _get_market_price(self, type_id: int) -> float | None:
        """Get market price for a type from Fuzzwork data."""
        if not self._fuzzwork or not self._fuzzwork.is_loaded:
            return None
        market_data = self._fuzzwork.get_market_data(type_id)
        if not market_data or not market_data.region_data:
            return None
        for region_data in market_data.region_data.values():
            if region_data.sell_stats:
                return region_data.sell_stats.median
        return None

    def _get_asset_price(self, asset: Any, type_id: int) -> float | None:
        """Get price for an asset using custom, market, or base price.

        Priority:
        1. Custom price (from settings)
        2. Asset's market_value (if enriched)
        3. Market price (from Fuzzwork)
        4. Base price (from SDE)

        Args:
            asset: Enriched asset object
            type_id: EVE type ID

        Returns:
            Price per unit or None
        """
        custom_price = None
        if self._settings:
            custom_prices = self._settings.get_custom_price(type_id)
            if custom_prices:
                custom_price = custom_prices.get("sell")

        if custom_price is not None and custom_price > 0:
            self._last_used_prices[type_id] = (custom_price, "custom")
            return custom_price

        market_value = getattr(asset, "market_value", None)
        if market_value is not None and market_value > 0:
            self._last_used_prices[type_id] = (market_value, "asset")
            return market_value

        market_price = self._get_market_price(type_id)
        if market_price is not None and market_price > 0:
            self._last_used_prices[type_id] = (market_price, "market")
            return market_price

        base_price = getattr(asset, "base_price", None)
        if base_price is not None and base_price > 0:
            self._last_used_prices[type_id] = (base_price, "base")
            return base_price

        return None

    async def calculate_networth(self, character_id: int) -> NetWorthSnapshot:
        """Calculate net worth snapshot for a character.

        Calculates net worth from data already stored in the repository.

        Args:
            character_id: Character ID to calculate net worth for
        Returns:
            NetWorthSnapshot with calculated values
        """
        self._last_used_prices = {}
        snapshot_time = datetime.now(UTC)

        wallet_balance = await journal.get_current_balance(self._repo, character_id)
        if wallet_balance is None:
            wallet_balance = 0.0
            logger.warning(
                "No wallet balance available for character %d, using 0",
                character_id,
            )

        market_escrow = 0.0
        market_sell_value = 0.0
        try:
            exposure = await market_orders.calculate_market_exposure(
                self._repo, character_id
            )
            market_escrow = float(exposure.get("total_escrow", 0.0))
            market_sell_value = float(exposure.get("sell_exposure", 0.0))
        except Exception:
            logger.debug("Market exposure calc failed", exc_info=True)

        contract_collateral = 0.0
        contract_value = 0.0
        try:
            active_contracts = await contracts.get_active_contracts(
                self._repo, character_id
            )
            for c in active_contracts:
                if c.collateral:
                    contract_collateral += float(c.collateral)
                if c.price:
                    contract_value += float(c.price)
                elif c.reward:
                    contract_value += float(c.reward)
        except Exception:
            logger.debug("Contract value calc failed", exc_info=True)

        total_asset_value = 0.0
        try:
            raw_assets = await assets.get_current_assets(self._repo, character_id)
            for asset in raw_assets:
                type_id = asset.type_id
                quantity = asset.quantity
                is_blueprint_copy = asset.is_blueprint_copy

                if is_blueprint_copy or quantity <= 0:
                    continue

                per_unit = self._get_asset_price(asset, type_id)
                if per_unit and per_unit > 0:
                    stack_value = per_unit * quantity
                    total_asset_value += stack_value
        except Exception:
            logger.debug("Asset valuation failed", exc_info=True)

        industry_job_value = 0.0

        return NetWorthSnapshot(
            snapshot_id=0,
            character_id=character_id,
            snapshot_time=snapshot_time,
            total_asset_value=total_asset_value,
            wallet_balance=wallet_balance,
            market_escrow=market_escrow,
            market_sell_value=market_sell_value,
            contract_collateral=contract_collateral,
            contract_value=contract_value,
            industry_job_value=industry_job_value,
        )

    async def save_networth_snapshot(self, character_id: int) -> int:
        """Calculate and save a net worth snapshot.

        Snapshots data already in the repository.

        Args:
            character_id: Character ID

        Returns:
            Snapshot ID
        """
        snapshot = await self.calculate_networth(character_id)

        asset_snapshot_id = None
        try:
            raw_assets = await assets.get_current_assets(self._repo, character_id)
            if raw_assets:
                asset_snapshot_id = await assets.save_snapshot(
                    self._repo,
                    character_id,
                    raw_assets,
                    notes=f"Networth snapshot at {snapshot.snapshot_time}",
                )
        except Exception:
            logger.debug("Failed to save asset snapshot", exc_info=True)

        price_snapshot_id = None
        if self._last_used_prices and self._fuzzwork:
            try:
                market_data: list[FuzzworkMarketDataPoint] = []
                for type_id, (price_value, source) in self._last_used_prices.items():
                    region_data = {}

                    fuzz_data = self._fuzzwork.get_market_data(type_id)
                    if fuzz_data and fuzz_data.region_data:
                        region_data = fuzz_data.region_data

                    if source == "custom" or not region_data:
                        region_data[0] = FuzzworkRegionMarketData(
                            region_id=0,
                            sell_stats=FuzzworkMarketStats(
                                weighted_average=price_value,
                                max_price=price_value,
                                min_price=price_value,
                                stddev=0.0,
                                median=price_value,
                                volume=0,
                                num_orders=0,
                                five_percent=price_value,
                            ),
                            buy_stats=None,
                        )

                    market_data.append(
                        FuzzworkMarketDataPoint(
                            type_id=type_id,
                            snapshot_time=snapshot.snapshot_time,
                            region_data=region_data,
                        )
                    )

                if market_data:
                    custom_count = sum(
                        1
                        for _, (_, src) in self._last_used_prices.items()
                        if src == "custom"
                    )
                    price_snapshot_id = await prices.save_snapshot(
                        self._repo,
                        market_data,
                        notes=f"Networth snapshot for character {character_id} "
                        f"(includes {custom_count} custom prices)",
                    )
            except Exception:
                logger.exception("Failed to save price snapshot", exc_info=True)

        snapshot_id = await networth.save_snapshot(self._repo, character_id, snapshot)
        logger.info(
            "Saved net worth snapshot %d for character %d "
            "(asset_snapshot=%s, price_snapshot=%s)",
            snapshot_id,
            character_id,
            asset_snapshot_id,
            price_snapshot_id,
        )
        return snapshot_id

    async def get_networth_trend(
        self, character_id: int, days: int = 30
    ) -> list[tuple[datetime, float]]:
        """Get net worth trend over time."""
        history = await networth.get_networth_history(
            self._repo, character_id, limit=days
        )
        return [(snap.snapshot_time, snap.total_net_worth) for snap in history]

    async def compare_networth(self, character_ids: list[int]) -> dict:
        """Compare net worth across multiple characters."""
        results: dict[int, dict[str, Any]] = {}
        for cid in character_ids:
            latest = await networth.get_latest_networth(self._repo, cid)
            if latest:
                results[cid] = {
                    "total_net_worth": latest.total_net_worth,
                    "snapshot_time": latest.snapshot_time,
                }
            else:
                results[cid] = {
                    "total_net_worth": 0.0,
                    "snapshot_time": None,
                }
        return results

    async def get_latest_networth(self, character_id: int) -> NetWorthSnapshot | None:
        """Get the most recent net worth snapshot for a character."""
        return await networth.get_latest_networth(self._repo, character_id)

    async def get_networth_history(
        self, character_id: int, limit: int = 30
    ) -> list[NetWorthSnapshot]:
        """Get net worth history for a character."""
        return await networth.get_networth_history(self._repo, character_id, limit)


__all__ = ["NetWorthService"]
