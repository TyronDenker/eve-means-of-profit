"""Tests for ESIClient dependency injection pattern.

The ESIClient no longer uses a singleton pattern. Instead, it is created
via dependency injection through the DI container. This test verifies that
the container correctly manages ESIClient instances.
"""

from data.clients import ESIClient
from utils import ServiceKeys, configure_container, get_container, reset_container


def test_esi_client_via_di_container():
    """Test that ESIClient is properly managed via DI container."""
    # Reset container for clean test
    reset_container()

    # Configure the container
    configure_container()
    container = get_container()

    # Resolve ESI client twice
    first = container.resolve(ServiceKeys.ESI_CLIENT)
    second = container.resolve(ServiceKeys.ESI_CLIENT)

    # Container should return the same instance (lazy singleton within container)
    assert first is second
    assert isinstance(first, ESIClient)


def test_multiple_esi_clients_can_coexist():
    """Test that multiple ESIClient instances can be created independently."""
    # Create two independent clients
    client1 = ESIClient(client_id="test_client_1")
    client2 = ESIClient(client_id="test_client_2")

    # They should be different instances
    assert client1 is not client2

    # But both should be ESIClient instances
    assert isinstance(client1, ESIClient)
    assert isinstance(client2, ESIClient)
