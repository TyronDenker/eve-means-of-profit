from pathlib import Path

from data.sde_provider import SDEProvider
from models.eve import EveCategory, EveGroup, EveMarketGroup, EveType


class _CountingParser:
    def __init__(self, base: Path):
        self.file_path = base
        self.calls = {
            "types": 0,
            "categories": 0,
            "groups": 0,
            "market_groups": 0,
            "blueprints": 0,
            "stations": 0,
            "station_names": 0,
            "station_systems": 0,
            "region_names": 0,
            "constellation_names": 0,
            "solar_system_names": 0,
        }

    def load_types(self):
        self.calls["types"] += 1
        yield EveType(
            id=100,
            name="Type",
            group_id=10,
            portion_size=1,
            published=True,
        )

    def load_categories(self):
        self.calls["categories"] += 1
        yield EveCategory(id=1, name="Cat", published=True, icon_id=None)

    def load_groups(self):
        self.calls["groups"] += 1
        yield EveGroup(
            id=10,
            anchorable=False,
            anchored=False,
            category_id=1,
            fittable_non_singleton=False,
            icon_id=None,
            name="Grp",
            published=True,
            use_base_price=False,
        )

    def load_market_groups(self):
        self.calls["market_groups"] += 1
        yield EveMarketGroup(
            marketgroup_id=5,
            name="MG",
            description="",
            has_types=True,
            parent_group_id=None,
            icon_id=None,
        )

    def load_blueprint_type_ids(self):
        self.calls["blueprints"] += 1
        return {200}

    def load_npc_station_ids(self):
        self.calls["stations"] += 1
        return {60000001}

    def load_npc_station_names(self):
        self.calls["station_names"] += 1
        return {60000001: "Station"}

    def load_npc_station_system_ids(self):
        self.calls["station_systems"] += 1
        return {60000001: 30000001}

    def load_region_names(self):
        self.calls["region_names"] += 1
        return {10000001: "Region"}

    def load_constellation_names(self):
        self.calls["constellation_names"] += 1
        return {20000001: "Constellation"}

    def load_solar_system_names(self):
        self.calls["solar_system_names"] += 1
        return {30000001: "System"}


def _touch_stub_files(base: Path):
    base.mkdir(parents=True, exist_ok=True)
    for name in [
        "types.jsonl",
        "categories.jsonl",
        "groups.jsonl",
        "marketGroups.jsonl",
        "npcStations.jsonl",
        "blueprints.jsonl",
        "regions.jsonl",
        "constellations.jsonl",
        "solarSystems.jsonl",
    ]:
        (base / name).write_text("{}\n", encoding="utf-8")


def test_sde_persist_and_reload(tmp_path):
    data_dir = tmp_path / "sde"
    persist_path = tmp_path / "persist.pkl"
    _touch_stub_files(data_dir)

    parser = _CountingParser(data_dir)
    provider = SDEProvider(parser, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]

    # Build and persist synchronously
    provider._build_all_indices_sync()
    provider._persist_indices()

    # Ensure caches are present
    assert provider.get_all_types()[0].type_id == 100
    assert persist_path.exists()
    first_calls = parser.calls.copy()

    # New provider using same data dir should load persisted caches without hitting parser
    parser2 = _CountingParser(data_dir)
    provider2 = SDEProvider(parser2, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]
    provider2.wait_until_ready(1)

    # Access data; should not trigger parser methods because loaded from cache
    types = provider2.get_all_types()
    assert len(types) == 1
    assert types[0].type_id == 100
    assert all(v == 0 for v in parser2.calls.values())

    # Original parser was called during initial build
    assert first_calls["types"] == 1
    assert first_calls["categories"] == 1
    assert first_calls["groups"] == 1
    assert first_calls["market_groups"] == 1
    assert first_calls["blueprints"] == 1


def test_sde_metadata_tracking(tmp_path):
    """Test that SDE metadata is tracked and stored."""

    data_dir = tmp_path / "sde"
    persist_path = tmp_path / "persist.pkl"
    _touch_stub_files(data_dir)

    parser = _CountingParser(data_dir)
    provider = SDEProvider(parser, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]

    # Build and persist
    provider._build_all_indices_sync()
    provider._persist_indices()

    # Check metadata exists
    metadata = provider.get_sde_metadata()
    assert metadata is not None
    assert "computed_at" in metadata
    assert metadata["total_types"] == 1
    assert metadata["total_groups"] == 1
    assert metadata["total_categories"] == 1

    # Reload and check metadata persists
    parser2 = _CountingParser(data_dir)
    provider2 = SDEProvider(parser2, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]
    provider2.wait_until_ready(1)

    metadata2 = provider2.get_sde_metadata()
    assert metadata2 is not None
    assert metadata2["computed_at"] == metadata["computed_at"]


def test_sde_partial_rebuild_on_file_change(tmp_path):
    """Test that only changed caches are rebuilt when SDE files change."""
    import time

    data_dir = tmp_path / "sde"
    persist_path = tmp_path / "persist.pkl"
    _touch_stub_files(data_dir)

    parser = _CountingParser(data_dir)
    provider = SDEProvider(parser, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]

    # Build and persist
    provider._build_all_indices_sync()
    provider._persist_indices()

    # Modify just the types.jsonl file
    time.sleep(0.1)  # Ensure mtime changes
    types_file = data_dir / "types.jsonl"
    types_file.write_text("{}\n{}\n", encoding="utf-8")  # Change content/size

    # Create new provider - should detect types.jsonl changed and rebuild only types
    parser2 = _CountingParser(data_dir)
    provider2 = SDEProvider(parser2, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]
    provider2.wait_until_ready(1)

    # Types should have been rebuilt
    assert parser2.calls["types"] == 1
    # Groups should NOT have been rebuilt (file unchanged)
    assert parser2.calls["groups"] == 0
    # Categories should NOT have been rebuilt (file unchanged)
    assert parser2.calls["categories"] == 0


def test_sde_file_signature_computation(tmp_path):
    """Test that file signatures are computed correctly."""
    data_dir = tmp_path / "sde"
    persist_path = tmp_path / "persist.pkl"
    _touch_stub_files(data_dir)

    parser = _CountingParser(data_dir)
    provider = SDEProvider(parser, background_build=False, persist_path=persist_path)  # type: ignore[arg-type]

    signatures = provider._compute_file_signatures()

    # Should have signatures for all stub files
    assert "types.jsonl" in signatures
    assert "groups.jsonl" in signatures
    assert "categories.jsonl" in signatures

    # Each signature should have mtime and size
    for filename, sig in signatures.items():
        assert "mtime" in sig
        assert "size" in sig
        assert isinstance(sig["mtime"], float)
        assert isinstance(sig["size"], int)
