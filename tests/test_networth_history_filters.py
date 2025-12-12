import asyncio
from datetime import UTC, datetime
from typing import cast

from data.clients import ESIClient
from data.repositories import networth as networth_repo
from data.repositories.repository import Repository
from models.app import NetWorthSnapshot
from services.networth_service import NetWorthService


async def _prepare_service_with_snapshots() -> tuple[Repository, NetWorthService]:
    repo = Repository(db_path=":memory:")
    await repo.initialize()

    dummy_esi = cast(ESIClient, object())
    service = NetWorthService(
        esi_client=dummy_esi,
        repository=repo,
        fuzzwork_provider=None,
        settings_manager=None,
        sde_provider=None,
        location_service=None,
    )

    times = [
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 2, 1, tzinfo=UTC),
        datetime(2024, 3, 1, tzinfo=UTC),
    ]

    for idx, ts in enumerate(times, start=1):
        snapshot = NetWorthSnapshot(
            snapshot_id=0,
            character_id=1,
            account_id=None,
            snapshot_group_id=None,
            snapshot_time=ts,
            total_asset_value=100.0 * idx,
            wallet_balance=10.0 * idx,
            market_escrow=0.0,
            market_sell_value=0.0,
            contract_collateral=0.0,
            contract_value=0.0,
            industry_job_value=0.0,
            plex_vault=0.0,
        )
        await networth_repo.save_snapshot(repo, 1, snapshot)

    return repo, service


def test_get_networth_history_filters_by_start_date() -> None:
    async def _run():
        repo, service = await _prepare_service_with_snapshots()
        try:
            start = datetime(2024, 2, 1, tzinfo=UTC)
            history = await service.get_networth_history(1, limit=None, start=start)
            assert [snap.snapshot_time for snap in history] == [
                datetime(2024, 3, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            ]
        finally:
            await repo.close()

    asyncio.run(_run())


def test_get_networth_history_filters_by_start_and_end_dates() -> None:
    async def _run():
        repo, service = await _prepare_service_with_snapshots()
        try:
            start = datetime(2024, 1, 15, tzinfo=UTC)
            end = datetime(2024, 2, 15, tzinfo=UTC)
            history = await service.get_networth_history(
                1, limit=None, start=start, end=end
            )
            assert len(history) == 1
            assert history[0].snapshot_time == datetime(2024, 2, 1, tzinfo=UTC)
        finally:
            await repo.close()

    asyncio.run(_run())
