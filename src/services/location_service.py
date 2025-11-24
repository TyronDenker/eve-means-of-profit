"""Service for resolving and caching location names.

Resolves location names from static data (SDE) for public entities and ESI for player structures.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from models.app import LocationInfo
from utils.config import get_config

if TYPE_CHECKING:
    from typing import Any

    from data import SDEProvider
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class LocationService:
    """Manages location name resolution using SDE data and ESI.

    Resolution Strategy:
    - Regions (10000000-10999999): SDE map data
    - Constellations (20000000-29999999): SDE map data
    - Solar Systems (30000000-39999999): SDE map data
    - NPC Stations (60000000-69999999): SDE npcStations data
    - Player Structures (1000000000000+): ESI with character auth

    Features:
    - Local lookups for all public entities (no ESI calls)
    - ESI only for player-owned structures
    - Persistent cache for player structures
    - Staleness tracking for player structures
    """

    CACHE_FILE = "locations.json"

    def __init__(
        self,
        esi_client: ESIClient,
        sde_provider: SDEProvider,
        cache_dir: str | Path | None = None,
        settings_manager: Any | None = None,
    ):
        """Initialize location service.

        Args:
            esi_client: ESI client for API requests
            sde_provider: SDE provider for NPC station lookups
            cache_dir: Directory for cache storage (user data directory)
            settings_manager: Settings manager for custom location names
        """
        self._client = esi_client
        self._sde = sde_provider
        self._settings = settings_manager
        self._cache_file = get_config().app.user_data_dir / self.CACHE_FILE

        # In-memory cache: location_id -> LocationInfo
        self._cache: dict[int, LocationInfo] = {}

        # Load location cache and apply custom names from settings
        self._load_cache()

        # Track which structures we've attempted to fetch (to avoid repeated failures)
        self._failed_structures: set[int] = set()

        # Lock for cache modifications
        self._cache_lock = asyncio.Lock()

    def _load_cache(self) -> None:
        """Load location cache from disk and apply custom names from settings."""
        if not self._cache_file.exists():
            logger.debug("No location cache file found")
        else:
            try:
                with open(self._cache_file, encoding="utf-8") as f:
                    data = json.load(f)

                for entry in data.get("locations", []):
                    try:
                        loc = LocationInfo(
                            location_id=entry["location_id"],
                            name=entry["name"],
                            category=entry["category"],
                            last_checked=datetime.fromisoformat(entry["last_checked"]),
                            owner_id=entry.get("owner_id"),
                            custom_name=None,  # Will be loaded from SettingsManager below
                            is_placeholder=entry.get("is_placeholder", False),
                        )
                        # Don't load placeholders from cache - they'll be re-resolved
                        if not loc.is_placeholder:
                            self._cache[loc.location_id] = loc
                    except (KeyError, ValueError) as e:
                        logger.debug("Skipping invalid cache entry: %s", e)

                logger.info("Loaded %d locations from cache", len(self._cache))
            except Exception as e:
                logger.warning("Failed to load location cache: %s", e)

        # Apply custom names from SettingsManager (source of truth)
        if self._settings:
            custom_locations = self._settings.get_all_custom_locations()
            for location_id, custom_name in custom_locations.items():
                if location_id in self._cache:
                    self._cache[location_id].custom_name = custom_name
                else:
                    # Create placeholder entry for custom-named location not yet cached
                    self._cache[location_id] = LocationInfo(
                        location_id=location_id,
                        name=custom_name,
                        category="structure",
                        last_checked=datetime.now(UTC),
                        owner_id=None,
                        custom_name=custom_name,
                        is_placeholder=True,
                    )
            logger.debug(
                "Applied %d custom location names from settings", len(custom_locations)
            )

    def _save_cache(self) -> None:
        """Save location cache to disk."""
        try:
            data = {
                "locations": [
                    {
                        "location_id": loc.location_id,
                        "name": loc.name,
                        "category": loc.category,
                        "last_checked": loc.last_checked.isoformat(),
                        "owner_id": loc.owner_id,
                        # custom_name NOT saved - SettingsManager is source of truth
                        "is_placeholder": loc.is_placeholder,
                    }
                    for loc in self._cache.values()
                    if not loc.is_placeholder  # Don't persist placeholders
                ],
                "saved_at": datetime.now(UTC).isoformat(),
            }

            # Atomic write
            tmp_file = self._cache_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp_file.replace(self._cache_file)

            logger.debug("Saved %d locations to cache", len(self._cache))
        except Exception:
            logger.exception("Failed to save location cache")

    def get_cached_location(self, location_id: int) -> LocationInfo | None:
        """Get cached location info if available.

        Args:
            location_id: Location ID to look up

        Returns:
            LocationInfo if cached, None otherwise
        """
        return self._cache.get(location_id)

    def get_stale_locations(self, location_ids: set[int]) -> list[int]:
        """Get list of location IDs that are stale or not cached.

        Priority order:
        1. Unknown structures (not in cache at all) - highest priority
        2. Placeholder structures (failed to resolve before) - retry these
        3. Stale structures (stalest last) - oldest structures are lowest priority

        Args:
            location_ids: Set of location IDs to check

        Returns:
            List of stale location IDs, sorted by priority
        """
        unknown = []
        placeholders = []
        stale = []

        for loc_id in location_ids:
            loc = self._cache.get(loc_id)

            if not loc:
                # Unknown - highest priority
                unknown.append(loc_id)
            elif loc.is_placeholder:
                # Placeholder - retry to get real name
                placeholders.append((loc_id, loc.last_checked))
            else:
                # Stale - sort by age
                stale.append((loc_id, loc.last_checked))

        # Sort placeholders and stale by age (newest first, so stalest are last)
        placeholders.sort(key=lambda x: x[1], reverse=True)
        stale.sort(key=lambda x: x[1], reverse=True)

        # Return in priority order: unknown (new names), then placeholders (failed before), then stale (stalest last)
        return (
            unknown
            + [loc_id for loc_id, _ in placeholders]
            + [loc_id for loc_id, _ in stale]
        )

    async def resolve_locations_bulk(
        self,
        location_ids: list[int],
        character_id: int | None = None,
        refresh_stale: bool = True,
    ) -> dict[int, LocationInfo]:
        """Resolve multiple locations efficiently.

        Uses SDE data for public entities (regions, systems, stations) and
        ESI for player-owned structures.

        Args:
            location_ids: List of location IDs to resolve
            character_id: Character ID for structure access (optional)
            refresh_stale: Whether to refresh stale player structure cache entries

        Returns:
            Dict mapping location_id to LocationInfo
        """
        if not location_ids:
            return {}

        location_set = set(location_ids)
        results: dict[int, LocationInfo] = {}

        # Categorize location IDs by type based on ID ranges
        structure_ids = []  # Player structures needing ESI resolution

        now = datetime.now(UTC)

        for loc_id in location_set:
            if not isinstance(loc_id, int) or loc_id <= 0:
                logger.warning("Invalid location ID: %s", loc_id)
                continue

            # Check if this is a player structure (13+ digit IDs)
            if loc_id >= 1000000000000:
                # Player structure - check cache first
                cached = self._cache.get(loc_id)

                # If not refreshing stale, use any non-placeholder cached value
                if not refresh_stale and cached and not cached.is_placeholder:
                    logger.debug(
                        "Using cached structure %d: '%s' (no refresh)",
                        loc_id,
                        cached.custom_name or cached.name,
                    )
                    results[loc_id] = cached
                elif cached and not cached.is_placeholder:
                    logger.debug(
                        "Using cached structure %d: '%s' (age: %d days)",
                        loc_id,
                        cached.custom_name or cached.name,
                        (now - cached.last_checked).days if cached.last_checked else 0,
                    )
                    results[loc_id] = cached
                else:
                    # Need to resolve: missing, placeholder, or stale
                    if not cached:
                        logger.debug("Structure %d not in cache, will fetch", loc_id)
                    elif cached.is_placeholder:
                        logger.debug(
                            "Structure %d has placeholder name, will fetch real name",
                            loc_id,
                        )
                    else:
                        logger.debug(
                            "Structure %d cache is stale, will refresh", loc_id
                        )
                    structure_ids.append(loc_id)
            else:
                # Public entity - resolve from SDE
                name, category = self._resolve_from_sde(loc_id)
                if name:
                    loc = LocationInfo(
                        location_id=loc_id,
                        name=name,
                        category=category,
                        last_checked=now,
                    )
                    results[loc_id] = loc
                else:
                    logger.warning(
                        "Failed to resolve location ID %d - not in known ID ranges (regions: 10M-11M, constellations: 20M-30M, systems: 30M-40M, stations: 60M-70M, structures: 1000000000000+)",
                        loc_id,
                    )

        # Resolve player structures via ESI if needed
        if structure_ids:
            if character_id:
                logger.info(
                    "Resolving %d player structures via ESI: %s",
                    len(structure_ids),
                    structure_ids[:5]
                    if len(structure_ids) <= 5
                    else f"{structure_ids[:3]}... and {len(structure_ids) - 3} more",
                )
                await self._resolve_structures(structure_ids, character_id, results)
            else:
                logger.debug(
                    "Cannot resolve %d player structures without character_id",
                    len(structure_ids),
                )

        # Save updated cache (only contains player structures now)
        if structure_ids:
            async with self._cache_lock:
                self._save_cache()

        return results

    def _resolve_from_sde(self, location_id: int) -> tuple[str | None, str]:
        """Resolve a location name from SDE data.

        Args:
            location_id: Location ID to resolve

        Returns:
            Tuple of (name, category) or (None, "") if not found
        """
        # Region IDs: 10000000-10999999
        if 10000000 <= location_id < 11000000:
            name = self._sde.get_region_name(location_id)
            return (name, "region") if name else (None, "")

        # Constellation IDs: 20000000-29999999
        if 20000000 <= location_id < 30000000:
            name = self._sde.get_constellation_name(location_id)
            return (name, "constellation") if name else (None, "")

        # Solar System IDs: 30000000-39999999
        if 30000000 <= location_id < 40000000:
            name = self._sde.get_solar_system_name(location_id)
            return (name, "solar_system") if name else (None, "")

        # NPC Station IDs: 60000000-69999999
        if 60000000 <= location_id < 70000000:
            name = self._sde.get_npc_station_name(location_id)
            return (name, "station") if name else (None, "")

        # Unknown public ID range
        return (None, "")

    async def _resolve_structures(
        self,
        structure_ids: list[int],
        character_id: int | None,
        results: dict[int, LocationInfo],
    ) -> None:
        """Resolve structures using individual /universe/structures/ calls.

        Args:
            structure_ids: List of structure IDs
            character_id: Character ID for authentication
            results: Dict to update with resolved structures
        """
        if not character_id:
            logger.debug(
                "Cannot resolve %d structures without character_id", len(structure_ids)
            )
            return

        for struct_id in structure_ids:
            # Note: We don't skip failed structures anymore because:
            # 1. Auth tokens can be refreshed
            # 2. Access permissions can change
            # 3. We want to retry to get real names instead of placeholders

            try:
                logger.debug(
                    "Attempting to resolve structure %d for character %d",
                    struct_id,
                    character_id,
                )
                structure = await self._client.universe.get_structure_info(
                    structure_id=struct_id, character_id=character_id, use_cache=True
                )

                logger.debug(
                    "Successfully fetched structure %d: name='%s' owner=%d system=%d",
                    struct_id,
                    structure.name,
                    structure.owner_id,
                    structure.solar_system_id,
                )

                # Update cache and results
                now = datetime.now(UTC)

                # Get custom name if previously set in cache
                existing = self._cache.get(struct_id)
                custom_name = existing.custom_name if existing else None

                loc = LocationInfo(
                    location_id=struct_id,
                    name=structure.name,
                    category="structure",
                    last_checked=now,
                    owner_id=character_id,
                    custom_name=custom_name,
                    is_placeholder=False,
                )

                async with self._cache_lock:
                    self._cache[struct_id] = loc
                    results[struct_id] = loc
                    # Remove from failed structures if it was there
                    self._failed_structures.discard(struct_id)

                logger.debug(
                    "Successfully resolved structure %d: %s (custom: %s)",
                    struct_id,
                    structure.name,
                    custom_name or "none",
                )

            except Exception as e:
                # Mark as failed to avoid repeated attempts in this session
                self._failed_structures.add(struct_id)

                # Log at DEBUG for auth errors (common when access is revoked), WARNING for others
                error_str = str(e)
                if (
                    "401" in error_str
                    or "403" in error_str
                    or "Unauthorized" in error_str
                ):
                    logger.debug(
                        "Structure %d: Access denied (character may have lost docking rights or not in ACL)",
                        struct_id,
                    )
                else:
                    logger.debug("Failed to resolve structure %d: %s", struct_id, e)

                # Check if we have a previous cached name to keep using
                async with self._cache_lock:
                    existing = self._cache.get(struct_id)

                    if existing and not existing.is_placeholder:
                        # Keep the existing name (access was lost but we know the name)
                        logger.debug(
                            "Structure %d: Keeping last known name '%s' (access lost)",
                            struct_id,
                            existing.custom_name or existing.name,
                        )
                        # Update last_checked to prevent immediate re-resolution
                        existing.last_checked = datetime.now(UTC)
                        results[struct_id] = existing
                    else:
                        # No previous name - return placeholder for UI display only (don't cache it)
                        logger.debug(
                            "Structure %d: No previous name available, using placeholder for display",
                            struct_id,
                        )
                        placeholder = LocationInfo(
                            location_id=struct_id,
                            name=f"Structure {struct_id}",
                            category="structure",
                            last_checked=datetime.now(UTC),
                            owner_id=character_id,
                            custom_name=(existing.custom_name if existing else None),
                            is_placeholder=True,
                        )
                        # Return placeholder for immediate use but DON'T save to cache
                        results[struct_id] = placeholder

                # Continue with other structures

    async def resolve_location(
        self, location_id: int, character_id: int | None = None
    ) -> LocationInfo | None:
        """Resolve a single location.

        Args:
            location_id: Location ID to resolve
            character_id: Character ID for structure access

        Returns:
            LocationInfo if resolved, None on failure
        """
        results = await self.resolve_locations_bulk([location_id], character_id)
        return results.get(location_id)

    def clear_failed_structures(self) -> None:
        """Clear the list of failed structures to allow retry."""
        count = len(self._failed_structures)
        self._failed_structures.clear()
        logger.info("Cleared %d failed structure entries", count)

    def set_custom_name(self, location_id: int, custom_name: str | None) -> None:
        """Set a custom user-defined name for a location.

        Args:
            location_id: Location ID
            custom_name: Custom name to set, or None to remove custom name
        """
        # Update in-memory cache immediately for UI responsiveness
        now = datetime.now(UTC)

        existing = self._cache.get(location_id)
        if custom_name:
            if existing:
                existing.custom_name = custom_name
                existing.last_checked = now
                if existing.is_placeholder:
                    existing.is_placeholder = False
            else:
                # Create a placeholder entry for the custom-named location
                loc = LocationInfo(
                    location_id=location_id,
                    name=custom_name,
                    category="structure",
                    last_checked=now,
                    owner_id=None,
                    custom_name=custom_name,
                    is_placeholder=True,
                )
                self._cache[location_id] = loc
            logger.info("Set custom name for location %d: %s", location_id, custom_name)
        else:
            # Remove custom name
            if existing:
                existing.custom_name = None
                existing.last_checked = now
            logger.info("Removed custom name for location %d", location_id)

        # Persist to SettingsManager (source of truth for custom names)
        if self._settings:
            self._settings.set_custom_location(location_id, custom_name)
        else:
            logger.warning(
                "No settings manager configured - custom name change not persisted"
            )

    def get_display_name(self, location_id: int) -> str | None:
        """Get the display name for a location, preferring custom name over ESI name.

        Args:
            location_id: Location ID

        Returns:
            Display name (custom if set, otherwise ESI name) or None if not cached
        """
        loc = self._cache.get(location_id)
        if not loc:
            return None

        # Prefer custom name if set
        return loc.custom_name or loc.name

    def has_conflict(self, location_id: int) -> bool:
        """Check if a location has a conflict between custom and ESI names.

        Args:
            location_id: Location ID

        Returns:
            True if location has both a custom name and a different ESI name
        """
        loc = self._cache.get(location_id)
        if not loc:
            return False

        return bool(loc.custom_name and loc.name and loc.custom_name != loc.name)

    def get_conflicting_locations(self) -> list[tuple[int, str, str]]:
        """Get all locations with conflicts between custom and ESI names.

        Returns:
            List of (location_id, custom_name, esi_name) tuples
        """
        conflicts = []
        for loc_id, loc in self._cache.items():
            if loc.custom_name and loc.name and loc.custom_name != loc.name:
                conflicts.append((loc_id, loc.custom_name, loc.name))
        return conflicts

    def get_all_custom_names(self) -> list[tuple[int, str, str | None]]:
        """Get all locations that have a custom name set.

        Returns:
            List of (location_id, custom_name, esi_name_or_none)
        """
        out: list[tuple[int, str, str | None]] = []
        for loc_id, loc in self._cache.items():
            if loc.custom_name:
                out.append((loc_id, loc.custom_name, loc.name if loc.name else None))
        # Sort by location_id for consistent presentation
        out.sort(key=lambda x: x[0])
        return out
