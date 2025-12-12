"""Tests for the DI container implementation."""

import pytest

from utils.di_container import (
    DIContainer,
    DIContainerError,
    ServiceKeys,
    get_container,
    reset_container,
)


class TestDIContainer:
    """Tests for DIContainer class."""

    def setup_method(self):
        """Reset container before each test."""
        reset_container()

    def test_register_and_resolve(self):
        """Test basic service registration and resolution."""
        container = DIContainer()
        service = object()
        container.register("test_service", service)

        resolved = container.resolve("test_service")

        assert resolved is service

    def test_register_factory(self):
        """Test factory registration and lazy instantiation."""
        container = DIContainer()
        call_count = 0

        def factory(c):
            nonlocal call_count
            call_count += 1
            return object()

        container.register_factory("lazy_service", factory)

        # Factory not called yet
        assert call_count == 0

        # First resolution calls factory
        first = container.resolve("lazy_service")
        assert call_count == 1

        # Second resolution returns cached instance
        second = container.resolve("lazy_service")
        assert call_count == 1
        assert first is second

    def test_resolve_not_registered_raises(self):
        """Test that resolving unregistered service raises error."""
        container = DIContainer()

        with pytest.raises(DIContainerError) as exc_info:
            container.resolve("nonexistent")

        assert "nonexistent" in str(exc_info.value)

    def test_resolve_optional_returns_none(self):
        """Test that resolve_optional returns None for unregistered service."""
        container = DIContainer()

        result = container.resolve_optional("nonexistent")

        assert result is None

    def test_is_registered(self):
        """Test is_registered checks both instances and factories."""
        container = DIContainer()

        assert not container.is_registered("test")

        container.register("test", object())
        assert container.is_registered("test")

        container.register_factory("factory_test", lambda c: object())
        assert container.is_registered("factory_test")

    def test_create_with_key_mappings(self):
        """Test creating instances with resolved dependencies."""
        container = DIContainer()
        container.register("dep_a", "value_a")
        container.register("dep_b", 42)

        class Service:
            def __init__(self, param_a, param_b):
                self.a = param_a
                self.b = param_b

        service = container.create(Service, param_a="dep_a", param_b="dep_b")

        assert service.a == "value_a"
        assert service.b == 42

    def test_clear_removes_all(self):
        """Test that clear removes all services and factories."""
        container = DIContainer()
        container.register("service", object())
        container.register_factory("factory", lambda c: object())

        container.clear()

        assert not container.is_registered("service")
        assert not container.is_registered("factory")

    def test_get_registered_keys(self):
        """Test listing registered keys."""
        container = DIContainer()
        container.register("service1", object())
        container.register("service2", object())
        container.register_factory("factory1", lambda c: object())

        keys = container.get_registered_keys()

        assert set(keys) == {"service1", "service2", "factory1"}

    def test_overwrite_service(self):
        """Test that registering same key overwrites previous value."""
        container = DIContainer()
        original = object()
        replacement = object()

        container.register("test", original)
        container.register("test", replacement)

        assert container.resolve("test") is replacement


class TestGlobalContainer:
    """Tests for global container singleton."""

    def setup_method(self):
        """Reset container before each test."""
        reset_container()

    def test_get_container_returns_singleton(self):
        """Test that get_container returns same instance."""
        first = get_container()
        second = get_container()

        assert first is second

    def test_reset_container_clears_singleton(self):
        """Test that reset_container creates new instance."""
        first = get_container()
        first.register("marker", object())

        reset_container()
        second = get_container()

        assert first is not second
        assert not second.is_registered("marker")


class TestServiceKeys:
    """Tests for ServiceKeys constants."""

    def test_service_keys_are_strings(self):
        """Test that all service keys are defined as strings."""
        keys = [
            ServiceKeys.ESI_CLIENT,
            ServiceKeys.REPOSITORY,
            ServiceKeys.SDE_PROVIDER,
            ServiceKeys.CONFIG,
            ServiceKeys.SETTINGS_MANAGER,
            ServiceKeys.SIGNAL_BUS,
            ServiceKeys.CHARACTER_SERVICE,
            ServiceKeys.ASSET_SERVICE,
            ServiceKeys.LOCATION_SERVICE,
            ServiceKeys.WALLET_SERVICE,
            ServiceKeys.MARKET_SERVICE,
            ServiceKeys.CONTRACT_SERVICE,
            ServiceKeys.INDUSTRY_SERVICE,
            ServiceKeys.NETWORTH_SERVICE,
        ]

        for key in keys:
            assert isinstance(key, str)
            assert len(key) > 0
