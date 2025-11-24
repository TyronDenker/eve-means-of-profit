"""Rate limiting with token bucket system for ESI requests.

ESI uses a floating window token-bucket system per route group (X-Ratelimit-*). Each request
typically consumes tokens based on response status:
- 2XX: 2 tokens
- 3XX: 1 token (promotes caching with ETags)
- 4XX: 5 tokens (discourages errors)
- 5XX: 0 tokens (server errors don't penalize clients)

This module also tracks the older error-rate system exposed via X-ESI-Error-Limit-*
(error remaining and reset seconds) for endpoints that haven't migrated yet.
"""

import asyncio
import json
import logging
import os
import random
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from utils import global_config

logger = logging.getLogger(__name__)


class RateLimitTracker:
    """Tracks ESI token bucket rate limits and error limits.

    Monitors both the token bucket system (X-Ratelimit-*) for most endpoints
    and the older error limit system (X-ESI-Error-Limit-*) for unmigrated endpoints.
    """

    def __init__(
        self,
        max_backoff_delay: int = 60,
        persist_file: str | Path | None = None,
    ):
        """Initialize rate limit tracker.

        Args:
            max_backoff_delay: Maximum backoff delay in seconds
            persist_file: Path to rate limit persistence file (defaults to config.esi.rate_limit_file_path)
        """
        # Old error limit system
        self.error_remain: int | None = None
        self.error_reset: datetime | None = None

        # New token bucket system
        self.max_backoff_delay = max_backoff_delay

        # Configured capacity for legacy error-limit headers (used with percentage)
        try:
            self.error_capacity = int(global_config.esi.error_limit_capacity)
        except Exception:
            self.error_capacity = 10

        self.rate_limit_groups: dict[
            str, dict
        ] = {}  # group -> {limit, remaining, used}

        self._backoff_levels: dict[str, int] = {}  # Per-group backoff tracking

        # Persistence
        if persist_file is None:
            self._persist_file = str(global_config.esi.rate_limit_file_path)
        else:
            self._persist_file = str(persist_file)

        if self._persist_file:
            # Ensure directory exists (guard against empty dirname)
            try:
                persist_dir = os.path.dirname(self._persist_file)
                if persist_dir:  # Only create if dirname is not empty
                    os.makedirs(persist_dir, exist_ok=True)
            except Exception as e:
                logger.debug("Could not create rate limit persist directory: %s", e)
            # Try to load existing state
            self._load()

    def update_from_headers(self, headers: dict, group_key: str | None = None) -> None:
        """Update rate limit state from response headers.

        Handles both old error limit system and new token bucket system.

        Args:
            headers: Response headers containing rate limit info
        """
        # Decide which system to use based on header presence.
        has_new = self._has_new_headers(headers)
        has_old = self._has_old_headers(headers)

        if has_new:
            # Token-bucket system takes precedence
            self._handle_new_token_bucket(headers, group_key)
            # Also update old error info if present (some endpoints send both)
            if has_old:
                self._handle_old_error_limit(headers)
        elif has_old:
            # Only old error limit headers present (unmigrated endpoint)
            self._handle_old_error_limit(headers)
        else:
            # No rate-limit headers present - do nothing
            return

    def _has_new_headers(self, headers: dict) -> bool:
        """Return True if headers contain any of the X-Ratelimit-* fields."""
        return any(
            headers.get(h) is not None
            for h in (
                "x-ratelimit-group",
                "x-ratelimit-limit",
                "x-ratelimit-remaining",
                "x-ratelimit-used",
            )
        )

    def _has_old_headers(self, headers: dict) -> bool:
        """Return True if headers contain older X-ESI-Error-Limit-* fields."""
        return any(
            headers.get(h) is not None
            for h in ("x-esi-error-limit-remain", "x-esi-error-limit-reset")
        )

    def _handle_old_error_limit(self, headers: dict) -> None:
        """Handle the older X-ESI-Error-Limit-* headers.

        This updates self.error_remain and self.error_reset.
        """
        if error_remain := headers.get("x-esi-error-limit-remain"):
            try:
                self.error_remain = int(error_remain)
            except ValueError:
                pass

        if error_reset := headers.get("x-esi-error-limit-reset"):
            try:
                val = int(error_reset)
                # X-ESI-Error-Limit-Reset is seconds remaining until reset
                self.error_reset = datetime.now(UTC) + timedelta(seconds=val)
            except ValueError:
                pass

    def _handle_new_token_bucket(self, headers: dict, group_key: str | None) -> None:
        """Handle the new token-bucket based rate limiting headers.

        Parses X-Ratelimit-* headers and updates self.rate_limit_groups.

        Bucket keying strategy:
        - Public endpoints: use group name alone (e.g., "market") — shared per application
        - Authenticated endpoints: use "group:character_id" (e.g., "character:12345") — per character
        The caller (ESI client) must provide group_key with character suffix when appropriate.
        """
        if rate_group := headers.get("x-ratelimit-group"):
            limit_str = headers.get("x-ratelimit-limit", "")
            remaining_str = headers.get("x-ratelimit-remaining", "")
            used_str = headers.get("x-ratelimit-used", "")

            try:
                # Parse limit string (e.g., "150/15m")
                max_tokens, window_seconds = self._parse_limit_string(limit_str)

                remaining = int(remaining_str) if remaining_str else None
                used = int(used_str) if used_str else None

                # Determine storage key: prefer caller-provided group_key (includes character ID for auth endpoints)
                store_key = group_key if group_key else rate_group

                # Infer token cost from previous state (if available)
                cost_per_request = self._infer_token_cost(store_key, used)

                # Compute rate metrics
                tokens_per_second = (
                    max_tokens / window_seconds if window_seconds and max_tokens else 0
                )
                tokens_per_request = cost_per_request if cost_per_request else 2.0
                requests_per_second = (
                    tokens_per_second / tokens_per_request
                    if tokens_per_second and tokens_per_request
                    else 0
                )

                # Update bucket state
                self._update_bucket(
                    store_key,
                    max_tokens,
                    remaining,
                    used,
                    window_seconds,
                    tokens_per_second,
                    tokens_per_request,
                    requests_per_second,
                )
            except ValueError:
                pass

    def _parse_limit_string(self, limit_str: str) -> tuple[int, int]:
        """Parse X-Ratelimit-Limit header (e.g., '150/15m') into max tokens and window seconds.

        Args:
            limit_str: Limit string from header

        Returns:
            Tuple of (max_tokens, window_seconds)
        """
        max_tokens = 0
        window_seconds = 1

        if "/" in limit_str:
            left, right = limit_str.split("/", 1)
            max_tokens = int(left)
            # right can be like '15m', '1h', '3600s'
            unit = right.strip().lower()
            if unit.endswith("m"):
                window_seconds = int(unit[:-1]) * 60
            elif unit.endswith("h"):
                window_seconds = int(unit[:-1]) * 3600
            elif unit.endswith("s"):
                window_seconds = int(unit[:-1])
            else:
                # Fallback: try parse as integer seconds
                try:
                    window_seconds = int(unit)
                except ValueError:
                    window_seconds = 1
        else:
            max_tokens = int(limit_str) if limit_str else 0

        return max_tokens, window_seconds

    def _infer_token_cost(
        self, store_key: str, current_used: int | None
    ) -> float | None:
        """Infer token cost per request by comparing current and previous 'used' values.

        Args:
            store_key: Bucket key (group or group:character_id)
            current_used: Current 'used' count from headers

        Returns:
            Inferred cost per request, or None if not inferrable
        """
        prev_info = self.rate_limit_groups.get(store_key, {})
        prev_used = prev_info.get("used")

        # Infer cost if both values are present and used increased
        if (
            prev_used is not None
            and current_used is not None
            and current_used > prev_used
        ):
            return float(current_used - prev_used)

        return None

    def _update_bucket(
        self,
        store_key: str,
        max_tokens: int,
        remaining: int | None,
        used: int | None,
        window_seconds: int,
        tokens_per_second: float,
        tokens_per_request: float,
        requests_per_second: float,
    ) -> None:
        """Update bucket state and persist to disk.

        Args:
            store_key: Bucket key (group name or group:character_id)
            max_tokens: Max tokens in window
            remaining: Tokens remaining
            used: Tokens used
            window_seconds: Window size in seconds
            tokens_per_second: Computed tokens/sec
            tokens_per_request: Computed tokens/request
            requests_per_second: Computed requests/sec
        """
        self.rate_limit_groups[store_key] = {
            "limit": max_tokens,
            "remaining": remaining,
            "used": used,
            "last_updated": datetime.now(
                UTC
            ),  # Track when tokens were spent for regeneration calculation
            "window_seconds": window_seconds,
            "tokens_per_second": tokens_per_second,
            "tokens_per_request": tokens_per_request,
            "requests_per_second": requests_per_second,
        }
        # Persist updated token bucket info (saves all buckets)
        self._persist()

    def get_available_tokens(self, group_key: str) -> int | None:
        """Calculate currently available tokens accounting for regeneration since last update.

        ESI uses a sliding window token bucket - tokens regenerate continuously based on
        tokens_per_second. This method projects current availability from last known state.

        Args:
            group_key: Bucket key (group name or group:character_id)

        Returns:
            Projected available tokens, or None if bucket not tracked
        """
        bucket = self.rate_limit_groups.get(group_key)
        if not bucket:
            return None

        last_updated = bucket.get("last_updated")
        remaining = bucket.get("remaining")
        tokens_per_second = bucket.get("tokens_per_second")
        limit = bucket.get("limit")

        # If we have timestamp and regeneration rate, compute projected availability
        if (
            last_updated
            and remaining is not None
            and tokens_per_second
            and limit is not None
        ):
            elapsed = (datetime.now(UTC) - last_updated).total_seconds()
            regenerated = elapsed * tokens_per_second
            # Cap at bucket limit
            available = min(remaining + regenerated, limit)
            return int(available)

        # Fall back to last known remaining count
        return remaining

    def _get_threshold_tokens(self, group_key: str) -> int | None:
        """Compute threshold token count for a bucket using configured percentage.

        Returns an integer token count or None if not computable (falls back to absolute threshold).
        """
        bucket = self.rate_limit_groups.get(group_key)
        if not bucket:
            return None

        limit = bucket.get("limit")
        if not limit:
            return None

        try:
            percent = float(global_config.esi.rate_limit_threshold_percent)
            if percent <= 0:
                return None

            return max(1, int(limit * (percent / 100.0)))

        except Exception:
            return None

    def should_backoff(self, group_key: str | None = None) -> bool:
        """Check if we should back off due to rate limits for a specific endpoint.

        This is context-aware: checks the specific bucket for token-bucket endpoints,
        or legacy error limits for old-system endpoints.

        Args:
            group_key: Bucket key for new token-bucket system endpoints (e.g., "market" or "character:12345")
                      If None, checks legacy error limit system only.

        Returns:
            True if we should wait before next request
        """
        if group_key:
            # New token bucket system - check specific bucket with regeneration
            available = self.get_available_tokens(group_key)
            if available is not None:
                threshold = self._get_threshold_tokens(group_key)
                if threshold is not None:
                    return available < threshold
                return False
            # No data for this bucket - don't block (optimistic)
            return False

        if self.error_remain is not None:
            # Legacy error limit system
            try:
                pct = float(global_config.esi.rate_limit_threshold_percent)
                threshold = max(1, int(self.error_capacity * (pct / 100.0)))
            except Exception:
                threshold = 1
            return self.error_remain < threshold
        return False

    async def wait_if_needed(self, group_key: str | None = None) -> None:
        """Wait if we're approaching rate limits for a specific endpoint.

        Implements graduated slowdown based on token scarcity:
        - When tokens fall below threshold, delay increases proportionally
        - More scarcity = longer delay (smooth load balancing)
        - Uses per-group backoff levels for isolation

        Args:
            group_key: Bucket key for token-bucket endpoints, None for unmigrated endpoints
        """
        if not self.should_backoff(group_key):
            return

        # If we have a reset time and it's in the future, wait until then
        if self.error_reset and group_key is None:
            now = datetime.now(UTC)
            if now < self.error_reset:
                wait_seconds = (self.error_reset - now).total_seconds()
                # Compute threshold for logging
                try:
                    pct = float(global_config.esi.rate_limit_threshold_percent)
                    error_thresh = max(1, int(self.error_capacity * (pct / 100.0)))
                except Exception:
                    error_thresh = None

                logger.info(
                    "Rate limit low (remaining=%s). Waiting %.1fs until reset (threshold=%s)",
                    self.error_remain,
                    wait_seconds,
                    error_thresh,
                )
                await asyncio.sleep(wait_seconds)
                if group_key:
                    self._backoff_levels[group_key] = 0
                return

        # Graduated slowdown for token bucket endpoints
        if group_key:
            available = self.get_available_tokens(group_key)
            if available is not None:
                # Determine threshold tokens (prefer percent-based when available)
                threshold = self._get_threshold_tokens(group_key)

                if threshold is not None and available < threshold:
                    # Calculate scarcity ratio (0.0 = at threshold, 1.0 = no tokens)
                    scarcity_ratio = min(
                        1.0, (threshold - available) / max(1, threshold)
                    )

                    # Get per-group backoff level
                    backoff_level = self._backoff_levels.get(group_key, 0)

                    # Apply proportional delay with exponential backoff component
                    base_delay = 2.0  # Base delay in seconds
                    delay = base_delay * scarcity_ratio * (1 + backoff_level)
                    delay = min(delay, self.max_backoff_delay)

                    # Add jitter (±10%)
                    jitter = delay * 0.1 * (2 * random.random() - 1)
                    actual_delay = max(0.1, delay + jitter)

                    logger.debug(
                        "Graduated slowdown: group=%s available=%d/%d threshold=%d scarcity=%.2f backoff_level=%d delay=%.2fs",
                        group_key,
                        available,
                        threshold,
                        threshold,
                        scarcity_ratio,
                        backoff_level,
                        actual_delay,
                    )
                    await asyncio.sleep(actual_delay)
                    return

        # Otherwise use exponential backoff (old error limit system)
        await self._exponential_backoff(group_key or "old_system")

    async def _exponential_backoff(self, group_key: str) -> None:
        """Implement exponential backoff with jitter per group.

        Args:
            group_key: Rate limit group key for isolated backoff tracking
        """
        backoff_level = self._backoff_levels.get(group_key, 0)
        base_delay = 2**backoff_level
        delay = min(base_delay, self.max_backoff_delay)

        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        actual_delay = delay + jitter

        logger.info(
            "Backing off for %.1fs (group=%s backoff_level=%d error_budget=%s)",
            actual_delay,
            group_key,
            backoff_level,
            self.error_remain,
        )
        await asyncio.sleep(actual_delay)

        # Increment backoff level for this group (cap at 2^6 = 64s)
        self._backoff_levels[group_key] = min(backoff_level + 1, 6)

    def _increment_backoff(self, group_key: str) -> None:
        """Increment backoff level for a specific group.

        Args:
            group_key: Rate limit group key
        """
        current = self._backoff_levels.get(group_key, 0)
        self._backoff_levels[group_key] = min(current + 1, 6)  # Cap at 2^6 = 64s
        logger.debug(
            "Incremented backoff for group=%s to level=%d",
            group_key,
            self._backoff_levels[group_key],
        )

    async def handle_429(
        self, retry_after: str | None = None, group_key: str | None = None
    ) -> None:
        """Handle 429 Too Many Requests response.

        Args:
            retry_after: Value of Retry-After header if present
            group_key: Rate limit group for context logging and backoff tracking
        """
        group_context = f"group={group_key}" if group_key else "unknown group"

        if retry_after:
            try:
                wait_seconds = int(retry_after)
                logger.warning(
                    "429 Too Many Requests for %s, Retry-After=%ds",
                    group_context,
                    wait_seconds,
                )
                await asyncio.sleep(wait_seconds)
                # Increment backoff to escalate if 429s continue
                if group_key:
                    self._increment_backoff(group_key)
                return
            except ValueError:
                logger.warning(
                    "429 Too Many Requests for %s (invalid Retry-After header)",
                    group_context,
                )

        # Fall back to exponential backoff
        logger.warning(
            "429 Too Many Requests for %s. Using exponential backoff", group_context
        )
        await self._exponential_backoff(group_key or "old_system")

    def reset_backoff(self, group_key: str | None = None) -> None:
        """Reset backoff level after successful request.

        Args:
            group_key: Rate limit group key (None resets old system backoff)
        """
        if group_key is None:
            group_key = "old_system"

        if group_key in self._backoff_levels and self._backoff_levels[group_key] > 0:
            self._backoff_levels[group_key] = max(
                0, self._backoff_levels[group_key] - 1
            )
            logger.debug(
                "Decremented backoff for group=%s to level=%d",
                group_key,
                self._backoff_levels[group_key],
            )

    def get_rate_limit_info(self) -> dict:
        """Get current rate limit status for all tracked groups.

        Returns:
            Dict with rate limit info per group and error limits
        """
        # Copy and present computed rate info where available
        buckets = {}
        for g, info in self.rate_limit_groups.items():
            buckets[g] = info.copy()

        return {
            "token_buckets": buckets,
            "error_limit": {
                "remaining": self.error_remain,
                "reset_at": self.error_reset.isoformat() if self.error_reset else None,
            },
        }

    def _persist(self) -> None:
        """Persist rate limit groups and error reset info to disk atomically.

        Saves all tracked buckets (both public and authenticated):
        - Public buckets: keyed by group name (e.g., "market")
        - Authenticated buckets: keyed by "group:character_id" (e.g., "character:12345")

        Timestamps are serialized to ISO format for persistence.
        Uses atomic write (temp file + rename) to prevent corruption.
        """
        if not self._persist_file:
            return

        # Make a clean copy, converting datetime objects to ISO strings
        clean_groups = {}
        for k, v in self.rate_limit_groups.items():
            copy_v = {}
            for kk, vv in v.items():
                if isinstance(vv, datetime):
                    copy_v[kk] = vv.isoformat()
                else:
                    copy_v[kk] = vv
            clean_groups[k] = copy_v

        payload = {
            "rate_limit_groups": clean_groups,
            "error_remain": self.error_remain,
            "error_reset": self.error_reset.isoformat() if self.error_reset else None,
            "backoff_levels": self._backoff_levels,
        }

        # Atomic write: temp file + rename
        try:
            persist_dir = os.path.dirname(self._persist_file)
            if not persist_dir:
                persist_dir = "."

            os.makedirs(persist_dir, exist_ok=True)

            temp_fd, temp_path = tempfile.mkstemp(
                dir=persist_dir,
                prefix=".rate_limit_",
                suffix=".json.tmp",
                text=True,
            )
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False, indent=2)
                    fh.flush()
                    os.fsync(fh.fileno())

                # Atomic rename
                os.replace(temp_path, self._persist_file)
            except Exception:
                # Clean up temp file on error
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            # Non-fatal - persistence is best-effort
            logger.debug("Failed to persist rate limit data: %s", e)

    def _load(self) -> None:
        """Load persisted rate limit data from disk if available.

        Restores all previously tracked buckets (public and authenticated).
        Deserializes ISO timestamp strings back to datetime objects.
        """
        if not self._persist_file or not os.path.exists(self._persist_file):
            return
        try:
            with open(self._persist_file, encoding="utf-8") as fh:
                payload = json.load(fh)
            groups = payload.get("rate_limit_groups") or {}

            # Deserialize timestamps
            for _, v in groups.items():
                if isinstance(v, dict):
                    last_updated = v.get("last_updated")
                    if last_updated:
                        try:
                            v["last_updated"] = datetime.fromisoformat(last_updated)
                        except Exception:
                            v["last_updated"] = None

            self.rate_limit_groups = groups
            self.error_remain = payload.get("error_remain")
            error_reset = payload.get("error_reset")
            if error_reset:
                try:
                    self.error_reset = datetime.fromisoformat(error_reset)
                except Exception:
                    self.error_reset = None

            self._backoff_levels = payload.get("backoff_levels", {})
            if not isinstance(self._backoff_levels, dict):
                self._backoff_levels = {}

        except Exception:
            return
