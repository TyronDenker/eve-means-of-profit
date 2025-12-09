"""OAuth authentication for EVE Online SSO with PKCE support.

Implements OAuth 2.0 Authorization Code flow with PKCE (Proof Key for Code Exchange).
PKCE allows secure authentication without requiring a client secret, making it
suitable for desktop and mobile applications that cannot securely store secrets.
"""

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import tempfile
import webbrowser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode, urlparse

import httpx

from utils import global_config

from .callback_server import CallbackServer

logger = logging.getLogger(__name__)


class ESIAuth:
    """Handles OAuth 2.0 authentication with EVE Online SSO."""

    def __init__(
        self,
        client_id: str | None = None,
        callback_url: str | None = None,
        token_file: str | Path | None = None,
    ):
        """Initialize ESI authentication with PKCE.

        Args:
            client_id: EVE application client ID. Falls back to config/env.
            callback_url: OAuth callback URL (must match app registration). Falls back to config/env.
            token_file: Path to token storage file. Falls back to config/env.

        Note:
            All parameters fall back to configuration values from .env or hardcoded defaults
            if not explicitly provided.
        """
        # Use config values as defaults
        self.client_id = client_id or global_config.esi.client_id
        self.callback_url = callback_url or global_config.esi.callback_url
        # Ensure token_file is always a Path instance
        self.token_file = Path(token_file or global_config.esi.token_file_path)
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        # SSO endpoints from config
        self.auth_url = global_config.esi.auth_url
        self.token_url = global_config.esi.token_url
        self.verify_url = global_config.esi.verify_url

        self._tokens: dict[str, dict] = {}
        # Map state -> code_verifier for PKCE flows (allows concurrent auths)
        self._pkce_by_state: dict[str, str] = {}
        # Per-character locks to prevent concurrent token refreshes
        self._token_locks: dict[str, asyncio.Lock] = {}
        self._load_tokens()

        # Reference to a running CallbackServer (if an interactive auth is active)
        # This is set when authenticate_interactive() starts the server so
        # callers (e.g., UI) can abort the flow if needed.
        self._current_callback_server: CallbackServer | None = None

    def _load_tokens(self) -> None:
        """Load tokens from disk.

        Reads the token file and parses it into the internal tokens dictionary.
        If the file doesn't exist or is invalid, initializes an empty dictionary.
        """
        if not self.token_file.exists():
            self._tokens = {}
            logger.debug("Token file does not exist; starting with empty tokens")
            return

        try:
            with open(self.token_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._tokens = data
                    logger.debug("Loaded %d tokens from file", len(data))
                    return
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load tokens from file: %s", e)

        self._tokens = {}

    def _save_tokens(self) -> None:
        """Save tokens to disk atomically to prevent corruption."""
        # Write to temp file first, then atomic rename
        temp_fd, temp_path = tempfile.mkstemp(
            dir=self.token_file.parent,
            prefix=".tokens_",
            suffix=".json.tmp",
            text=True,
        )
        try:
            with os.fdopen(temp_fd, "w") as f:
                json.dump(self._tokens, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            # Atomic replace (works on Windows and POSIX)
            os.replace(temp_path, self.token_file)

            # Set restrictive permissions on POSIX systems (ignore on Windows)
            try:
                os.chmod(self.token_file, 0o600)
            except (OSError, AttributeError):
                pass  # Not available or not needed on this platform

            logger.debug("Saved %d tokens to file", len(self._tokens))

        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise

    def _is_loopback_host(self, host: str) -> bool:
        """Check if a hostname is loopback-only (safe for OAuth callback server).

        Args:
            host: Hostname or IP address

        Returns:
            True if host is loopback (localhost, 127.0.0.1, ::1, etc.)
        """
        # Check common loopback hostnames
        if host.lower() in ("localhost", "localhost.", "ip6-localhost"):
            return True

        # Check if it's an IP address and verify it's loopback
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_loopback
        except ValueError:
            # Not a valid IP, check if hostname resolves to loopback (optional)
            # For now, be strict and only allow explicit loopback names/IPs
            return False

    def _generate_pkce_challenge(self) -> tuple[str, str]:
        """Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate 32 random bytes and base64url encode (no padding)
        code_verifier_bytes = secrets.token_bytes(32)
        code_verifier = (
            base64.urlsafe_b64encode(code_verifier_bytes).decode("utf-8").rstrip("=")
        )

        # Hash with SHA-256 and base64url encode (no padding)
        sha256_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
        code_challenge = (
            base64.urlsafe_b64encode(sha256_hash).decode("utf-8").rstrip("=")
        )

        return code_verifier, code_challenge

    def get_auth_url(self, scopes: list[str]) -> tuple[str, str]:
        """Generate OAuth authorization URL with PKCE.

        Args:
            scopes: List of ESI scopes to request

        Returns:
            Tuple of (auth_url, state) where state is used for CSRF protection
        """
        state = secrets.token_urlsafe(32)
        params = {
            "response_type": "code",
            "redirect_uri": self.callback_url,
            "client_id": self.client_id,
            "scope": " ".join(scopes),
            "state": state,
        }

        # Generate and store PKCE challenge
        code_verifier, code_challenge = self._generate_pkce_challenge()

        # Store verifier keyed by state for later retrieval
        self._pkce_by_state[state] = code_verifier
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

        auth_url = f"{self.auth_url}?{urlencode(params)}"
        return auth_url, state

    async def authenticate_interactive(self, scopes: list[str] | None = None) -> dict:
        """Interactive OAuth flow (opens browser with callback server).

        Args:
            scopes: List of ESI scopes (defaults to assets read)

        Returns:
            Character info dict with access token

        Raises:
            ValueError: If callback_url host is not loopback (security risk)
        """
        if scopes is None:
            scopes = global_config.esi.default_scopes.copy()

        auth_url, expected_state = self.get_auth_url(scopes)

        logger.info("Starting local callback server for OAuth authentication")

        # Parse callback URL to get host and port
        parsed = urlparse(self.callback_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8080

        # SECURITY: Validate that callback host is loopback-only to prevent
        # exposing the OAuth callback server to network attacks
        if not self._is_loopback_host(host):
            raise ValueError(
                f"Callback URL host '{host}' is not loopback. "
                f"For security, only localhost/127.0.0.1/::1 are allowed. "
                f"Exposing OAuth callback server to network is a security risk."
            )

        # Create and start the callback server so we can stop it from the main
        # thread if necessary. Starting is quick because it launches its own
        # background thread; waiting for the callback is done via
        # `wait_for_callback` which we call in a thread to avoid blocking the
        # asyncio event loop.
        server = CallbackServer(host, port)

        # Expose the running server so callers may cancel the flow by calling
        # `abort_current_auth()` (useful for UI-driven cancellation).
        self._current_callback_server = server
        try:
            server.start()
            logger.info(
                "Opening browser for authentication (if browser doesn't open, visit: %s)",
                auth_url,
            )
            try:
                webbrowser.open(auth_url)
            except Exception:
                logger.debug(
                    "Failed to open browser automatically; manual visit may be required"
                )

            # Wait for callback in thread (non-blocking to event loop)
            try:
                callback_data = await asyncio.to_thread(server.wait_for_callback, 300)
            except Exception as e:
                logger.exception("Error while waiting for OAuth callback: %s", e)
                raise

            if not callback_data:
                raise TimeoutError(
                    "OAuth callback timeout - no response received after 5 minutes"
                )

            if callback_data.get("error"):
                raise ValueError(f"OAuth error: {callback_data['error']}")

            # Validate state to prevent CSRF attacks
            received_state = callback_data.get("state")
            if received_state != expected_state:
                raise ValueError(
                    f"State mismatch: expected {expected_state}, got {received_state}. "
                    "Possible CSRF attack detected."
                )

            code = callback_data.get("code")
            if not code:
                raise ValueError("No authorization code received in callback")

            logger.info("Received authorization code, exchanging for token")

            # Exchange code for token, passing the state to retrieve the correct verifier
            return await self.exchange_code(code, state=expected_state)
        finally:
            try:
                server.stop()
            except Exception:
                logger.debug("Callback server stop raised an exception")
            finally:
                # Clear exposed server reference
                self._current_callback_server = None

    def abort_current_auth(self) -> bool:
        """Abort any currently-running interactive authentication.

        Returns True if a server was running and was stopped, False otherwise.
        """
        if self._current_callback_server:
            try:
                self._current_callback_server.stop()
                logger.info("Aborted current interactive authentication")
                return True
            except Exception:
                logger.exception("Failed to abort current interactive authentication")
                return False
        return False

    async def exchange_code(self, code: str, state: str | None = None) -> dict:
        """Exchange authorization code for access token (PKCE).

        Args:
            code: Authorization code from OAuth callback
            state: OAuth state value (used to retrieve the correct code_verifier)

        Returns:
            Character info dict with tokens
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Prepare token exchange payload
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": self.client_id,
            }

            # Retrieve and remove the code_verifier for this state
            if state and state in self._pkce_by_state:
                code_verifier = self._pkce_by_state.pop(state)
            else:
                raise ValueError(
                    f"PKCE code verifier not found for state {state}. "
                    "get_auth_url() must be called first."
                )
            token_data["code_verifier"] = code_verifier

            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            response = await client.post(
                self.token_url,
                data=token_data,
                headers=headers,
            )
            response.raise_for_status()
            token_response = response.json()

            # Validate required fields in response
            access_token = token_response.get("access_token")
            if not access_token:
                raise ValueError(
                    f"Token exchange failed: missing access_token in response: {token_response}"
                )
            refresh_token = token_response.get("refresh_token")
            expires_in = token_response.get("expires_in", 1200)

            # Verify token and get character info
            verify_response = await client.get(
                self.verify_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            verify_response.raise_for_status()
            character_info = verify_response.json()

            # Validate required fields
            character_id = character_info.get("CharacterID")
            character_name = character_info.get("CharacterName")
            if not character_id or not character_name:
                raise ValueError(
                    f"Token verification failed: missing character info: {character_info}"
                )

            expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()

            self._tokens[str(character_id)] = {
                "character_id": character_id,
                "character_name": character_name,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "scopes": character_info.get("Scopes", "").split(),
            }

            self._save_tokens()

            logger.info(
                "Successfully authenticated as %s (id=%s), token expires: %s",
                character_name,
                character_id,
                expires_at,
            )

            return self._tokens[str(character_id)]

    async def get_token(self, character_id: int | str) -> str:
        """Get a valid access token for character, refreshing if needed.

        Uses per-character locking to prevent concurrent refresh attempts.

        Args:
            character_id: Character ID

        Returns:
            Valid access token

        Raises:
            ValueError: If no token found for character
        """
        character_id = str(character_id)

        if character_id not in self._tokens:
            raise ValueError(
                f"No token found for character {character_id}. "
                "Run authenticate_interactive() first."
            )

        # Use per-character lock to prevent concurrent refreshes
        lock = self._token_locks.setdefault(character_id, asyncio.Lock())
        async with lock:
            token_info = self._tokens[character_id]

            # Parse stored expires_at (ISO 8601 format)
            expires_raw = token_info.get("expires_at")
            expires_at: datetime
            try:
                expires_at = datetime.fromisoformat(str(expires_raw))
                # Ensure timezone-aware in UTC
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=UTC)
            except Exception:
                # If parsing fails, force refresh to be safe
                return await self._refresh_token(character_id)

            # Token is still valid (with 5min buffer)
            if datetime.now(UTC) < expires_at - timedelta(minutes=5):
                return token_info["access_token"]

            # Token expired, refresh it
            logger.debug("Refreshing token for character %s", character_id)
            return await self._refresh_token(character_id)

    async def refresh_token(self, character_id: int | str) -> str:
        """Public wrapper to force a token refresh for a character.

        Delegates to the internal _refresh_token implementation but provides
        a public, documented API so callers don't access a private method.
        """
        return await self._refresh_token(str(character_id))

    async def _refresh_token(self, character_id: str) -> str:
        """Refresh an expired access token (PKCE compatible).

        Args:
            character_id: Character ID

        Returns:
            New access token
        """
        token_info = self._tokens[character_id]
        refresh_token = token_info.get("refresh_token")

        if not refresh_token:
            raise ValueError(
                f"No refresh token for character {character_id}. "
                "Re-authentication required."
            )

        async with httpx.AsyncClient(timeout=30.0) as client:
            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
            }

            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            try:
                response = await client.post(
                    self.token_url,
                    data=token_data,
                    headers=headers,
                )
                response.raise_for_status()
                token_response = response.json()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "Token refresh failed for character %s: %s %s",
                    character_id,
                    e.response.status_code,
                    e.response.text[:200] if e.response.text else "",
                )
                raise

            # Update stored token
            access_token = token_response["access_token"]
            refresh_token = token_response.get("refresh_token", refresh_token)
            expires_in = token_response.get("expires_in", 1200)

            expires_at = (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat()

            token_info["access_token"] = access_token
            token_info["refresh_token"] = refresh_token
            token_info["expires_at"] = expires_at

            self._save_tokens()

            logger.info("Token refreshed for %s", token_info["character_name"])

            return access_token

    def list_authenticated_characters(self) -> list[dict]:
        """Get list of authenticated characters.

        Returns:
            List of character info dicts
        """
        return [
            {
                "character_id": info["character_id"],
                "character_name": info["character_name"],
                "scopes": info["scopes"],
            }
            for info in self._tokens.values()
        ]

    def remove_token(self, character_id: int | str) -> bool:
        """Remove stored token for a character.

        Args:
            character_id: Character ID to remove

        Returns:
            True if token was removed, False if not found
        """
        character_id = str(character_id)
        if character_id in self._tokens:
            del self._tokens[character_id]
            self._save_tokens()
            logger.info("Removed token for character %s", character_id)
            return True
        return False
