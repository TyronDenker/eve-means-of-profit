"""
ESI OAuth2 Authentication and Token Management.

Handles OAuth2 PKCE flow, JWT token decoding, and automatic token refresh.
Tokens are stored securely in a JSON file with automatic expiry handling.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
from authlib.integrations.httpx_client import OAuth2Client


class TokenProvider:
    """
    Manages OAuth2 tokens for ESI API access.

    Stores tokens in a JSON file and handles automatic refresh.
    Supports multiple characters.
    """

    # ESI OAuth2 endpoints
    AUTHORIZATION_URL = "https://login.eveonline.com/v2/oauth/authorize"
    TOKEN_URL = "https://login.eveonline.com/v2/oauth/token"

    def __init__(
        self,
        client_id: str,
        redirect_uri: str = "http://localhost:8080/eve-means-of-profit",
        token_file: str | Path | None = None,
    ):
        """
        Initialize token provider.

        Args:
            client_id: ESI application client ID
            redirect_uri: OAuth2 redirect URI
            token_file: Path to token storage file (default: data/esi/tokens.json)
        """
        self.client_id = client_id
        self.redirect_uri = redirect_uri

        # Set default token file location
        if token_file is None:
            token_file = Path("data/esi/tokens.json")
        self.token_file = Path(token_file)

        # Ensure directory exists
        self.token_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing tokens
        self._tokens: dict[int, dict[str, Any]] = self._load_tokens()

        # Store PKCE code verifier temporarily (in-memory only for security)
        self._code_verifier: str | None = None

    def _generate_pkce_challenge(self) -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate code verifier (32 random bytes, base64url encoded)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(
            "utf-8"
        )

        # Generate code challenge (SHA256 hash of verifier, base64url encoded without padding)
        sha256 = hashlib.sha256()
        sha256.update(code_verifier.encode("utf-8"))
        code_challenge = (
            base64.urlsafe_b64encode(sha256.digest()).decode("utf-8").rstrip("=")
        )

        return code_verifier, code_challenge

    def _load_tokens(self) -> dict[int, dict[str, Any]]:
        """Load tokens from file."""
        if not self.token_file.exists():
            return {}

        try:
            with open(self.token_file, encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys back to integers
                return {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, ValueError):
            return {}

    def _save_tokens(self) -> None:
        """Save tokens to file."""
        # Convert integer keys to strings for JSON
        data = {str(k): v for k, v in self._tokens.items()}

        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def get_authorization_url(self, scopes: list[str] | None = None) -> str:
        """
        Get OAuth2 authorization URL.

        Args:
            scopes: List of ESI scopes to request

        Returns:
            Authorization URL to redirect user to
        """

        # Generate PKCE challenge
        self._code_verifier, code_challenge = self._generate_pkce_challenge()

        # Build authorization URL with PKCE parameters
        client = OAuth2Client(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
        )
        scope = " ".join(scopes) if scopes else ""
        uri, _state = client.create_authorization_url(
            self.AUTHORIZATION_URL,
            scope=scope,
            code_challenge=code_challenge,
            code_challenge_method="S256",
        )

        return uri

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth2 callback

        Returns:
            Token data including character_id, character_name, etc.
        """
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": self.client_id,
                    "code_verifier": self._code_verifier,
                },
            )
            response.raise_for_status()
            token = response.json()

            # Clear the code verifier
            self._code_verifier = None

        # Extract character info from JWT token claims
        # JWT contains: sub="CHARACTER:EVE:<character_id>", name="<character_name>", scp=[scopes]
        character_info = self._decode_token_claims(token["access_token"])

        # Store token
        character_id = character_info["character_id"]
        self._tokens[character_id] = {
            "character_id": character_id,
            "character_name": character_info["character_name"],
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token"),
            "expires_at": time.time() + token.get("expires_in", 1200),
            "scopes": character_info["scopes"],
        }

        self._save_tokens()
        return self._tokens[character_id]

    def _decode_token_claims(self, access_token: str) -> dict[str, Any]:
        """
        Decode JWT token to extract character information.

        The access token is a JWT with claims:
        - sub: "CHARACTER:EVE:<character_id>"
        - name: "<character_name>"
        - scp: ["scope1", "scope2", ...]

        Args:
            access_token: JWT access token

        Returns:
            Dictionary with character_id, character_name, and scopes
        """
        # Decode JWT without verification (we trust ESI)
        # The token is in format: header.payload.signature
        # We only need the payload which is base64-encoded JSON
        try:
            # Split the JWT and get the payload
            _header, payload, _signature = access_token.split(".")

            # Add padding if needed (JWT uses base64url without padding)
            padding = len(payload) % 4
            if padding:
                payload += "=" * (4 - padding)

            # Decode base64
            decoded = base64.urlsafe_b64decode(payload)
            claims = json.loads(decoded)

            # Extract character info from claims
            # sub format: "CHARACTER:EVE:<character_id>"
            sub_parts = claims.get("sub", "").split(":")
            character_id = int(sub_parts[-1]) if len(sub_parts) == 3 else 0

            return {
                "character_id": character_id,
                "character_name": claims.get("name", "Unknown"),
                "scopes": claims.get("scp", []),
            }
        except (ValueError, json.JSONDecodeError, IndexError) as e:
            msg = f"Failed to decode JWT token: {e}"
            raise ValueError(msg) from e

    async def get_token(self, character_id: int) -> str:
        """
        Get valid access token for character.

        Automatically refreshes if expired.

        Args:
            character_id: Character ID to get token for

        Returns:
            Valid access token

        Raises:
            ValueError: If character not authenticated
        """
        if character_id not in self._tokens:
            msg = f"Character {character_id} not authenticated"
            raise ValueError(msg)

        token_data = self._tokens[character_id]

        # Check if token is expired (with 60 second buffer)
        if token_data["expires_at"] < time.time() + 60:
            await self._refresh_token(character_id)

        return self._tokens[character_id]["access_token"]

    async def _refresh_token(self, character_id: int) -> None:
        """
        Refresh access token using refresh token.

        For PKCE flow, refresh doesn't require client secret.

        Args:
            character_id: Character ID to refresh token for
        """
        token_data = self._tokens[character_id]

        if not token_data.get("refresh_token"):
            msg = f"No refresh token for character {character_id}"
            raise ValueError(msg)

        # Refresh token request
        async with httpx.AsyncClient() as http_client:
            response = await http_client.post(
                self.TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token_data["refresh_token"],
                    "client_id": self.client_id,
                },
            )
            response.raise_for_status()
            token = response.json()

        # Update stored token
        self._tokens[character_id].update(
            {
                "access_token": token["access_token"],
                "refresh_token": token.get(
                    "refresh_token", token_data["refresh_token"]
                ),
                "expires_at": time.time() + token.get("expires_in", 1200),
            }
        )

        self._save_tokens()

    def list_characters(self) -> list[dict[str, Any]]:
        """
        List all authenticated characters.

        Returns:
            List of character info dictionaries
        """
        return [
            {
                "character_id": token_data["character_id"],
                "character_name": token_data["character_name"],
                "scopes": token_data.get("scopes", []),
            }
            for token_data in self._tokens.values()
        ]

    def remove_character(self, character_id: int) -> None:
        """
        Remove character authentication.

        Args:
            character_id: Character ID to remove
        """
        if character_id in self._tokens:
            del self._tokens[character_id]
            self._save_tokens()
