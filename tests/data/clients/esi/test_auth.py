"""
Comprehensive tests for TokenProvider OAuth2 authentication.

Tests cover token lifecycle, OAuth2 PKCE flow, JWT decoding, token refresh,
and multi-character management.
"""

import base64
import json
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from data.clients.esi.auth import TokenProvider

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_token_file():
    """Provide temporary token file path."""
    with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        yield Path(tmpdir) / "tokens.json"


@pytest.fixture
def provider_params(temp_token_file):
    """Standard TokenProvider initialization parameters."""
    return {
        "client_id": "test_client_id",
        "token_file": temp_token_file,
        "redirect_uri": "http://localhost:8080/callback",
    }


@pytest.fixture
def sample_jwt_token():
    """Sample JWT token with valid structure."""
    # JWT format: header.payload.signature
    # Payload contains: {"sub": "CHARACTER:EVE:123456789", "name": "Test Character", "scp": ["esi-scope.1"]}
    payload = {
        "sub": "CHARACTER:EVE:123456789",
        "name": "Test Character",
        "scp": [
            "esi-assets.read_assets.v1",
            "esi-characters.read_corporation_roles.v1",
        ],
    }

    # Encode payload
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

    # Create fake JWT (header and signature are not validated)
    return f"header.{payload_b64}.signature"


@pytest.fixture
def sample_token_response(sample_jwt_token):
    """Sample OAuth2 token response."""
    return {
        "access_token": sample_jwt_token,
        "refresh_token": "refresh_token_123",
        "expires_in": 1200,
        "token_type": "Bearer",
    }


# ============================================================================
# Test Class: Initialization and PKCE
# ============================================================================


class TestTokenProviderInitialization:
    """Tests for TokenProvider initialization and PKCE generation."""

    def test_initialization_creates_token_file_directory(self, temp_token_file):
        """
        Given: Token file path in non-existent subdirectory
        When: TokenProvider is initialized
        Then: Parent directories are created
        """
        # Given - use nested directory that doesn't exist yet
        nested_token_file = temp_token_file.parent / "subdir" / "tokens.json"
        assert not nested_token_file.parent.exists()

        # When
        TokenProvider(
            client_id="test_client",
            token_file=nested_token_file,
            redirect_uri="http://localhost:8080/callback",
        )

        # Then
        assert nested_token_file.parent.exists()

    def test_initialization_loads_empty_tokens_if_no_file(self, provider_params):
        """
        Given: No existing token file
        When: TokenProvider is initialized
        Then: Empty tokens dictionary is created
        """
        # Given/When
        provider = TokenProvider(**provider_params)

        # Then
        assert provider._tokens == {}

    def test_initialization_loads_existing_tokens(self, provider_params):
        """
        Given: Existing token file with saved tokens
        When: TokenProvider is initialized
        Then: Tokens are loaded from file
        """
        # Given - create token file
        token_file = provider_params["token_file"]
        token_file.parent.mkdir(parents=True, exist_ok=True)

        tokens = {
            "123456789": {
                "character_id": 123456789,
                "character_name": "Saved Character",
                "access_token": "saved_token",
                "refresh_token": "saved_refresh",
                "expires_at": time.time() + 3600,
                "scopes": ["scope1"],
            }
        }

        with open(token_file, "w") as f:
            json.dump(tokens, f)

        # When
        provider = TokenProvider(**provider_params)

        # Then
        assert 123456789 in provider._tokens
        assert provider._tokens[123456789]["character_name"] == "Saved Character"

    def test_initialization_handles_corrupted_token_file(self, provider_params):
        """
        Given: Corrupted token file with invalid JSON
        When: TokenProvider is initialized
        Then: Empty tokens dictionary is created without error
        """
        # Given
        token_file = provider_params["token_file"]
        token_file.parent.mkdir(parents=True, exist_ok=True)

        with open(token_file, "w") as f:
            f.write("invalid json {{{")

        # When
        provider = TokenProvider(**provider_params)

        # Then
        assert provider._tokens == {}

    def test_pkce_challenge_generation_returns_valid_values(self, provider_params):
        """
        Given: TokenProvider is initialized
        When: PKCE challenge is generated
        Then: Code verifier and challenge are valid base64url strings
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When
        verifier, challenge = provider._generate_pkce_challenge()

        # Then
        assert len(verifier) > 0
        assert len(challenge) > 0
        # Base64url characters (including padding =)
        valid_chars = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="
        )
        assert all(c in valid_chars for c in verifier)
        assert all(c in valid_chars for c in challenge)


# ============================================================================
# Test Class: Authorization URL Generation
# ============================================================================


class TestAuthorizationURL:
    """Tests for OAuth2 authorization URL generation."""

    def test_get_authorization_url_returns_valid_url(self, provider_params):
        """
        Given: List of ESI scopes
        When: get_authorization_url is called
        Then: Valid authorization URL with PKCE parameters is returned
        """
        # Given
        provider = TokenProvider(**provider_params)
        scopes = ["esi-assets.read_assets.v1", "esi-markets.read_corporation_orders.v1"]

        # When
        url = provider.get_authorization_url(scopes)

        # Then
        assert url.startswith("https://login.eveonline.com/v2/oauth/authorize")
        assert "client_id=test_client_id" in url
        assert "redirect_uri=" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "scope=" in url

    def test_get_authorization_url_stores_code_verifier(self, provider_params):
        """
        Given: Authorization URL is generated
        When: Method completes
        Then: Code verifier is stored for later exchange
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When
        provider.get_authorization_url(["scope1"])

        # Then
        assert provider._code_verifier is not None
        assert len(provider._code_verifier) > 0

    def test_get_authorization_url_with_no_scopes(self, provider_params):
        """
        Given: No scopes provided
        When: get_authorization_url is called
        Then: URL is generated with empty scope
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When
        url = provider.get_authorization_url(None)

        # Then
        assert "https://login.eveonline.com/v2/oauth/authorize" in url
        assert "client_id=test_client_id" in url


# ============================================================================
# Test Class: Token Exchange
# ============================================================================


class TestTokenExchange:
    """Tests for authorization code to token exchange."""

    async def test_exchange_code_for_token_makes_correct_request(
        self, provider_params, sample_token_response
    ):
        """
        Given: Authorization code and stored code verifier
        When: exchange_code_for_token is called
        Then: Correct token request is made to ESI
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._code_verifier = "test_verifier_123"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider.exchange_code_for_token("auth_code_123")

            # Then
            assert mock_client.post.called
            call_args = mock_client.post.call_args
            assert call_args.args[0] == TokenProvider.TOKEN_URL

            data = call_args.kwargs["data"]
            assert data["grant_type"] == "authorization_code"
            assert data["code"] == "auth_code_123"
            assert data["client_id"] == "test_client_id"
            assert data["code_verifier"] == "test_verifier_123"

    async def test_exchange_code_for_token_stores_token(
        self, provider_params, sample_token_response
    ):
        """
        Given: Successful token exchange
        When: Response is received
        Then: Token is stored with character information
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._code_verifier = "test_verifier"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            result = await provider.exchange_code_for_token("auth_code")

            # Then
            assert 123456789 in provider._tokens
            assert result["character_id"] == 123456789
            assert result["character_name"] == "Test Character"
            assert result["access_token"] == sample_token_response["access_token"]
            assert "expires_at" in result

    async def test_exchange_code_for_token_saves_to_file(
        self, provider_params, sample_token_response
    ):
        """
        Given: Token is exchanged successfully
        When: Method completes
        Then: Token is persisted to disk
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._code_verifier = "test_verifier"
        token_file = provider_params["token_file"]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider.exchange_code_for_token("auth_code")

            # Then
            assert token_file.exists()

            with open(token_file) as f:
                saved_data = json.load(f)

            assert "123456789" in saved_data

    async def test_exchange_code_for_token_clears_verifier(
        self, provider_params, sample_token_response
    ):
        """
        Given: Token exchange completes
        When: Method returns
        Then: Code verifier is cleared from memory for security
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._code_verifier = "test_verifier"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider.exchange_code_for_token("auth_code")

            # Then
            assert provider._code_verifier is None

    async def test_exchange_code_for_token_handles_http_error(self, provider_params):
        """
        Given: Token endpoint returns error
        When: exchange_code_for_token is called
        Then: HTTPStatusError is raised
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._code_verifier = "test_verifier"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Bad Request", request=MagicMock(), response=mock_response
            )
            mock_client.post.return_value = mock_response

            # When/Then
            with pytest.raises(httpx.HTTPStatusError):
                await provider.exchange_code_for_token("invalid_code")


# ============================================================================
# Test Class: JWT Token Decoding
# ============================================================================


class TestJWTDecoding:
    """Tests for JWT token decoding and claims extraction."""

    def test_decode_token_claims_extracts_character_info(
        self, provider_params, sample_jwt_token
    ):
        """
        Given: Valid JWT token
        When: _decode_token_claims is called
        Then: Character ID, name, and scopes are extracted
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When
        claims = provider._decode_token_claims(sample_jwt_token)

        # Then
        assert claims["character_id"] == 123456789
        assert claims["character_name"] == "Test Character"
        assert "esi-assets.read_assets.v1" in claims["scopes"]

    def test_decode_token_claims_handles_malformed_jwt(self, provider_params):
        """
        Given: Malformed JWT token
        When: _decode_token_claims is called
        Then: ValueError is raised
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When/Then
        with pytest.raises(ValueError, match="Failed to decode JWT token"):
            provider._decode_token_claims("invalid.token")

    def test_decode_token_claims_handles_invalid_sub_format(self, provider_params):
        """
        Given: JWT with invalid subject format
        When: _decode_token_claims is called
        Then: Character ID defaults to 0
        """
        # Given
        provider = TokenProvider(**provider_params)

        payload = {"sub": "INVALID_FORMAT", "name": "Test", "scp": []}
        payload_json = json.dumps(payload)
        payload_b64 = (
            base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")
        )
        invalid_token = f"header.{payload_b64}.signature"

        # When
        claims = provider._decode_token_claims(invalid_token)

        # Then
        assert claims["character_id"] == 0


# ============================================================================
# Test Class: Token Retrieval and Refresh
# ============================================================================


class TestTokenRetrieval:
    """Tests for token retrieval and automatic refresh."""

    async def test_get_token_returns_valid_token(
        self, provider_params, sample_jwt_token
    ):
        """
        Given: Character has valid non-expired token
        When: get_token is called
        Then: Access token is returned
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": sample_jwt_token,
            "refresh_token": "refresh_123",
            "expires_at": time.time() + 3600,  # 1 hour from now
        }

        # When
        token = await provider.get_token(123456789)

        # Then
        assert token == sample_jwt_token

    async def test_get_token_raises_error_for_unauthenticated_character(
        self, provider_params
    ):
        """
        Given: Character has not been authenticated
        When: get_token is called
        Then: ValueError is raised
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When/Then
        with pytest.raises(ValueError, match="not authenticated"):
            await provider.get_token(999999999)

    async def test_get_token_refreshes_expired_token(
        self, provider_params, sample_jwt_token, sample_token_response
    ):
        """
        Given: Character token is expired
        When: get_token is called
        Then: Token is automatically refreshed
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": "old_token",
            "refresh_token": "refresh_123",
            "expires_at": time.time() - 100,  # Expired 100 seconds ago
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            token = await provider.get_token(123456789)

            # Then
            assert mock_client.post.called
            assert token == sample_jwt_token

    async def test_get_token_refreshes_near_expiry_token(
        self, provider_params, sample_jwt_token, sample_token_response
    ):
        """
        Given: Token expires in less than 60 seconds
        When: get_token is called
        Then: Token is proactively refreshed
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": "old_token",
            "refresh_token": "refresh_123",
            "expires_at": time.time() + 30,  # Expires in 30 seconds
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider.get_token(123456789)

            # Then
            assert mock_client.post.called


# ============================================================================
# Test Class: Token Refresh
# ============================================================================


class TestTokenRefresh:
    """Tests for token refresh mechanism."""

    async def test_refresh_token_makes_correct_request(
        self, provider_params, sample_token_response
    ):
        """
        Given: Character has refresh token
        When: _refresh_token is called
        Then: Correct refresh request is made
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": "old_token",
            "refresh_token": "refresh_123",
            "expires_at": time.time() - 100,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider._refresh_token(123456789)

            # Then
            call_args = mock_client.post.call_args
            data = call_args.kwargs["data"]
            assert data["grant_type"] == "refresh_token"
            assert data["refresh_token"] == "refresh_123"
            assert data["client_id"] == "test_client_id"

    async def test_refresh_token_updates_stored_token(
        self, provider_params, sample_token_response
    ):
        """
        Given: Refresh request succeeds
        When: Response is received
        Then: Stored token is updated with new values
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": "old_token",
            "refresh_token": "old_refresh",
            "expires_at": time.time() - 100,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider._refresh_token(123456789)

            # Then
            token_data = provider._tokens[123456789]
            assert token_data["access_token"] == sample_token_response["access_token"]
            assert token_data["expires_at"] > time.time()

    async def test_refresh_token_saves_to_file(
        self, provider_params, sample_token_response
    ):
        """
        Given: Token is refreshed
        When: Method completes
        Then: Updated token is saved to disk
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": "old_token",
            "refresh_token": "old_refresh",
            "expires_at": time.time() - 100,
        }
        token_file = provider_params["token_file"]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            mock_response = MagicMock()
            mock_response.json.return_value = sample_token_response
            mock_client.post.return_value = mock_response

            # When
            await provider._refresh_token(123456789)

            # Then
            assert token_file.exists()

            with open(token_file) as f:
                saved = json.load(f)

            assert (
                saved["123456789"]["access_token"]
                == sample_token_response["access_token"]
            )

    async def test_refresh_token_raises_error_if_no_refresh_token(
        self, provider_params
    ):
        """
        Given: Character token has no refresh_token
        When: _refresh_token is called
        Then: ValueError is raised
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "access_token": "token",
            "expires_at": time.time() - 100,
        }

        # When/Then
        with pytest.raises(ValueError, match="No refresh token"):
            await provider._refresh_token(123456789)


# ============================================================================
# Test Class: Multi-Character Management
# ============================================================================


class TestMultiCharacterManagement:
    """Tests for managing multiple character tokens."""

    def test_list_characters_returns_all_authenticated(self, provider_params):
        """
        Given: Multiple characters are authenticated
        When: list_characters is called
        Then: All characters with their info are returned
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens = {
            111111111: {
                "character_id": 111111111,
                "character_name": "Character One",
                "access_token": "token1",
                "refresh_token": "refresh1",
                "expires_at": time.time() + 3600,
                "scopes": ["scope1", "scope2"],
            },
            222222222: {
                "character_id": 222222222,
                "character_name": "Character Two",
                "access_token": "token2",
                "refresh_token": "refresh2",
                "expires_at": time.time() + 3600,
                "scopes": ["scope3"],
            },
        }

        # When
        characters = provider.list_characters()

        # Then
        assert len(characters) == 2
        assert any(c["character_id"] == 111111111 for c in characters)
        assert any(c["character_id"] == 222222222 for c in characters)

        char_one = next(c for c in characters if c["character_id"] == 111111111)
        assert char_one["character_name"] == "Character One"
        assert char_one["scopes"] == ["scope1", "scope2"]

    def test_list_characters_returns_empty_if_none(self, provider_params):
        """
        Given: No characters are authenticated
        When: list_characters is called
        Then: Empty list is returned
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When
        characters = provider.list_characters()

        # Then
        assert characters == []

    def test_remove_character_deletes_token(self, provider_params):
        """
        Given: Character is authenticated
        When: remove_character is called
        Then: Token is removed from memory
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "character_name": "Test",
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_at": time.time() + 3600,
        }

        # When
        provider.remove_character(123456789)

        # Then
        assert 123456789 not in provider._tokens

    def test_remove_character_saves_to_file(self, provider_params):
        """
        Given: Character is removed
        When: Method completes
        Then: Token file is updated without the character
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "character_name": "Test",
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_at": time.time() + 3600,
        }
        provider._save_tokens()
        token_file = provider_params["token_file"]

        # When
        provider.remove_character(123456789)

        # Then
        with open(token_file) as f:
            saved = json.load(f)

        assert "123456789" not in saved

    def test_remove_character_handles_nonexistent_character(self, provider_params):
        """
        Given: Character does not exist
        When: remove_character is called
        Then: No error occurs
        """
        # Given
        provider = TokenProvider(**provider_params)

        # When/Then - should not raise
        provider.remove_character(999999999)


# ============================================================================
# Test Class: Token Persistence
# ============================================================================


class TestTokenPersistence:
    """Tests for token file I/O operations."""

    def test_save_tokens_writes_to_disk(self, provider_params):
        """
        Given: Tokens are in memory
        When: _save_tokens is called
        Then: Tokens are written to file in JSON format
        """
        # Given
        provider = TokenProvider(**provider_params)
        provider._tokens[123456789] = {
            "character_id": 123456789,
            "character_name": "Test Character",
            "access_token": "test_token",
            "refresh_token": "test_refresh",
            "expires_at": 1234567890.0,
            "scopes": ["scope1"],
        }
        token_file = provider_params["token_file"]

        # When
        provider._save_tokens()

        # Then
        assert token_file.exists()

        with open(token_file) as f:
            data = json.load(f)

        assert "123456789" in data
        assert data["123456789"]["character_name"] == "Test Character"

    def test_load_tokens_reads_from_disk(self, provider_params):
        """
        Given: Token file exists with data
        When: _load_tokens is called
        Then: Tokens are loaded into memory with integer keys
        """
        # Given
        token_file = provider_params["token_file"]
        token_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "123456789": {
                "character_id": 123456789,
                "character_name": "Saved Character",
                "access_token": "saved_token",
                "refresh_token": "saved_refresh",
                "expires_at": 1234567890.0,
            }
        }

        with open(token_file, "w") as f:
            json.dump(data, f)

        provider = TokenProvider(**provider_params)

        # When
        tokens = provider._load_tokens()

        # Then
        assert 123456789 in tokens
        assert isinstance(next(iter(tokens.keys())), int)
        assert tokens[123456789]["character_name"] == "Saved Character"

    def test_token_persistence_survives_reinitialization(self, provider_params):
        """
        Given: Tokens are saved to disk
        When: Provider is recreated
        Then: Tokens are automatically loaded
        """
        # Given
        provider1 = TokenProvider(**provider_params)
        provider1._tokens[123456789] = {
            "character_id": 123456789,
            "character_name": "Persistent Character",
            "access_token": "token",
            "refresh_token": "refresh",
            "expires_at": time.time() + 3600,
        }
        provider1._save_tokens()

        # When
        provider2 = TokenProvider(**provider_params)

        # Then
        assert 123456789 in provider2._tokens
        assert provider2._tokens[123456789]["character_name"] == "Persistent Character"
