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
from data.repositories.schemas import CREATE_NETWORTH_SNAPSHOT_GROUPS_TABLE
from models.app import (
    AssetLocationOption,
    FuzzworkMarketDataPoint,
    FuzzworkMarketStats,
    FuzzworkRegionMarketData,
    LocationInfo,
    NetWorthSnapshot,
)
from models.eve.asset import EveAsset

if TYPE_CHECKING:
    from data.clients import ESIClient
    from services.location_service import LocationService

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
        sde_provider: Any | None = None,
        location_service: LocationService | None = None,
    ) -> None:
        self._esi_client = esi_client
        self._repo = repository
        self._fuzzwork = fuzzwork_provider
        self._settings = settings_manager
        self._last_used_prices: dict[int, tuple[float, str]] = {}
        self._schema_ready: bool = False
        self._sde = sde_provider
        self._location_service = location_service

    async def _ensure_schema(self) -> None:
        """Ensure networth snapshot groups table exists."""
        if self._schema_ready:
            return
        try:
            if not await self._repo.table_exists("networth_snapshot_groups"):
                await self._repo.execute(CREATE_NETWORTH_SNAPSHOT_GROUPS_TABLE)
            await self._repo.commit()
            self._schema_ready = True
        except Exception:
            logger.debug("Networth schema initialization failed", exc_info=True)

    def _get_market_price(self, type_id: int) -> float | None:
        """Get market price for a type from Fuzzwork data respecting user preferences.

        Respects:
        - Trade hub selection (Jita, Amarr, Dodixie, Rens, Hek)
        - Price type (buy, sell, weighted)
        """
        if not self._fuzzwork or not self._fuzzwork.is_loaded:
            return None
        market_data = self._fuzzwork.get_market_data(type_id)
        if not market_data or not market_data.region_data:
            return None

        # Get user preferences for market valuation
        trade_hub = (
            self._settings.get_market_source_station() if self._settings else "jita"
        )
        price_type = (
            self._settings.get_market_price_type() if self._settings else "sell"
        )

        # Map trade hub names to region IDs
        hub_to_region = {
            "jita": 10000002,  # The Forge
            "amarr": 10000043,  # Domain
            "dodixie": 10000032,  # Sinq Laison
            "rens": 10000030,  # Heimatar
            "hek": 10000042,  # Metropolis
        }

        preferred_region_id = hub_to_region.get(
            trade_hub.lower(), 10000002
        )  # Default to Jita

        # Try to get data from preferred region first
        region_data = market_data.region_data.get(preferred_region_id)

        # Fallback to any available region if preferred not found
        if not region_data:
            for region_data in market_data.region_data.values():
                if region_data:
                    break
            else:
                return None

        # Extract price based on user preference
        if price_type == "buy" and region_data.buy_stats:
            return region_data.buy_stats.median
        if price_type == "sell" and region_data.sell_stats:
            return region_data.sell_stats.median
        if price_type == "weighted":
            # Weighted average: default 30% buy, 70% sell
            weighted_ratio = (
                self._settings.get_market_weighted_buy_ratio()
                if self._settings
                else 0.3
            )
            buy_price = region_data.buy_stats.median if region_data.buy_stats else 0
            sell_price = region_data.sell_stats.median if region_data.sell_stats else 0
            if buy_price > 0 and sell_price > 0:
                return (buy_price * weighted_ratio) + (
                    sell_price * (1 - weighted_ratio)
                )
            if sell_price > 0:
                return sell_price
            if buy_price > 0:
                return buy_price

        # Final fallback to sell price
        if region_data.sell_stats:
            return region_data.sell_stats.median

        return None

    async def _get_price_history_price(self, type_id: int) -> float | None:
        """Fallback to latest stored price snapshot when live market data is missing."""
        try:
            record = await prices.get_latest_jita_price(self._repo, type_id)
            if record is None:
                return None
            candidates = [
                record.sell_weighted_average,
                record.sell_median,
                record.sell_max_price,
                record.sell_min_price,
            ]
            price_val = next((float(v) for v in candidates if v is not None), None)
            if price_val is not None and price_val > 0:
                self._last_used_prices[type_id] = (price_val, "history")
                return price_val
        except Exception:
            logger.debug("Price history lookup failed for %s", type_id, exc_info=True)
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

        # Fallback: look up base price from SDE provider if available
        if self._sde is not None:
            try:
                eve_type = self._sde.get_type_by_id(type_id)
                if eve_type and getattr(eve_type, "base_price", None):
                    bp = float(eve_type.base_price)
                    if bp > 0:
                        self._last_used_prices[type_id] = (bp, "base")
                        return bp
            except Exception:
                logger.debug("SDE base price lookup failed for %s", type_id)

        return None

    async def calculate_assets_for_locations(
        self, character_id: int, include_locations: list[int]
    ) -> float:
        """Calculate asset value limited to specific location IDs using latest data."""

        if not include_locations:
            return 0.0
        total = 0.0
        include_set = {int(loc) for loc in include_locations if loc is not None}
        try:
            raw_assets = await assets.get_current_assets(self._repo, character_id)
            by_item_id = {asset.item_id: asset for asset in raw_assets}
            for asset in raw_assets:
                try:
                    if asset.is_blueprint_copy or asset.quantity <= 0:
                        continue
                    if include_set:
                        root_id, _root_type = self._find_root_location(
                            asset, by_item_id
                        )
                        if root_id is None or int(root_id) not in include_set:
                            continue
                    per_unit = self._get_asset_price(asset, asset.type_id)
                    if per_unit is None:
                        per_unit = await self._get_price_history_price(asset.type_id)
                    if per_unit and per_unit > 0:
                        total += per_unit * asset.quantity
                except Exception:
                    logger.debug(
                        "Failed to value asset %s for %s",
                        getattr(asset, "item_id", None),
                        character_id,
                        exc_info=True,
                    )
        except Exception:
            logger.debug(
                "Failed to compute filtered assets for character %s",
                character_id,
                exc_info=True,
            )
        return total

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

        # PLEX is account-level data stored separately in account_plex_snapshots table.
        # PLEX snapshots are created separately during refresh operations.
        plex_vault = 0.0
        account_id = None
        if self._settings and hasattr(self._settings, "get_account_for_character"):
            account_id = self._settings.get_account_for_character(character_id)

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
                if per_unit is None:
                    per_unit = await self._get_price_history_price(type_id)
                if per_unit and per_unit > 0:
                    stack_value = per_unit * quantity
                    total_asset_value += stack_value
        except Exception:
            logger.debug("Asset valuation failed", exc_info=True)

        industry_job_value = 0.0

        return NetWorthSnapshot(
            snapshot_id=0,
            character_id=character_id,
            account_id=account_id,
            snapshot_group_id=None,
            snapshot_time=snapshot_time,
            total_asset_value=total_asset_value,
            wallet_balance=wallet_balance,
            market_escrow=market_escrow,
            market_sell_value=market_sell_value,
            contract_collateral=contract_collateral,
            contract_value=contract_value,
            industry_job_value=industry_job_value,
            plex_vault=plex_vault,
        )

    @staticmethod
    def _find_root_location(
        asset: EveAsset, by_item_id: dict[int, EveAsset]
    ) -> tuple[int | None, str | None]:
        """Walk parent chain to find the first non-item location."""

        loc_id = asset.location_id
        loc_type = asset.location_type

        if loc_type != "item":
            return loc_id, loc_type

        max_hops = 64
        hops = 0
        while loc_type == "item" and hops < max_hops:
            parent = by_item_id.get(loc_id)
            if parent is None:
                # Infer based on numeric range if parent row missing
                if loc_id >= 1_000_000_000_000:
                    return loc_id, "structure"
                if 60000000 <= loc_id < 70000000:
                    return loc_id, "station"
                if 30000000 <= loc_id < 40000000:
                    return loc_id, "solar_system"
                return None, None
            loc_id = parent.location_id
            loc_type = parent.location_type
            hops += 1

        if loc_type == "item":
            return None, None
        return loc_id, loc_type

    async def list_asset_locations(
        self, character_ids: list[int] | None = None
    ) -> list[AssetLocationOption]:
        """Return all known root asset locations for the provided characters."""

        if not character_ids:
            rows = await self._repo.fetchall(
                "SELECT DISTINCT character_id FROM current_assets"
            )
            character_ids = [
                int(row["character_id"])
                for row in rows
                if row["character_id"] is not None
            ]

        if not character_ids:
            return []

        stats: dict[int, dict[str, Any]] = {}
        for cid in character_ids:
            raw_assets = await assets.get_current_assets(self._repo, cid)
            if not raw_assets:
                continue
            by_item = {asset.item_id: asset for asset in raw_assets}
            for asset in raw_assets:
                root_id, root_type = self._find_root_location(asset, by_item)
                if root_id is None:
                    continue
                entry = stats.setdefault(
                    int(root_id),
                    {
                        "asset_count": 0,
                        "characters": set(),
                        "location_type": root_type or "",
                    },
                )
                entry["asset_count"] += 1
                entry["characters"].add(int(cid))
                if root_type and not entry.get("location_type"):
                    entry["location_type"] = root_type

        if not stats:
            return []

        resolved: dict[int, LocationInfo] = {}
        location_ids = list(stats.keys())
        if self._location_service is not None:
            try:
                resolved = await self._location_service.resolve_locations_bulk(
                    location_ids,
                    character_id=character_ids[0],
                    refresh_stale=False,
                )
            except Exception:
                logger.debug("Failed to resolve asset location names", exc_info=True)
                resolved = {}

        options: list[AssetLocationOption] = []
        for loc_id, entry in stats.items():
            info = resolved.get(loc_id)
            display_name = None
            system_name = None
            category = entry.get("location_type") or ""
            if info is not None:
                display_name = info.custom_name or info.name
                category = info.category or category
                if info.solar_system_id is not None:
                    if self._sde is not None:
                        system_name = self._sde.get_solar_system_name(
                            info.solar_system_id
                        )
                    if not system_name:
                        system_name = str(info.solar_system_id)

            if not display_name:
                display_name = f"Location {loc_id}"

            options.append(
                AssetLocationOption(
                    location_id=loc_id,
                    display_name=display_name,
                    location_type=str(category or ""),
                    asset_count=int(entry["asset_count"]),
                    character_count=len(entry["characters"]),
                    system_name=system_name,
                )
            )

        options.sort(key=lambda opt: (opt.display_name.lower(), opt.location_id))
        return options

    async def create_snapshot_group(
        self,
        account_id: int | None = None,
        refresh_source: str | None = None,
        label: str | None = None,
    ) -> int:
        """Create a snapshot group to tie together concurrent snapshots.

        Args:
            account_id: Optional account ID (set for 'account' refresh source)
            refresh_source: Type of refresh ('refresh_all', 'account', etc.)
            label: Optional label for the group

        Returns:
            snapshot_group_id of the created group
        """

        await self._ensure_schema()
        cursor = await self._repo.execute(
            """
            INSERT INTO networth_snapshot_groups (account_id, refresh_source, created_at, label)
            VALUES (?, ?, ?, ?)
            """,
            (account_id, refresh_source, datetime.now(UTC).isoformat(), label),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("Failed to create snapshot group")
        await self._repo.commit()
        return int(cursor.lastrowid)

    async def update_snapshot(self, snapshot: NetWorthSnapshot) -> None:
        """Persist edits to an existing net worth snapshot."""

        await self._ensure_schema()
        await networth.update_snapshot(self._repo, snapshot)

    async def delete_snapshot(self, snapshot_id: int) -> None:
        """Delete a snapshot by ID."""

        await self._ensure_schema()
        await networth.delete_snapshot(self._repo, snapshot_id)

    async def save_networth_snapshot(
        self, character_id: int, snapshot_group_id: int | None = None
    ) -> int:
        """Calculate and save a net worth snapshot.

        Snapshots data already in the repository.

        Args:
            character_id: Character ID

        Returns:
            Snapshot ID
        """
        await self._ensure_schema()

        # Ensure snapshots always belong to a group so graph aggregation picks them up
        if snapshot_group_id is None:
            try:
                snapshot_group_id = await self.create_snapshot_group(
                    account_id=None,
                    refresh_source="manual",
                    label="Manual snapshot",
                )
                logger.debug(
                    "Created snapshot group %s for manual networth save",
                    snapshot_group_id,
                )
            except Exception:
                logger.debug(
                    "Failed to create snapshot group for manual save", exc_info=True
                )

        snapshot = await self.calculate_networth(character_id)
        snapshot.snapshot_group_id = snapshot_group_id

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

        # Ensure contract items are saved
        try:
            active_contracts_list = await contracts.get_active_contracts(
                self._repo, character_id
            )
            for contract in active_contracts_list:
                try:
                    # Check if items already exist
                    existing_items = await contracts.get_contract_items(
                        self._repo, contract.contract_id
                    )
                    if not existing_items:
                        logger.debug(
                            "Contract %d has no items saved, skipping",
                            contract.contract_id,
                        )
                except Exception:
                    logger.debug(
                        "Failed to check contract items for %d",
                        contract.contract_id,
                        exc_info=True,
                    )
        except Exception:
            logger.debug("Failed to verify contract items", exc_info=True)

        price_snapshot_id = None
        if self._last_used_prices and self._fuzzwork:
            try:
                # Check if we should save a price snapshot
                custom_count = sum(
                    1
                    for _, (_, src) in self._last_used_prices.items()
                    if src == "custom"
                )

                should_save = False

                # Always save if there are custom prices
                if custom_count > 0:
                    should_save = True
                    logger.debug(
                        "Price snapshot needed: %d custom prices used", custom_count
                    )
                else:
                    # Check if Fuzzwork data is newer than last snapshot
                    fuzz_time = self._fuzzwork.get_snapshot_time()
                    if fuzz_time:
                        recent_snapshots = await prices.get_snapshots(
                            self._repo, limit=1
                        )
                        if not recent_snapshots:
                            should_save = True
                            logger.debug("Price snapshot needed: no previous snapshots")
                        else:
                            last_snapshot_time = recent_snapshots[0].snapshot_time
                            if fuzz_time > last_snapshot_time:
                                should_save = True
                                logger.debug(
                                    "Price snapshot needed: Fuzzwork data updated (fuzz=%s > last=%s)",
                                    fuzz_time.isoformat(),
                                    last_snapshot_time.isoformat(),
                                )
                            else:
                                logger.debug(
                                    "Skipping price snapshot: Fuzzwork data unchanged (fuzz=%s <= last=%s)",
                                    fuzz_time.isoformat(),
                                    last_snapshot_time.isoformat(),
                                )

                if should_save:
                    market_data: list[FuzzworkMarketDataPoint] = []
                    for type_id, (
                        price_value,
                        source,
                    ) in self._last_used_prices.items():
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
                        price_snapshot_id = await prices.save_snapshot(
                            self._repo,
                            market_data,
                            notes=f"Networth snapshot for character {character_id} "
                            f"(includes {custom_count} custom prices)",
                            snapshot_group_id=snapshot_group_id,
                        )
            except Exception:
                logger.exception("Failed to save price snapshot", exc_info=True)

        try:
            # Pass account and group to persistence
            snapshot_id = await networth.save_snapshot(
                self._repo,
                character_id,
                snapshot,
                account_id=snapshot.account_id,
                snapshot_group_id=snapshot_group_id,
            )
        except Exception:
            logger.exception("Failed to persist networth snapshot")
            raise
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
        await self._ensure_schema()
        history = await networth.get_networth_history(
            self._repo, character_id, limit=days
        )
        return [(snap.snapshot_time, snap.total_net_worth) for snap in history]

    async def compare_networth(self, character_ids: list[int]) -> dict:
        """Compare net worth across multiple characters."""
        await self._ensure_schema()
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

    async def save_account_plex_snapshot(
        self,
        account_id: int,
        plex_units: int,
        plex_unit_price: float,
        snapshot_group_id: int | None = None,
    ) -> int:
        """Save an account-level PLEX snapshot.

        Args:
            account_id: Account ID
            plex_units: PLEX units in vault
            plex_unit_price: Market price per PLEX unit
            snapshot_group_id: Optional snapshot group to associate with

        Returns:
            plex_snapshot_id of the created snapshot
        """
        await self._ensure_schema()
        return await networth.save_account_plex_snapshot(
            self._repo,
            account_id,
            plex_units,
            plex_unit_price,
            snapshot_group_id,
            snapshot_time=datetime.now(UTC),
        )

    async def get_latest_networth(self, character_id: int) -> NetWorthSnapshot | None:
        """Get the most recent net worth snapshot for a character."""
        await self._ensure_schema()
        return await networth.get_latest_networth(self._repo, character_id)

    async def get_networth_history(
        self,
        character_id: int,
        *,
        limit: int | None = 30,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NetWorthSnapshot]:
        """Get net worth history for a character."""
        await self._ensure_schema()
        return await networth.get_networth_history(
            self._repo,
            character_id,
            limit=limit,
            start=start,
            end=end,
        )

    async def get_snapshots_for_group(
        self, snapshot_group_id: int, character_ids: list[int] | None = None
    ) -> list[NetWorthSnapshot]:
        """Return, for each character, the latest snapshot whose snapshot_group_id <= target.

        Acts as a thin wrapper around the repository helper that implements the
        ROW_NUMBER() windowing query to pick one snapshot per character.
        """
        await self._ensure_schema()
        return await networth.get_snapshots_for_group(
            self._repo, snapshot_group_id, character_ids
        )

    async def get_snapshots_up_to_time(
        self, target_time: datetime, character_ids: list[int] | None = None
    ) -> list[NetWorthSnapshot]:
        """Return, for each character, the latest snapshot whose snapshot_time <= target_time.

        Works with both grouped and legacy (ungrouped) snapshots. Returns at most
        one snapshot per character.
        """
        await self._ensure_schema()
        return await networth.get_snapshots_up_to_time(
            self._repo, target_time, character_ids
        )


__all__ = ["NetWorthService"]
