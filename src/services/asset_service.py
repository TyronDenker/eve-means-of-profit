"""Asset application service.

Handles asset-related business logic including enrichment with SDE data,
location resolution, and asset management operations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data import SDEProvider
    from data.clients import ESIClient
    from data.repositories import Repository
    from services.location_service import LocationService

from data.repositories import assets as asset_repo
from models.app import EnrichedAsset
from models.eve import EveAsset

logger = logging.getLogger(__name__)


class AssetService:
    """Application service for asset-related operations."""

    def __init__(
        self,
        sde_provider: SDEProvider,
        location_service: LocationService,
        repository: Repository,
        esi_client: ESIClient | None = None,
    ):
        """Initialize asset service.

        Args:
            sde_facade: SDE facade for type/group/category data
            location_service: Service for resolving locations
            repository: Repository for persistence
        """
        self._sde = sde_provider
        self._location_service = location_service
        self._repo = repository
        self._esi = esi_client

    async def get_all_enriched_assets(
        self,
        character_id: int,
        character_name: str,
        resolve_locations: bool = True,
        refresh_locations: bool = True,
    ) -> list[EnrichedAsset]:
        """Get enriched assets for a character from the repository.

        Services must not read directly from clients or frontend cache.
        This method reads current assets from the repository's
        current_assets table, then enriches them.

        Args:
            character_id: Character ID
            character_name: Character name for display
            resolve_locations: Whether to resolve location names
            refresh_locations: Whether to refresh stale location cache entries.
                Set to False for fast startup (use cached names only).

        Returns:
            List of enriched assets with SDE data and location info
        """
        # Fetch current assets from repository
        assets = await asset_repo.get_current_assets(self._repo, character_id)
        # Index assets by item_id for parent traversal
        by_item_id: dict[int, EveAsset] = {a.item_id: a for a in assets}

        # Build set of root location IDs to resolve
        root_ids: set[int] = set()
        root_for_asset: dict[int, int] = {}
        for a in assets:
            rid, rtype = self._find_root_location(a, by_item_id)
            if rid is not None and rtype is not None and rtype != "item":
                root_ids.add(rid)
                root_for_asset[a.item_id] = rid

        # Resolve locations
        locations = {}
        if resolve_locations:
            locations = await self._location_service.resolve_locations_bulk(
                list(root_ids),
                character_id=character_id,
                refresh_stale=refresh_locations,
            )

        # Create enriched assets
        enriched_assets = []
        for asset in assets:
            enriched = self._enrich_asset(asset, character_id, character_name)
            rid = root_for_asset.get(asset.item_id)
            if rid is not None:
                loc_info = locations.get(rid)
                if loc_info is not None:
                    self._apply_location_info(enriched, loc_info)
            enriched_assets.append(enriched)

        return enriched_assets

    async def sync_assets(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> int:
        """Refresh assets from ESI and update repository current_assets.

        Services should request data updates via clients, then store in the
        repository. Subsequent reads must come from the repository.

        Args:
            character_id: Character ID to refresh
            use_cache: Whether to allow ETag/HTTP cache
            bypass_cache: Force fresh network fetch

        Returns:
            Number of assets stored in current_assets
        """
        if self._esi is None:
            raise RuntimeError("ESI client not configured in AssetService")

        try:
            result = await self._esi.assets.get_assets(
                character_id,
                use_cache=use_cache,
                bypass_cache=bypass_cache,
            )
            assets, headers = result if isinstance(result, tuple) else (result, {})
        except Exception:
            logger.exception("Failed to fetch assets from ESI for %s", character_id)
            raise

        # Always persist a snapshot to keep current_assets and history in sync
        try:
            snapshot_id = await asset_repo.save_snapshot(
                self._repo,
                character_id,
                assets,
                notes=f"ESI refresh (etag={headers.get('etag')})",
            )
            logger.info(
                "Saved asset snapshot %s and updated current_assets for character %d with %d items",
                snapshot_id,
                character_id,
                len(assets),
            )
        except Exception:
            logger.exception(
                "Failed to snapshot assets; falling back to current update"
            )
            await asset_repo.update_current_assets(self._repo, character_id, assets)
            await self._repo.commit()
        return len(assets)

    def _enrich_asset(
        self, asset: EveAsset, character_id: int, character_name: str = ""
    ) -> EnrichedAsset:
        """Enrich a raw asset with SDE data.

        Args:
            asset: Raw asset from ESI
            character_id: Character ID owning this asset
            character_name: Character name for owner display

        Returns:
            Enriched asset with SDE data
        """
        # Start with basic ESI data
        enriched = EnrichedAsset(
            item_id=asset.item_id,
            type_id=asset.type_id,
            quantity=asset.quantity,
            location_id=asset.location_id,
            location_type=asset.location_type,
            location_flag=asset.location_flag,
            is_singleton=asset.is_singleton,
            is_blueprint_copy=asset.is_blueprint_copy,
            owner_character_id=character_id,
            owner_character_name=character_name,
        )

        try:
            eve_type = self._sde.get_type_by_id(asset.type_id)
            if eve_type:
                enriched.type_name = eve_type.name or ""
                enriched.volume = eve_type.volume or 0.0
                enriched.packaged_volume = None
                enriched.base_price = eve_type.base_price

                # Get group info
                if eve_type.group_id:
                    enriched.group_id = eve_type.group_id
                    group = self._sde.get_group_by_id(eve_type.group_id)
                    if group:
                        enriched.group_name = group.name or ""
                        enriched.category_id = group.category_id

                        # Get category info
                        category = self._sde.get_category_by_id(group.category_id)
                        if category:
                            enriched.category_name = category.name or ""
        except Exception:
            logger.debug(
                "Failed to enrich asset %s (type %s)",
                asset.item_id,
                asset.type_id,
                exc_info=True,
            )

        return enriched

    def _apply_location_info(self, asset: EnrichedAsset, loc_info) -> None:
        """Apply location information to an enriched asset.

        Args:
            asset: EnrichedAsset to update
            loc_info: LocationInfo from location service
        """
        # Apply location name based on category
        if loc_info.category == "station":
            asset.station_name = loc_info.name
            # Stations have system info - resolve it
            if loc_info.solar_system_id:
                asset.system_id = loc_info.solar_system_id
                system_name = self._sde.get_solar_system_name(loc_info.solar_system_id)
                if system_name:
                    asset.system_name = system_name
        elif loc_info.category == "solar_system":
            asset.system_id = loc_info.location_id
            asset.system_name = loc_info.name
        elif loc_info.category == "planet":
            asset.planet_id = loc_info.location_id
            asset.planet_name = loc_info.name
        elif loc_info.category == "structure":
            asset.structure_id = loc_info.location_id
            asset.structure_name = loc_info.custom_name or loc_info.name
            # Structures have system info - resolve it
            if loc_info.solar_system_id:
                asset.system_id = loc_info.solar_system_id
                system_name = self._sde.get_solar_system_name(loc_info.solar_system_id)
                if system_name:
                    asset.system_name = system_name
        elif loc_info.category == "region":
            asset.region_id = loc_info.location_id
            asset.region_name = loc_info.name
        elif loc_info.category == "constellation":
            asset.constellation_id = loc_info.location_id
            asset.constellation_name = loc_info.name

    def _find_root_location(
        self, asset: EveAsset, by_item_id: dict[int, EveAsset]
    ) -> tuple[int | None, str | None]:
        """Follow parent chain to a non-item location.

        Args:
            asset: Asset to find root location for
            by_item_id: Index of assets by item_id for parent traversal

        Returns:
            Tuple of (location_id, location_type) or (None, None) if not found
        """
        loc_id = asset.location_id
        loc_type = asset.location_type

        if loc_type != "item":
            return loc_id, loc_type

        # Traverse container chain
        max_hops = 64
        hops = 0
        while loc_type == "item" and hops < max_hops:
            parent = by_item_id.get(loc_id)
            if parent is None:
                # Try to infer location type from ID
                if loc_id >= 1000000000000:  # Structure ID
                    return loc_id, "other"
                if 60000000 <= loc_id < 70000000:  # Station ID
                    return loc_id, "station"
                if 30000000 <= loc_id < 40000000:  # System ID
                    return loc_id, "solar_system"
                return None, None
            loc_id = parent.location_id
            loc_type = parent.location_type
            hops += 1

        if loc_type == "item":
            return None, None
        return loc_id, loc_type
