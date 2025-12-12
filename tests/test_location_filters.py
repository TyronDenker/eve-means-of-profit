import asyncio
from datetime import UTC, datetime
from typing import cast

import pytest

from data.clients import ESIClient
from data.repositories import assets as assets_repo
from data.repositories.repository import Repository
from models.app import LocationInfo
from models.eve.asset import EveAsset
from services.location_service import LocationService
from services.networth_service import NetWorthService


class _DummySettings:
    def __init__(self, prices: dict[int, float]):
        self._prices = prices

    def get_custom_price(self, type_id: int):
        price = self._prices.get(type_id)
        if price is None:
            return None
        return {"sell": price}


class _DummyLocationService:
    async def resolve_locations_bulk(
        self, location_ids, character_id=None, refresh_stale=True
    ):
        now = datetime.now(UTC)
        result = {}
        for loc_id in location_ids:
            result[int(loc_id)] = LocationInfo(
                location_id=int(loc_id),
                name=f"Loc {loc_id}",
                category="structure",
                last_checked=now,
                owner_id=None,
                esi_name=f"Loc {loc_id}",
                custom_name=None,
                is_placeholder=False,
                solar_system_id=30000142,
                metadata=None,
            )
        return result


async def _setup_repo_with_assets() -> tuple[Repository, NetWorthService]:
    repo = Repository(db_path=":memory:")
    await repo.initialize()

    ship = EveAsset(
        item_id=1001,
        type_id=17740,
        quantity=1,
        location_id=60003760,
        location_type="station",
        location_flag="Hangar",
        is_singleton=True,
        is_blueprint_copy=False,
    )
    module = EveAsset(
        item_id=1002,
        type_id=34,
        quantity=100,
        location_id=1001,
        location_type="item",
        location_flag="Hangar",
        is_singleton=False,
        is_blueprint_copy=False,
    )
    await assets_repo.update_current_assets(repo, 1, [ship, module])

    dummy_esi = cast(ESIClient, object())
    dummy_location_service = cast(LocationService, _DummyLocationService())

    service = NetWorthService(
        esi_client=dummy_esi,
        repository=repo,
        fuzzwork_provider=None,
        settings_manager=_DummySettings({34: 5000.0, 17740: 1_000_000.0}),
        sde_provider=None,
        location_service=dummy_location_service,
    )
    return repo, service


def test_calculate_assets_for_locations_uses_root_location():
    async def _run():
        repo, service = await _setup_repo_with_assets()
        try:
            total = await service.calculate_assets_for_locations(1, [60003760])
            assert total == pytest.approx(1_000_000.0 + 100 * 5000.0)

            zero_total = await service.calculate_assets_for_locations(1, [60000000])
            assert zero_total == 0.0
        finally:
            await repo.close()

    asyncio.run(_run())


def test_list_asset_locations_returns_resolved_names():
    async def _run():
        repo, service = await _setup_repo_with_assets()
        try:
            options = await service.list_asset_locations([1])
            assert len(options) == 1
            opt = options[0]
            assert opt.location_id == 60003760
            assert opt.asset_count == 2
            assert opt.character_count == 1
            assert opt.display_name == "Loc 60003760"
        finally:
            await repo.close()

    asyncio.run(_run())
