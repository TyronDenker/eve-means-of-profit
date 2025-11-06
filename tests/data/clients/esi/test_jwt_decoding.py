"""Test JWT token decoding functionality."""

import base64
import json

from data.clients.esi.auth import TokenManager


def test_decode_token_claims():
    """Test that JWT token claims are properly decoded."""
    # Create a minimal JWT token for testing
    # Format: header.payload.signature (we only care about payload)

    # Create test payload
    payload_data = {
        "sub": "CHARACTER:EVE:123456789",
        "name": "Test Character",
        "scp": ["esi-assets.read_assets.v1", "esi-wallet.read_character_wallet.v1"],
        "exp": 1234567890,
        "iss": "login.eveonline.com",
        "aud": ["EVE Online", "test_client_id"],
    }

    # Encode payload as base64url (without padding)
    payload_json = json.dumps(payload_data)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

    # Create minimal JWT (header and signature don't matter for this test)
    fake_header = base64.urlsafe_b64encode(b'{"typ":"JWT"}').decode().rstrip("=")
    fake_signature = "fake_signature"
    test_token = f"{fake_header}.{payload_b64}.{fake_signature}"

    # Create TokenManager instance
    manager = TokenManager(client_id="test_client_id")

    # Decode the token
    result = manager._decode_token_claims(test_token)

    # Verify the results
    assert result["character_id"] == 123456789
    assert result["character_name"] == "Test Character"
    assert result["scopes"] == [
        "esi-assets.read_assets.v1",
        "esi-wallet.read_character_wallet.v1",
    ]


def test_decode_token_with_padding():
    """Test JWT decoding with various base64 padding scenarios."""
    # Test with payload that needs padding
    payload_data = {"sub": "CHARACTER:EVE:987654321", "name": "X", "scp": []}

    payload_json = json.dumps(payload_data)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip("=")

    fake_header = base64.urlsafe_b64encode(b'{"typ":"JWT"}').decode().rstrip("=")
    fake_signature = "sig"
    test_token = f"{fake_header}.{payload_b64}.{fake_signature}"

    manager = TokenManager(client_id="test")
    result = manager._decode_token_claims(test_token)

    assert result["character_id"] == 987654321
    assert result["character_name"] == "X"
    assert result["scopes"] == []


if __name__ == "__main__":
    # Run tests
    test_decode_token_claims()
    print("✅ test_decode_token_claims passed")

    test_decode_token_with_padding()
    print("✅ test_decode_token_with_padding passed")

    print("\n✅ All JWT decoding tests passed!")
