import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest

from services.location_service import LocationService


class _FakeStructure:
    def __init__(self, struct_id: int, name: str):
        self.structure_id = struct_id
        self.name = name
        self.owner_id = 999
        self.solar_system_id = 30000001


class _FakeUniverse:
    def __init__(self):
        self.calls = 0

    async def get_structure_info(
        self, structure_id: int, character_id: int, use_cache: bool = True
    ):
        self.calls += 1
        # Small delay to allow overlapping awaits
        await asyncio.sleep(0.01)
        return _FakeStructure(structure_id, f"Structure {structure_id}"), {}


class _FakeESIClient:
    def __init__(self):
        self.universe = _FakeUniverse()
        self.rate_limiter = SimpleNamespace(rate_limit_groups={})


class _FakeSDE:
    def __getattr__(self, name):  # pragma: no cover - unused in this test
        raise AttributeError(name)


class _DummyApp:
    def __init__(self, user_data_dir):
        self.user_data_dir = user_data_dir
        self.structure_resolution_backoff = timedelta(seconds=0.05)


class _DummyConfig:
    def __init__(self, user_data_dir):
        self.app = _DummyApp(user_data_dir)


@pytest.mark.asyncio
async def test_structure_resolution_is_coalesced(monkeypatch, tmp_path):
    # Ensure cache writes happen in a temp directory and avoid touching real config
    monkeypatch.setattr(
        "services.location_service.get_config", lambda: _DummyConfig(tmp_path)
    )

    client = _FakeESIClient()
    svc = LocationService(client, _FakeSDE())  # type: ignore[arg-type]

    # Run two concurrent resolutions for the same structure
    results = await asyncio.gather(
        svc.resolve_locations_bulk([1230000000000], character_id=42),
        svc.resolve_locations_bulk([1230000000000], character_id=42),
    )

    # Only one backend call should have been made
    assert client.universe.calls == 1

    # Both callers should receive the resolved name
    for res in results:
        assert res[1230000000000].name == "Structure 1230000000000"
        assert not res[1230000000000].is_placeholder
