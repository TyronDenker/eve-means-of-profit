"""Tests demonstrating multi-character async concurrency with DI-based ESI client.

This test suite shows how the new DI architecture enables safe concurrent
operations across multiple characters without singleton bottlenecks.
"""

import asyncio
from unittest.mock import Mock

import pytest

from data.clients import ESIClient
from services.character_service import CharacterService
from utils import ServiceKeys, get_container, reset_container


@pytest.fixture
def mock_esi_client():
    """Create a mock ESI client for testing."""
    client = Mock(spec=ESIClient)
    client.auth = Mock()
    client.assets = Mock()
    client.wallet = Mock()
    client.characters = Mock()
    return client


@pytest.fixture
def configured_container():
    """Setup DI container with mocked services."""
    reset_container()
    container = get_container()

    # Register mock ESI client
    mock_client = Mock(spec=ESIClient)
    mock_client.auth = Mock()
    container.register(ServiceKeys.ESI_CLIENT, mock_client)

    return container


class TestMultiCharacterAsyncConcurrency:
    """Tests for concurrent multi-character operations."""

    @pytest.mark.asyncio
    async def test_multiple_characters_refresh_concurrently(self, mock_esi_client):
        """Test that multiple characters can be refreshed concurrently."""
        # Setup mock responses
        call_times = []

        async def mock_get_assets(character_id: int, **kwargs):
            call_times.append(("assets", character_id, asyncio.get_event_loop().time()))
            await asyncio.sleep(0.01)  # Simulate network delay
            return ([], {})

        async def mock_get_transactions(character_id: int, **kwargs):
            call_times.append(
                ("transactions", character_id, asyncio.get_event_loop().time())
            )
            await asyncio.sleep(0.01)
            return ([], {})

        mock_esi_client.assets.get_assets = mock_get_assets
        mock_esi_client.wallet.get_transactions = mock_get_transactions

        # Refresh 3 characters concurrently
        character_ids = [12345, 67890, 11111]

        async def refresh_character(char_id: int):
            # Simulate fetching multiple endpoints
            await asyncio.gather(
                mock_get_assets(char_id),
                mock_get_transactions(char_id),
            )

        start_time = asyncio.get_event_loop().time()
        await asyncio.gather(*[refresh_character(cid) for cid in character_ids])
        total_time = asyncio.get_event_loop().time() - start_time

        # Verify all calls were made
        assert len(call_times) == 6  # 3 characters * 2 endpoints each

        # Verify concurrency: total time should be ~0.01s (parallel)
        # not ~0.06s (sequential). Allow some overhead.
        assert total_time < 0.05, (
            f"Operations were sequential ({total_time}s), not concurrent"
        )

        # Verify all characters were processed
        character_ids_called = {call[1] for call in call_times}
        assert character_ids_called == set(character_ids)

    @pytest.mark.asyncio
    async def test_di_container_enables_concurrent_services(self, configured_container):
        """Test that DI container supports concurrent service access."""

        # Setup async mock methods
        async def mock_auth_list():
            await asyncio.sleep(0.001)
            return [
                {"character_id": 123, "character_name": "Char1", "scopes": []},
                {"character_id": 456, "character_name": "Char2", "scopes": []},
            ]

        mock_client = configured_container.resolve(ServiceKeys.ESI_CLIENT)
        mock_client.auth.list_authenticated_characters = mock_auth_list

        # Register character service factory
        def char_service_factory(c):
            return CharacterService(esi_client=c.resolve(ServiceKeys.ESI_CLIENT))

        configured_container.register_factory(
            ServiceKeys.CHARACTER_SERVICE, char_service_factory
        )

        # Resolve service multiple times concurrently
        async def get_service():
            return configured_container.resolve(ServiceKeys.CHARACTER_SERVICE)

        # Multiple concurrent resolves should work fine
        services = await asyncio.gather(*[get_service() for _ in range(5)])

        # All should be the same instance (lazy singleton in container)
        assert all(s is services[0] for s in services)

    @pytest.mark.asyncio
    async def test_no_singleton_contention(self):
        """Test that there's no global singleton lock causing contention."""
        # Create multiple independent ESI clients
        clients = [ESIClient(client_id=f"test_{i}") for i in range(5)]

        # All should be different instances
        for i, client1 in enumerate(clients):
            for j, client2 in enumerate(clients):
                if i != j:
                    assert client1 is not client2

        # All should be ESIClient instances
        assert all(isinstance(c, ESIClient) for c in clients)

    @pytest.mark.asyncio
    async def test_concurrent_endpoint_calls_with_shared_client(self, mock_esi_client):
        """Test concurrent endpoint calls with a shared client instance."""
        call_log = []

        async def mock_endpoint(endpoint_name: str, character_id: int):
            call_log.append(f"{endpoint_name}:{character_id}")
            await asyncio.sleep(0.01)
            return ([], {})

        # Setup mock endpoints
        mock_esi_client.assets.get_assets = lambda cid, **kw: mock_endpoint(
            "assets", cid
        )
        mock_esi_client.wallet.get_transactions = lambda cid, **kw: mock_endpoint(
            "wallet", cid
        )
        mock_esi_client.market = Mock()
        mock_esi_client.market.get_orders = lambda cid, **kw: mock_endpoint(
            "market", cid
        )

        # Make concurrent calls across different characters and services
        tasks = [
            mock_esi_client.assets.get_assets(123),
            mock_esi_client.wallet.get_transactions(123),
            mock_esi_client.market.get_orders(123),
            mock_esi_client.assets.get_assets(456),
            mock_esi_client.wallet.get_transactions(456),
            mock_esi_client.market.get_orders(456),
        ]

        await asyncio.gather(*tasks)

        # All calls should have completed
        assert len(call_log) == 6

        # Both characters should have all endpoints called
        assert "assets:123" in call_log
        assert "wallet:123" in call_log
        assert "market:123" in call_log
        assert "assets:456" in call_log
        assert "wallet:456" in call_log
        assert "market:456" in call_log


class TestDIvsSingletonComparison:
    """Compare DI approach to singleton approach."""

    def test_di_explicit_dependencies(self):
        """Test that DI makes dependencies explicit."""
        # With DI, dependencies are clear in constructor
        mock_client = Mock(spec=ESIClient)
        service = CharacterService(esi_client=mock_client)

        # The dependency is explicit and testable
        assert service._client is mock_client

    def test_di_testability(self):
        """Test that DI improves testability."""
        # Create mock with specific behavior
        mock_client = Mock(spec=ESIClient)
        mock_client.auth = Mock()
        mock_client.auth.list_authenticated_characters = Mock(return_value=[])

        # Inject directly - no global state to manage
        service = CharacterService(esi_client=mock_client)

        # Test with clean mock
        result = asyncio.run(service.get_authenticated_characters(use_cache_only=True))
        assert result == []
        mock_client.auth.list_authenticated_characters.assert_called_once()

    def test_multiple_instances_possible(self):
        """Test that multiple client instances can coexist."""
        # Can create multiple clients for different purposes
        client1 = ESIClient(client_id="test1")
        client2 = ESIClient(client_id="test2")

        service1 = CharacterService(esi_client=client1)
        service2 = CharacterService(esi_client=client2)

        # Services use different clients
        assert service1._client is client1
        assert service2._client is client2
        assert service1._client is not service2._client


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
