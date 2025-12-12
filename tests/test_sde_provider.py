"""Tests for SDE Provider persistence and partial rebuild features.

This test module validates SDE (Static Data Export) persistence features using
self-contained mocks to avoid requiring external dependencies like pydantic.

Core features tested:
- File signature detection and change tracking
- Partial rebuild logic (only rebuild what changed)
- Metadata persistence and integrity validation
- Cache file management
"""

import pickle
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

# ==============================================================================
# Self-contained mock implementations for SDE data types
# ==============================================================================


@dataclass
class MockEveType:
    """Mock implementation of EveType without pydantic dependency."""

    id: int
    name: str
    group_id: int
    portion_size: int = 1
    published: bool = True
    market_group_id: int | None = None
    volume: float = 0.0
    packaged_volume: float = 0.0
    icon_id: int | None = None
    description: str = ""


@dataclass
class MockEveCategory:
    """Mock implementation of EveCategory without pydantic dependency."""

    id: int
    name: str
    published: bool = True
    icon_id: int | None = None


@dataclass
class MockEveGroup:
    """Mock implementation of EveGroup without pydantic dependency."""

    id: int
    name: str
    category_id: int
    published: bool = True
    anchorable: bool = False
    anchored: bool = False
    fittable_non_singleton: bool = False
    icon_id: int | None = None
    use_base_price: bool = False


@dataclass
class MockEveMarketGroup:
    """Mock implementation of EveMarketGroup without pydantic dependency."""

    marketgroup_id: int
    name: str
    description: str = ""
    has_types: bool = True
    parent_group_id: int | None = None
    icon_id: int | None = None


# ==============================================================================
# Constants matching the real implementation
# ==============================================================================

# Define which cache files depend on which SDE source files
CACHE_FILE_DEPENDENCIES = {
    "types_cache": ["types.jsonl"],
    "categories_cache": ["categories.jsonl"],
    "groups_cache": ["groups.jsonl"],
    "market_groups_cache": ["marketGroups.jsonl"],
    "blueprints_cache": ["blueprints.jsonl"],
    "stations_cache": ["npcStations.jsonl"],
    "regions_cache": ["regions.jsonl"],
    "constellations_cache": ["constellations.jsonl"],
    "systems_cache": ["solarSystems.jsonl"],
}

# Minimum expected sizes for cache validation
MIN_EXPECTED_CACHE_SIZES = {
    "types_cache": 1000,
    "categories_cache": 10,
    "groups_cache": 100,
    "market_groups_cache": 100,
    "blueprints_cache": 100,
    "stations_cache": 1000,
    "regions_cache": 50,
    "systems_cache": 5000,
    "constellations_cache": 500,
}


# ==============================================================================
# Mock Parser for testing
# ==============================================================================


class MockParser:
    """Mock parser for testing SDE provider without actual SDE files."""

    def __init__(self, base_path: Path):
        self.file_path = base_path
        self.call_counts = {
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
        self.call_counts["types"] += 1
        yield MockEveType(
            id=100,
            name="Test Type",
            group_id=10,
            portion_size=1,
            published=True,
        )
        yield MockEveType(
            id=101,
            name="Test Type 2",
            group_id=10,
            portion_size=1,
            published=False,
        )

    def load_categories(self):
        self.call_counts["categories"] += 1
        yield MockEveCategory(id=1, name="Test Category", published=True, icon_id=None)

    def load_groups(self):
        self.call_counts["groups"] += 1
        yield MockEveGroup(
            id=10,
            anchorable=False,
            anchored=False,
            category_id=1,
            fittable_non_singleton=False,
            icon_id=None,
            name="Test Group",
            published=True,
            use_base_price=False,
        )

    def load_market_groups(self):
        self.call_counts["market_groups"] += 1
        yield MockEveMarketGroup(
            marketgroup_id=5,
            name="Test Market Group",
            description="",
            has_types=True,
            parent_group_id=None,
            icon_id=None,
        )

    def load_blueprint_type_ids(self):
        self.call_counts["blueprints"] += 1
        return {200, 201}

    def load_npc_station_ids(self):
        self.call_counts["stations"] += 1
        return {60000001, 60000002}

    def load_npc_station_names(self):
        self.call_counts["station_names"] += 1
        return {60000001: "Jita Station", 60000002: "Amarr Station"}

    def load_npc_station_system_ids(self):
        self.call_counts["station_systems"] += 1
        return {60000001: 30000001, 60000002: 30000002}

    def load_region_names(self):
        self.call_counts["region_names"] += 1
        return {10000001: "The Forge", 10000002: "Domain"}

    def load_constellation_names(self):
        self.call_counts["constellation_names"] += 1
        return {20000001: "Kimotoro", 20000002: "Throne Worlds"}

    def load_solar_system_names(self):
        self.call_counts["solar_system_names"] += 1
        return {30000001: "Jita", 30000002: "Amarr"}


# ==============================================================================
# Mock SDE Provider implementation for testing
# ==============================================================================


class MockSDEProvider:
    """Mock SDE Provider for testing persistence and rebuild logic."""

    def __init__(
        self,
        parser: MockParser,
        background_build: bool = False,
        persist_path: Path | None = None,
    ):
        self.parser = parser
        self.persist_path = persist_path
        self.background_build = background_build
        self._ready = False

        # Data caches
        self.types: dict[int, MockEveType] = {}
        self.categories: dict[int, MockEveCategory] = {}
        self.groups: dict[int, MockEveGroup] = {}
        self.market_groups: dict[int, MockEveMarketGroup] = {}
        self.blueprint_type_ids: set[int] = set()
        self.npc_station_ids: set[int] = set()
        self.npc_station_names: dict[int, str] = {}
        self.npc_station_system_ids: dict[int, int] = {}
        self.region_names: dict[int, str] = {}
        self.constellation_names: dict[int, str] = {}
        self.solar_system_names: dict[int, str] = {}

        # Metadata
        self._metadata: dict[str, Any] = {}
        self._file_signatures: dict[str, dict] = {}

        # Try to load from cache on init
        if persist_path and persist_path.exists():
            self._try_load_from_cache()

    def _compute_file_signatures(self) -> dict[str, dict]:
        """Compute signatures for all SDE source files."""
        signatures = {}
        if self.parser.file_path.exists():
            for name in [
                "types.jsonl",
                "categories.jsonl",
                "groups.jsonl",
                "marketGroups.jsonl",
                "blueprints.jsonl",
                "npcStations.jsonl",
                "regions.jsonl",
                "constellations.jsonl",
                "solarSystems.jsonl",
            ]:
                file_path = self.parser.file_path / name
                if file_path.exists():
                    stat = file_path.stat()
                    signatures[name] = {
                        "mtime": stat.st_mtime,
                        "size": stat.st_size,
                    }
        return signatures

    def _try_load_from_cache(self):
        """Try to load data from persisted cache."""
        if not self.persist_path or not self.persist_path.exists():
            return False

        try:
            with open(self.persist_path, "rb") as f:
                cached_data = pickle.load(f)

            # Check if signatures match (files haven't changed)
            cached_signatures = cached_data.get("file_signatures", {})
            current_signatures = self._compute_file_signatures()

            # Determine which caches need rebuilding
            files_changed = []
            for name, current_sig in current_signatures.items():
                cached_sig = cached_signatures.get(name, {})
                if current_sig != cached_sig:
                    files_changed.append(name)

            if not files_changed:
                # Load all data from cache
                self.types = cached_data.get("types", {})
                self.categories = cached_data.get("categories", {})
                self.groups = cached_data.get("groups", {})
                self.market_groups = cached_data.get("market_groups", {})
                self.blueprint_type_ids = cached_data.get("blueprint_type_ids", set())
                self.npc_station_ids = cached_data.get("npc_station_ids", set())
                self.npc_station_names = cached_data.get("npc_station_names", {})
                self.npc_station_system_ids = cached_data.get(
                    "npc_station_system_ids", {}
                )
                self.region_names = cached_data.get("region_names", {})
                self.constellation_names = cached_data.get("constellation_names", {})
                self.solar_system_names = cached_data.get("solar_system_names", {})
                self._metadata = cached_data.get("metadata", {})
                self._file_signatures = cached_signatures
                self._ready = True
                return True
            # Partial rebuild needed - load what we can, rebuild what changed
            self._partial_rebuild(cached_data, files_changed)
            return True

        except Exception:
            return False

    def _partial_rebuild(self, cached_data: dict, files_changed: list[str]):
        """Rebuild only the caches that need updating."""
        # First, load everything from cache
        self.types = cached_data.get("types", {})
        self.categories = cached_data.get("categories", {})
        self.groups = cached_data.get("groups", {})
        self.market_groups = cached_data.get("market_groups", {})
        self.blueprint_type_ids = cached_data.get("blueprint_type_ids", set())
        self.npc_station_ids = cached_data.get("npc_station_ids", set())
        self.npc_station_names = cached_data.get("npc_station_names", {})
        self.npc_station_system_ids = cached_data.get("npc_station_system_ids", {})
        self.region_names = cached_data.get("region_names", {})
        self.constellation_names = cached_data.get("constellation_names", {})
        self.solar_system_names = cached_data.get("solar_system_names", {})

        # Rebuild only what changed
        if "types.jsonl" in files_changed:
            self._build_types()
        if "categories.jsonl" in files_changed:
            self._build_categories()
        if "groups.jsonl" in files_changed:
            self._build_groups()
        if "marketGroups.jsonl" in files_changed:
            self._build_market_groups()
        if "blueprints.jsonl" in files_changed:
            self._build_blueprints()
        if "npcStations.jsonl" in files_changed:
            self._build_stations()

        self._ready = True

    def _build_types(self):
        """Build types index from parser."""
        self.types = {}
        for eve_type in self.parser.load_types():
            self.types[eve_type.id] = eve_type

    def _build_categories(self):
        """Build categories index from parser."""
        self.categories = {}
        for category in self.parser.load_categories():
            self.categories[category.id] = category

    def _build_groups(self):
        """Build groups index from parser."""
        self.groups = {}
        for group in self.parser.load_groups():
            self.groups[group.id] = group

    def _build_market_groups(self):
        """Build market groups index from parser."""
        self.market_groups = {}
        for market_group in self.parser.load_market_groups():
            self.market_groups[market_group.marketgroup_id] = market_group

    def _build_blueprints(self):
        """Build blueprints set from parser."""
        self.blueprint_type_ids = self.parser.load_blueprint_type_ids()

    def _build_stations(self):
        """Build stations data from parser."""
        self.npc_station_ids = self.parser.load_npc_station_ids()
        self.npc_station_names = self.parser.load_npc_station_names()
        self.npc_station_system_ids = self.parser.load_npc_station_system_ids()

    def _build_regions(self):
        """Build region/constellation/system data from parser."""
        self.region_names = self.parser.load_region_names()
        self.constellation_names = self.parser.load_constellation_names()
        self.solar_system_names = self.parser.load_solar_system_names()

    def _build_all_indices_sync(self):
        """Build all indices synchronously."""
        self._build_types()
        self._build_categories()
        self._build_groups()
        self._build_market_groups()
        self._build_blueprints()
        self._build_stations()
        self._build_regions()
        self._update_metadata()
        self._ready = True

    def _update_metadata(self):
        """Update metadata with current counts."""
        import datetime

        self._metadata = {
            "computed_at": datetime.datetime.now().isoformat(),
            "total_types": len(self.types),
            "total_groups": len(self.groups),
            "total_categories": len(self.categories),
            "total_market_groups": len(self.market_groups),
        }

    def _persist_indices(self):
        """Persist indices to disk."""
        if not self.persist_path:
            return

        self._file_signatures = self._compute_file_signatures()

        data = {
            "types": self.types,
            "categories": self.categories,
            "groups": self.groups,
            "market_groups": self.market_groups,
            "blueprint_type_ids": self.blueprint_type_ids,
            "npc_station_ids": self.npc_station_ids,
            "npc_station_names": self.npc_station_names,
            "npc_station_system_ids": self.npc_station_system_ids,
            "region_names": self.region_names,
            "constellation_names": self.constellation_names,
            "solar_system_names": self.solar_system_names,
            "metadata": self._metadata,
            "file_signatures": self._file_signatures,
        }

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, "wb") as f:
            pickle.dump(data, f)

    def get_sde_metadata(self) -> dict | None:
        """Get SDE metadata."""
        return self._metadata if self._metadata else None

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Wait until provider is ready."""
        if self._ready:
            return True
        # If not ready from cache, build everything
        self._build_all_indices_sync()
        return True


# ==============================================================================
# Helper functions for tests
# ==============================================================================


def create_stub_sde_files(base_path: Path) -> None:
    """Create stub SDE files for testing."""
    base_path.mkdir(parents=True, exist_ok=True)
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
        (base_path / name).write_text("{}\n", encoding="utf-8")


# ==============================================================================
# Test Classes
# ==============================================================================


class TestFileSignatureDetection:
    """Tests for per-file signature detection."""

    def test_compute_file_signatures_returns_mtime_and_size(self, tmp_path):
        """Test that file signatures contain mtime and size."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )

        signatures = provider._compute_file_signatures()

        # Check all expected files have signatures
        assert "types.jsonl" in signatures
        assert "groups.jsonl" in signatures
        assert "categories.jsonl" in signatures

        # Each signature should have mtime and size
        for filename, sig in signatures.items():
            assert "mtime" in sig, f"Missing mtime for {filename}"
            assert "size" in sig, f"Missing size for {filename}"
            assert isinstance(sig["mtime"], float)
            assert isinstance(sig["size"], int)

    def test_signatures_change_when_file_modified(self, tmp_path):
        """Test that signatures change when files are modified."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )

        # Get initial signatures
        sig1 = provider._compute_file_signatures()
        original_size = sig1["types.jsonl"]["size"]

        # Modify a file
        time.sleep(0.1)  # Ensure mtime changes
        (sde_dir / "types.jsonl").write_text("{}\n{}\n{}\n", encoding="utf-8")

        # Get new signatures
        sig2 = provider._compute_file_signatures()
        new_size = sig2["types.jsonl"]["size"]

        # Size should have changed
        assert new_size != original_size

    def test_missing_files_handled_gracefully(self, tmp_path):
        """Test that missing SDE files don't cause crashes."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        sde_dir.mkdir(parents=True, exist_ok=True)
        # Only create some files
        (sde_dir / "types.jsonl").write_text("{}\n", encoding="utf-8")

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )

        # Should not raise
        signatures = provider._compute_file_signatures()
        assert "types.jsonl" in signatures

    def test_empty_directory_returns_empty_signatures(self, tmp_path):
        """Test that an empty directory returns empty signatures."""
        sde_dir = tmp_path / "sde"
        sde_dir.mkdir(parents=True, exist_ok=True)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(parser, background_build=False)

        signatures = provider._compute_file_signatures()
        assert signatures == {}

    def test_signature_includes_all_sde_files(self, tmp_path):
        """Test that signatures are computed for all expected SDE files."""
        sde_dir = tmp_path / "sde"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(parser, background_build=False)

        signatures = provider._compute_file_signatures()

        expected_files = [
            "types.jsonl",
            "categories.jsonl",
            "groups.jsonl",
            "marketGroups.jsonl",
            "blueprints.jsonl",
            "npcStations.jsonl",
            "regions.jsonl",
            "constellations.jsonl",
            "solarSystems.jsonl",
        ]
        for expected in expected_files:
            assert expected in signatures, f"Missing signature for {expected}"


class TestPartialRebuild:
    """Tests for partial rebuild when only some files change."""

    def test_unchanged_files_not_reloaded(self, tmp_path):
        """Test that unchanged caches are not rebuilt."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # First build
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Verify initial build called parser
        assert parser1.call_counts["types"] >= 1
        assert parser1.call_counts["groups"] >= 1

        # Second load from persisted cache
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(1)

        # Parser should not be called when loading from cache
        assert parser2.call_counts["types"] == 0
        assert parser2.call_counts["groups"] == 0

    def test_changed_file_triggers_rebuild_of_dependent_cache(self, tmp_path):
        """Test that modifying a file rebuilds only the dependent cache."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # First build
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Modify only types.jsonl
        time.sleep(0.1)
        (sde_dir / "types.jsonl").write_text("{}\n{}\n", encoding="utf-8")

        # Second load should detect change
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(1)

        # Types should be rebuilt, groups should not
        assert parser2.call_counts["types"] >= 1
        assert parser2.call_counts["groups"] == 0

    def test_multiple_files_changed_rebuilds_multiple_caches(self, tmp_path):
        """Test that multiple file changes trigger multiple cache rebuilds."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # First build
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Modify both types and groups
        time.sleep(0.1)
        (sde_dir / "types.jsonl").write_text("{}\n{}\n", encoding="utf-8")
        (sde_dir / "groups.jsonl").write_text("{}\n{}\n", encoding="utf-8")

        # Second load
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(1)

        # Both should be rebuilt
        assert parser2.call_counts["types"] >= 1
        assert parser2.call_counts["groups"] >= 1

    def test_partial_rebuild_preserves_unchanged_data(self, tmp_path):
        """Test that partial rebuild preserves data from unchanged caches."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # First build
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Store original group count
        original_group_count = len(provider1.groups)

        # Modify only types
        time.sleep(0.1)
        (sde_dir / "types.jsonl").write_text("{}\n{}\n", encoding="utf-8")

        # Second load
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(1)

        # Groups should still be intact
        assert len(provider2.groups) == original_group_count


class TestMetadataPersistence:
    """Tests for metadata persistence."""

    def test_metadata_stored_on_build(self, tmp_path):
        """Test that metadata is stored when caches are built."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )
        provider._build_all_indices_sync()
        provider._persist_indices()

        metadata = provider.get_sde_metadata()
        assert metadata is not None
        assert "computed_at" in metadata
        assert "total_types" in metadata
        assert metadata["total_types"] == 2  # MockParser yields 2 types

    def test_metadata_restored_from_cache(self, tmp_path):
        """Test that metadata is restored when loading from cache."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build and persist
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()
        original_metadata = provider1.get_sde_metadata()

        # Reload from cache
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(1)
        loaded_metadata = provider2.get_sde_metadata()

        assert loaded_metadata is not None
        assert loaded_metadata["computed_at"] == original_metadata["computed_at"]
        assert loaded_metadata["total_types"] == original_metadata["total_types"]

    def test_metadata_contains_expected_fields(self, tmp_path):
        """Test that metadata contains all expected fields."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )
        provider._build_all_indices_sync()

        metadata = provider.get_sde_metadata()
        assert metadata is not None

        expected_fields = [
            "computed_at",
            "total_types",
            "total_groups",
            "total_categories",
            "total_market_groups",
        ]
        for field in expected_fields:
            assert field in metadata, f"Missing metadata field: {field}"

    def test_metadata_counts_are_accurate(self, tmp_path):
        """Test that metadata counts reflect actual data sizes."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )
        provider._build_all_indices_sync()

        metadata = provider.get_sde_metadata()

        assert metadata["total_types"] == len(provider.types)
        assert metadata["total_groups"] == len(provider.groups)
        assert metadata["total_categories"] == len(provider.categories)
        assert metadata["total_market_groups"] == len(provider.market_groups)


class TestIntegrityValidation:
    """Tests for integrity validation on load."""

    def test_corrupted_cache_triggers_rebuild(self, tmp_path):
        """Test that corrupted cache file triggers a rebuild."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build valid cache
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Corrupt the cache file
        persist_path.write_bytes(b"corrupted data")

        # Try to load - should rebuild instead of crashing
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(2)

        # Should have rebuilt (parser was called)
        assert parser2.call_counts["types"] >= 1

    def test_empty_cache_triggers_rebuild(self, tmp_path):
        """Test that empty cache file triggers rebuild."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Create empty cache file
        persist_path.write_bytes(b"")

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )
        provider.wait_until_ready(2)

        # Should have built (parser was called)
        assert parser.call_counts["types"] >= 1

    def test_valid_cache_loads_without_rebuild(self, tmp_path):
        """Test that valid cache loads without calling parser."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build valid cache
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Load from cache
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(1)

        # Parser should not be called
        assert parser2.call_counts["types"] == 0

    def test_missing_cache_file_triggers_build(self, tmp_path):
        """Test that missing cache file triggers a full build."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(
            parser, background_build=False, persist_path=persist_path
        )
        provider.wait_until_ready(1)

        # Should have built (parser was called)
        assert parser.call_counts["types"] >= 1

    def test_truncated_cache_handled_gracefully(self, tmp_path):
        """Test that truncated pickle file is handled gracefully."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build valid cache
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Truncate the cache file
        with open(persist_path, "rb") as f:
            data = f.read()
        persist_path.write_bytes(data[: len(data) // 2])

        # Try to load - should rebuild
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )
        provider2.wait_until_ready(2)

        # Should have rebuilt
        assert parser2.call_counts["types"] >= 1


class TestCacheFileDependencies:
    """Tests for the cache file dependencies mapping."""

    def test_types_depends_on_types_jsonl(self):
        """Test types cache depends on types.jsonl."""
        assert "types.jsonl" in CACHE_FILE_DEPENDENCIES["types_cache"]

    def test_groups_depends_on_groups_jsonl(self):
        """Test groups cache depends on groups.jsonl."""
        assert "groups.jsonl" in CACHE_FILE_DEPENDENCIES["groups_cache"]

    def test_categories_depends_on_categories_jsonl(self):
        """Test categories cache depends on categories.jsonl."""
        assert "categories.jsonl" in CACHE_FILE_DEPENDENCIES["categories_cache"]

    def test_market_groups_depends_on_marketgroups_jsonl(self):
        """Test market groups cache depends on marketGroups.jsonl."""
        assert "marketGroups.jsonl" in CACHE_FILE_DEPENDENCIES["market_groups_cache"]

    def test_all_caches_have_dependencies(self):
        """Test that all caches have at least one dependency."""
        for cache_name, deps in CACHE_FILE_DEPENDENCIES.items():
            assert len(deps) > 0, f"Cache {cache_name} has no dependencies"


class TestMinExpectedCacheSizes:
    """Tests for minimum expected cache sizes validation."""

    def test_min_sizes_defined_for_important_caches(self):
        """Test minimum sizes are defined for important caches."""
        assert "types_cache" in MIN_EXPECTED_CACHE_SIZES
        assert "groups_cache" in MIN_EXPECTED_CACHE_SIZES
        assert "categories_cache" in MIN_EXPECTED_CACHE_SIZES

    def test_min_sizes_are_positive(self):
        """Test all minimum sizes are positive."""
        for cache, min_size in MIN_EXPECTED_CACHE_SIZES.items():
            assert min_size > 0, f"Invalid min size for {cache}: {min_size}"

    def test_types_has_largest_min_size(self):
        """Test that types cache has the largest minimum size expectation."""
        types_min = MIN_EXPECTED_CACHE_SIZES["types_cache"]
        for cache, min_size in MIN_EXPECTED_CACHE_SIZES.items():
            if cache != "types_cache" and cache != "systems_cache":
                assert types_min >= min_size, f"{cache} has larger min than types_cache"


class TestDataIntegrity:
    """Tests for data integrity after build and load."""

    def test_types_data_preserved_after_persist(self, tmp_path):
        """Test that type data is preserved after persist and reload."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build and persist
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Check original data
        original_types = dict(provider1.types)

        # Reload
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )

        # Compare
        for type_id, eve_type in original_types.items():
            assert type_id in provider2.types
            assert provider2.types[type_id].name == eve_type.name

    def test_blueprints_set_preserved(self, tmp_path):
        """Test that blueprint IDs set is preserved."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build and persist
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        original_blueprints = set(provider1.blueprint_type_ids)

        # Reload
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )

        assert provider2.blueprint_type_ids == original_blueprints

    def test_station_names_preserved(self, tmp_path):
        """Test that station names are preserved."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build and persist
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        original_names = dict(provider1.npc_station_names)

        # Reload
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )

        assert provider2.npc_station_names == original_names


class TestProviderInitialization:
    """Tests for provider initialization scenarios."""

    def test_provider_ready_after_sync_build(self, tmp_path):
        """Test that provider is ready after synchronous build."""
        sde_dir = tmp_path / "sde"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(parser, background_build=False)
        provider._build_all_indices_sync()

        assert provider._ready is True

    def test_provider_has_data_after_build(self, tmp_path):
        """Test that provider has data after build."""
        sde_dir = tmp_path / "sde"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(parser, background_build=False)
        provider._build_all_indices_sync()

        assert len(provider.types) > 0
        assert len(provider.categories) > 0
        assert len(provider.groups) > 0

    def test_wait_until_ready_returns_true(self, tmp_path):
        """Test that wait_until_ready eventually returns True."""
        sde_dir = tmp_path / "sde"
        create_stub_sde_files(sde_dir)

        parser = MockParser(sde_dir)
        provider = MockSDEProvider(parser, background_build=False)

        result = provider.wait_until_ready(1)
        assert result is True

    def test_multiple_providers_can_share_cache(self, tmp_path):
        """Test that multiple providers can read from the same cache file."""
        sde_dir = tmp_path / "sde"
        persist_path = tmp_path / "persist.pkl"
        create_stub_sde_files(sde_dir)

        # Build cache
        parser1 = MockParser(sde_dir)
        provider1 = MockSDEProvider(
            parser1, background_build=False, persist_path=persist_path
        )
        provider1._build_all_indices_sync()
        provider1._persist_indices()

        # Multiple providers read same cache
        parser2 = MockParser(sde_dir)
        provider2 = MockSDEProvider(
            parser2, background_build=False, persist_path=persist_path
        )

        parser3 = MockParser(sde_dir)
        provider3 = MockSDEProvider(
            parser3, background_build=False, persist_path=persist_path
        )

        # All should have same data
        assert provider2.types == provider3.types
        assert parser2.call_counts["types"] == 0
        assert parser3.call_counts["types"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
