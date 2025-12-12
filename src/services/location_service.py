"""Service for resolving and caching location names.

Resolves location names from static data (SDE) for public entities and ESI for player structures.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from models.app import LocationInfo
from utils.config import get_config

if TYPE_CHECKING:
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
    ):
        """Initialize location service.

        Args:
            esi_client: ESI client for API requests
            sde_provider: SDE provider for NPC station lookups
        """
        self._client = esi_client
        self._sde = sde_provider
        self._cache_file = get_config().app.user_data_dir / self.CACHE_FILE

        # Ensure cache directory exists
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("Failed to create location cache directory: %s", e)

        # In-memory cache: location_id -> LocationInfo
        self._cache: dict[int, LocationInfo] = {}

        # Load location cache and apply custom names from settings
        self._load_cache()

        # Track which structures we've attempted to fetch (to avoid repeated failures)
        self._failed_structures: set[int] = set()
        # Backoff tracking for recent failures (struct_id -> next_allowed_datetime)
        self._failed_structures_backoff: dict[int, datetime] = {}

        # Pending in-flight structure resolutions to coalesce concurrent requests
        self._pending_structures: dict[int, asyncio.Future[LocationInfo | None]] = {}

        # Lock for cache modifications
        self._cache_lock = asyncio.Lock()

    def _load_cache(self) -> None:
        """Load location cache from disk and apply custom names from settings."""
        if not self._cache_file.exists():
            logger.debug("No location cache file found")
            try:
                # Create an empty cache file so future loads don't warn
                self._save_cache()
            except Exception:
                logger.debug(
                    "Unable to create initial location cache file", exc_info=True
                )
        else:
            try:
                with open(self._cache_file, encoding="utf-8") as f:
                    data = json.load(f)

                for entry in data.get("locations", []):
                    try:
                        canonical_name = entry.get("esi_name") or entry.get("name")
                        loc = LocationInfo(
                            location_id=entry["location_id"],
                            name=canonical_name,
                            esi_name=canonical_name,
                            category=entry["category"],
                            last_checked=datetime.fromisoformat(entry["last_checked"]),
                            owner_id=entry.get("owner_id"),
                            custom_name=entry.get("custom_name"),
                            is_placeholder=entry.get("is_placeholder", False),
                            solar_system_id=entry.get("solar_system_id"),
                            metadata=entry.get("metadata"),
                        )
                        # Don't load placeholders from cache - they'll be re-resolved
                        if not loc.is_placeholder:
                            self._cache[loc.location_id] = loc
                    except (KeyError, ValueError) as e:
                        logger.debug("Skipping invalid cache entry: %s", e)

                logger.info("Loaded %d locations from cache", len(self._cache))
            except Exception as e:
                logger.warning("Failed to load location cache: %s", e)

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
                        "esi_name": loc.esi_name or loc.name,
                        "custom_name": loc.custom_name,
                        "is_placeholder": loc.is_placeholder,
                        "solar_system_id": loc.solar_system_id,
                        "metadata": loc.metadata or {},
                    }
                    for loc in self._cache.values()
                    # Persist entries that have custom data even if they were
                    # previously placeholders.
                    if not loc.is_placeholder
                    or loc.custom_name
                    or (
                        isinstance(loc.metadata, dict)
                        and loc.metadata.get("custom_overrides")
                    )
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

    def get_custom_location_data(self, location_id: int) -> dict[str, Any] | None:
        """Return custom override data (name/system) for a location from cache."""

        loc = self._cache.get(location_id)
        if not loc:
            return None

        data: dict[str, Any] = {}
        if loc.custom_name:
            data["name"] = loc.custom_name

        metadata = loc.metadata or {}
        custom_meta = (
            metadata.get("custom_overrides") if isinstance(metadata, dict) else None
        )
        if custom_meta and isinstance(custom_meta, dict):
            if custom_meta.get("system_id") is not None:
                try:
                    data["system_id"] = int(custom_meta.get("system_id"))
                except Exception:
                    pass

        return data or None

    def get_all_custom_locations(self) -> dict[int, dict[str, Any]]:
        """Return all locations that have custom overrides stored in cache."""

        result: dict[int, dict[str, Any]] = {}
        for loc_id in self._cache:
            data = self.get_custom_location_data(loc_id)
            if data:
                result[int(loc_id)] = data
        return result

    def _ensure_cache_entry(self, location_id: int) -> LocationInfo:
        """Get or create a cache entry for a location."""

        loc = self._cache.get(location_id)
        if loc:
            return loc

        now = datetime.now(UTC)
        loc = LocationInfo(
            location_id=location_id,
            name=str(location_id),
            category="structure",
            last_checked=now,
            owner_id=None,
            custom_name=None,
            is_placeholder=True,
            solar_system_id=None,
            metadata={},
        )
        self._cache[location_id] = loc
        return loc

    def set_custom_location_data(
        self,
        location_id: int,
        *,
        name: str | None = None,
        system_id: int | None = None,
        persist: bool = True,
    ) -> None:
        """Persist custom location overrides into the locations cache.

        Both custom names and system overrides are stored in the locations.json
        cache file. Any provided override will be persisted immediately.
        Passing ``None`` for both parameters clears existing overrides.
        """

        loc = self._ensure_cache_entry(location_id)

        # Normalize name
        cleaned_name = None
        if name is not None:
            cleaned = str(name).strip()
            cleaned_name = cleaned or None

        # Normalize system id
        sys_override: int | None = None
        if system_id is not None:
            try:
                sys_override = int(system_id)
            except Exception:
                sys_override = None

        metadata = loc.metadata or {}
        if not isinstance(metadata, dict):
            metadata = {}

        custom_meta = metadata.get("custom_overrides")
        if not isinstance(custom_meta, dict):
            custom_meta = {}

        if sys_override is not None:
            # Preserve original system id if present for potential restoration
            if loc.solar_system_id is not None and "original_system_id" not in metadata:
                metadata["original_system_id"] = loc.solar_system_id
            custom_meta["system_id"] = sys_override
            loc.solar_system_id = sys_override
        else:
            # Clear override and restore original if available
            custom_meta.pop("system_id", None)
            if "original_system_id" in metadata:
                loc.solar_system_id = metadata.pop("original_system_id")

        # Persist name override
        loc.custom_name = cleaned_name

        # Remove empty custom meta to avoid clutter
        if custom_meta:
            metadata["custom_overrides"] = custom_meta
        else:
            metadata.pop("custom_overrides", None)

        loc.metadata = metadata or None
        # Custom overrides should not be treated as placeholders so they get saved
        loc.is_placeholder = False

        # Save cache to disk
        if persist:
            self._save_cache()

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
                    # Get system_id for stations
                    system_id = None
                    if category == "station":
                        system_id = self._sde.get_npc_station_system_id(loc_id)

                    loc = LocationInfo(
                        location_id=loc_id,
                        name=name,
                        esi_name=name,
                        category=category,
                        last_checked=now,
                        solar_system_id=system_id,
                        metadata={"source": "sde"},
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

        # Planet IDs (approximate range 40000000-49999999) - SDE planet names not yet loaded
        if 40000000 <= location_id < 50000000:
            # Placeholder naming until parser gains planet name support
            return (f"Planet {location_id}", "planet")

        # NPC Station IDs: 60000000-69999999
        if 60000000 <= location_id <= 69999999:
            name = self._sde.get_npc_station_name(location_id)
            # Note: system_id is handled separately in resolve_locations_bulk
            if name:
                return (name, "station")
            # Fallback for missing stations in SDE data
            logger.debug(
                "Station ID %d not found in SDE, using placeholder name",
                location_id,
            )
            return (f"Unknown Station {location_id}", "station")

        # Unknown public ID range
        return (None, "")

    async def _resolve_structures(
        self,
        structure_ids: list[int],
        character_id: int | None,
        results: dict[int, LocationInfo],
    ) -> None:
        """Resolve structures using batched /universe/structures/ calls.

        Resolves structures in batches to avoid overwhelming rate limits.
        Uses ~10-20% of available rate limit tokens per batch.

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

        # Determine batch size based on rate limit capacity
        # Aim for 10-20% of limit per batch to leave headroom for other requests
        rate_limiter = self._client.rate_limiter
        batch_size = 10  # Default conservative batch size

        # Try to get rate limit info for universe endpoints
        universe_group_key = None
        for group_key in rate_limiter.rate_limit_groups.keys():
            if "universe" in group_key.lower():
                universe_group_key = group_key
                break

        if universe_group_key:
            group_info = rate_limiter.rate_limit_groups.get(universe_group_key, {})
            limit = group_info.get("limit", 100)
            # Use 15% of limit for batch size
            batch_size = max(5, min(20, int(limit * 0.15)))
            logger.debug(
                "Using batch size %d for structure resolution (rate limit: %d)",
                batch_size,
                limit,
            )

        total = len(structure_ids)
        resolved = 0

        # Process structures in batches
        for i in range(0, len(structure_ids), batch_size):
            batch = structure_ids[i : i + batch_size]
            now = datetime.now(UTC)
            # Skip structures that are still in backoff window
            batch = [
                sid
                for sid in batch
                if self._failed_structures_backoff.get(
                    sid, datetime.min.replace(tzinfo=UTC)
                )
                <= now
            ]
            if not batch:
                continue
            logger.info(
                "Resolving structure batch %d-%d of %d",
                i + 1,
                min(i + len(batch), total),
                total,
            )

            # Process batch concurrently
            tasks = [
                self._resolve_structure_coalesced(struct_id, character_id)
                for struct_id in batch
            ]
            structures = await asyncio.gather(*tasks, return_exceptions=True)

            for struct_id, loc in zip(batch, structures, strict=True):
                if isinstance(loc, Exception):
                    logger.debug(
                        "Structure %d resolution returned exception: %s",
                        struct_id,
                        loc,
                    )
                    continue
                if loc is not None:
                    results[struct_id] = loc
            resolved += len(batch)

            # Small delay between batches to allow rate limit tokens to regenerate
            if i + batch_size < len(structure_ids):
                await asyncio.sleep(0.5)

        logger.info(
            "Completed structure resolution: %d/%d processed",
            resolved,
            total,
        )

        # Persist any newly resolved structures to disk so subsequent runs
        # don't re-fetch them and custom names remain merged with ESI data.
        try:
            self._save_cache()
        except Exception:
            logger.debug(
                "Failed to persist location cache after resolution", exc_info=True
            )

    async def resolve_structures_multi_character(
        self,
        structure_ids: set[int],
        character_ids: list[int],
    ) -> dict[int, LocationInfo]:
        """Resolve structures efficiently across multiple characters.

        Instead of trying each structure with each character, this method:
        1. Collects unique structures needed across all characters
        2. Tries each structure with the first character that has assets there
        3. Falls back to trying other characters if first one fails
        4. Caches which characters have access to which structures

        This dramatically reduces API calls when multiple characters share structures.

        Args:
            structure_ids: Set of structure IDs to resolve
            character_ids: List of character IDs that might have access

        Returns:
            Dict mapping structure_id to LocationInfo
        """
        if not structure_ids or not character_ids:
            return {}

        results: dict[int, LocationInfo] = {}
        remaining_structures = list(structure_ids)

        # Try with first character for all structures
        if character_ids:
            primary_char = character_ids[0]
            logger.info(
                "Attempting to resolve %d structures with primary character %d",
                len(remaining_structures),
                primary_char,
            )
            await self._resolve_structures(remaining_structures, primary_char, results)

            # Check which structures still need resolution (failed with primary)
            remaining_structures = [
                sid for sid in remaining_structures if sid not in results
            ]

        # For any structures that failed, try with remaining characters
        if remaining_structures and len(character_ids) > 1:
            logger.info(
                "%d structures need retry with alternate characters",
                len(remaining_structures),
            )
            for char_id in character_ids[1:]:
                if not remaining_structures:
                    break

                logger.debug(
                    "Retrying %d structures with character %d",
                    len(remaining_structures),
                    char_id,
                )
                await self._resolve_structures(remaining_structures, char_id, results)

                # Update remaining structures
                remaining_structures = [
                    sid for sid in remaining_structures if sid not in results
                ]

        logger.info(
            "Multi-character structure resolution complete: %d/%d resolved",
            len(results),
            len(structure_ids),
        )

        return results

    async def _resolve_single_structure(
        self,
        struct_id: int,
        character_id: int,
    ) -> LocationInfo | None:
        """Resolve a single structure (helper for batched resolution).

        Args:
            struct_id: Structure ID to resolve
            character_id: Character ID for authentication

        Returns:
            LocationInfo (resolved or placeholder) or None on unrecoverable error.
        """
        # Note: We don't skip failed structures because:
        # 1. Auth tokens can be refreshed
        # 2. Access permissions can change
        # 3. We want to retry to get real names instead of placeholders

        try:
            logger.debug(
                "Attempting to resolve structure %d for character %d",
                struct_id,
                character_id,
            )
            structure, _ = await self._client.universe.get_structure_info(
                structure_id=struct_id, character_id=character_id, use_cache=True
            )

            logger.debug(
                "Successfully fetched structure %d: name='%s' owner=%d system=%d",
                structure.structure_id,
                structure.name,
                getattr(structure, "owner_id", -1),
                getattr(structure, "solar_system_id", -1),
            )

            now = datetime.now(UTC)

            owner_id_val = getattr(structure, "owner_id", None)

            # Get custom overrides if previously set in cache
            existing = self._cache.get(structure.structure_id)
            custom_name = existing.custom_name if existing else None

            existing_metadata: dict[str, Any] = {}
            if existing and isinstance(existing.metadata, dict):
                existing_metadata = dict(existing.metadata)

            custom_overrides = existing_metadata.get("custom_overrides")
            sys_override = None
            if isinstance(custom_overrides, dict):
                sys_override = custom_overrides.get("system_id")

            # Extract solar_system_id from structure info (respect override if present)
            if sys_override is not None:
                try:
                    solar_system_id = int(sys_override)
                except Exception:
                    solar_system_id = getattr(structure, "solar_system_id", None)
            else:
                solar_system_id = getattr(structure, "solar_system_id", None)

            metadata = existing_metadata or {}
            metadata["source"] = "esi"
            # Preserve custom override metadata if present
            if custom_overrides:
                metadata["custom_overrides"] = custom_overrides

            loc = LocationInfo(
                location_id=structure.structure_id,
                name=structure.name,
                esi_name=structure.name,
                category="structure",
                last_checked=now,
                owner_id=owner_id_val,
                custom_name=custom_name,
                is_placeholder=False,
                solar_system_id=solar_system_id,
                metadata=metadata,
            )

            # Cache the resolved structure for future use
            self._cache[structure.structure_id] = loc
            # Maintain minimal internal state unrelated to cache
            self._failed_structures.discard(structure.structure_id)
            self._failed_structures_backoff.pop(structure.structure_id, None)

            logger.debug(
                "Successfully resolved structure %d: %s (custom: %s)",
                structure.structure_id,
                structure.name,
                custom_name or "none",
            )

            return loc

        except Exception as e:
            # Mark as failed to avoid repeated attempts in this session
            self._failed_structures.add(struct_id)
            backoff = getattr(
                get_config().app, "structure_resolution_backoff", timedelta(seconds=300)
            )
            if isinstance(backoff, (int, float)):
                backoff = timedelta(seconds=backoff)
            self._failed_structures_backoff[struct_id] = datetime.now(UTC) + backoff

            # Log at DEBUG for auth errors (common when access is revoked), WARNING for others
            error_str = str(e)
            if "401" in error_str or "403" in error_str or "Unauthorized" in error_str:
                logger.debug(
                    "Structure %d: Access denied (character may have lost docking rights or not in ACL)",
                    struct_id,
                )
            else:
                logger.debug("Failed to resolve structure %d: %s", struct_id, e)

            # Check if we have a previous cached name to keep using
            # Read-only existing cache entry if present; avoid mutating cache
            existing = self._cache.get(struct_id)

            if existing and not existing.is_placeholder:
                # Keep the existing name (access was lost but we know the name)
                logger.debug(
                    "Structure %d: Keeping last known name '%s' (access lost)",
                    struct_id,
                    existing.custom_name or existing.name,
                )
                # Return a copy with updated last_checked for immediate use
                return LocationInfo(
                    location_id=existing.location_id,
                    name=existing.name,
                    category=existing.category,
                    last_checked=datetime.now(UTC),
                    owner_id=existing.owner_id,
                    custom_name=existing.custom_name,
                    is_placeholder=False,
                )

            # No previous name - return placeholder for UI display only (don't cache it)
            logger.debug(
                "Structure %d: No previous name available, using placeholder for display",
                struct_id,
            )
            return LocationInfo(
                location_id=struct_id,
                name=f"Structure {struct_id}",
                esi_name=f"Structure {struct_id}",
                category="structure",
                last_checked=datetime.now(UTC),
                owner_id=character_id,
                custom_name=(existing.custom_name if existing else None)
                if existing
                else None,
                is_placeholder=True,
            )

    async def _resolve_structure_coalesced(
        self, struct_id: int, character_id: int
    ) -> LocationInfo | None:
        """Coalesce concurrent structure lookups for the same ID.

        Ensures only one outbound ESI request is in-flight for a given
        structure ID at a time, reducing startup load and duplicate log noise.
        """

        existing = self._pending_structures.get(struct_id)
        if existing:
            return await existing

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[LocationInfo | None] = loop.create_future()
        self._pending_structures[struct_id] = fut
        try:
            loc = await self._resolve_single_structure(struct_id, character_id)
            fut.set_result(loc)
            return loc
        except Exception as exc:  # pragma: no cover - defensive
            if not fut.done():
                fut.set_exception(exc)
            raise
        finally:
            self._pending_structures.pop(struct_id, None)

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
        """Backward-compatible wrapper to set only the custom name."""

        self.set_custom_location_data(location_id, name=custom_name)
        if custom_name:
            logger.info("Set custom name for location %d: %s", location_id, custom_name)
        else:
            logger.info("Removed custom name for location %d", location_id)

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
        return loc.custom_name or loc.esi_name or loc.name

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
