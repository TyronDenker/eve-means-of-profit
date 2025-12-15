"""Dependency Injection Container for EVE Means of Profit.

Provides a lightweight dependency injection system for managing application
services and their dependencies.

Features:
- Service registration (instances and factories)
- Lazy instantiation via factories
- Thread-safe singleton pattern
- Optional interface for backwards compatibility

Usage:
    from src.utils.di_container import DIContainer, get_container

    # Get the global container
    container = get_container()

    # Register services
    container.register("esi_client", esi_client_instance)
    container.register_factory("settings", lambda c: SettingsManager())

    # Resolve services
    esi = container.resolve("esi_client")
    settings = container.resolve("settings")

    # Class-based injection
    class MyService:
        def __init__(self, esi_client: ESIClient, settings: SettingsManager):
            self.esi = esi_client
            self.settings = settings

    # Auto-wire from container
    service = container.create(MyService, esi_client="esi_client", settings="settings")
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DIContainerError(Exception):
    """Exception raised for DI container errors."""

    pass


class DIContainer:
    """Simple dependency injection container.

    Manages service instances and factories for dependency resolution.
    Thread-safe for concurrent access.
    """

    def __init__(self) -> None:
        """Initialize empty container."""
        self._services: dict[str, Any] = {}
        self._factories: dict[str, Callable[[DIContainer], Any]] = {}
        self._lock = threading.RLock()

    def register(self, key: str, instance: Any) -> None:
        """Register a service instance.

        Args:
            key: Service identifier
            instance: Service instance to register
        """
        with self._lock:
            if key in self._services:
                logger.debug("Overwriting existing service: %s", key)
            self._services[key] = instance
            logger.debug("Registered service: %s", key)

    def register_factory(self, key: str, factory: Callable[[DIContainer], Any]) -> None:
        """Register a factory function for lazy instantiation.

        The factory receives the container as argument for resolving
        nested dependencies.

        Args:
            key: Service identifier
            factory: Factory function (container) -> service instance
        """
        with self._lock:
            if key in self._factories:
                logger.debug("Overwriting existing factory: %s", key)
            self._factories[key] = factory
            logger.debug("Registered factory: %s", key)

    def resolve(self, key: str) -> Any:
        """Resolve a service by key.

        If a factory is registered for the key and no instance exists yet,
        the factory is called once and the result is cached.

        Args:
            key: Service identifier

        Returns:
            Service instance

        Raises:
            DIContainerError: If service is not registered
        """
        with self._lock:
            # Check for existing instance first
            if key in self._services:
                return self._services[key]

            # Try factory
            if key in self._factories:
                logger.debug("Creating service from factory: %s", key)
                instance = self._factories[key](self)
                self._services[key] = instance
                return instance

            raise DIContainerError(
                f"Service '{key}' not registered. "
                f"Available: {list(self._services.keys()) + list(self._factories.keys())}"
            )

    def resolve_optional(self, key: str) -> Any | None:
        """Resolve a service by key, returning None if not found.

        Args:
            key: Service identifier

        Returns:
            Service instance or None
        """
        try:
            return self.resolve(key)
        except DIContainerError:
            return None

    def is_registered(self, key: str) -> bool:
        """Check if a service is registered.

        Args:
            key: Service identifier

        Returns:
            True if service or factory is registered
        """
        with self._lock:
            return key in self._services or key in self._factories

    def create(self, cls: type[T], **key_mappings: str) -> T:
        """Create an instance of a class with dependencies resolved from container.

        Args:
            cls: Class to instantiate
            **key_mappings: Mapping of constructor parameter names to container keys

        Returns:
            Instance of cls with dependencies injected

        Example:
            service = container.create(
                MyService,
                esi_client="esi_client",
                settings="settings_manager"
            )
        """
        resolved_args = {}
        for param_name, container_key in key_mappings.items():
            resolved_args[param_name] = self.resolve(container_key)
        return cls(**resolved_args)

    def clear(self) -> None:
        """Clear all registered services and factories.

        Primarily for testing.
        """
        with self._lock:
            self._services.clear()
            self._factories.clear()
            logger.debug("Container cleared")

    def get_registered_keys(self) -> list[str]:
        """Get list of all registered service keys.

        Returns:
            List of service/factory keys
        """
        with self._lock:
            return list(set(self._services.keys()) | set(self._factories.keys()))


# Standard service keys for the application
class ServiceKeys:
    """Standard service key constants for the DI container."""

    # Core infrastructure
    ESI_AUTH = "esi_auth"
    ESI_CLIENT = "esi_client"
    REPOSITORY = "repository"
    SDE_PROVIDER = "sde_provider"
    SDE_CLIENT = "sde_client"
    FUZZWORK_CLIENT = "fuzzwork_client"
    FUZZWORK_PROVIDER = "fuzzwork_provider"

    # Configuration/Settings
    CONFIG = "config"
    SETTINGS_MANAGER = "settings_manager"
    METRICS = "metrics"

    # UI infrastructure
    SIGNAL_BUS = "signal_bus"

    # Business services
    CHARACTER_SERVICE = "character_service"
    ASSET_SERVICE = "asset_service"
    LOCATION_SERVICE = "location_service"
    WALLET_SERVICE = "wallet_service"
    MARKET_SERVICE = "market_service"
    CONTRACT_SERVICE = "contract_service"
    INDUSTRY_SERVICE = "industry_service"
    NETWORTH_SERVICE = "networth_service"


# Global singleton container
_container_instance: DIContainer | None = None
_container_lock = threading.Lock()


def get_container() -> DIContainer:
    """Get the global DI container instance.

    Returns:
        Global DIContainer singleton
    """
    global _container_instance  # noqa: PLW0603
    if _container_instance is None:
        with _container_lock:
            if _container_instance is None:
                _container_instance = DIContainer()
    # Type checker needs assurance - will always be set at this point
    assert _container_instance is not None
    return _container_instance


def reset_container() -> None:
    """Reset the global container.

    Primarily for testing.
    """
    global _container_instance  # noqa: PLW0603
    with _container_lock:
        if _container_instance is not None:
            _container_instance.clear()
        _container_instance = None


def configure_container(container: DIContainer | None = None) -> DIContainer:
    """Configure the DI container with default service factories.

    This sets up lazy factories for core services. Services are only
    instantiated when first resolved.

    Args:
        container: Container to configure (uses global if None)

    Returns:
        Configured container
    """
    if container is None:
        container = get_container()

    # Register config (eager - needed by many other services)
    from src.utils.config import get_config

    container.register(ServiceKeys.CONFIG, get_config())

    # Register metrics collector
    from src.utils.metrics import get_metrics

    container.register(ServiceKeys.METRICS, get_metrics())

    # Register signal bus (UI event bus)
    def signal_bus_factory(c: DIContainer) -> Any:
        from ui.signal_bus import SignalBus

        return SignalBus()

    container.register_factory(ServiceKeys.SIGNAL_BUS, signal_bus_factory)

    # Register settings manager
    def settings_factory(c: DIContainer) -> Any:
        from src.utils.settings_manager import SettingsManager

        return SettingsManager()

    container.register_factory(ServiceKeys.SETTINGS_MANAGER, settings_factory)

    # Register ESI authentication
    def esi_auth_factory(c: DIContainer) -> Any:
        from data.clients.esi.auth import ESIAuth

        config = c.resolve(ServiceKeys.CONFIG)
        return ESIAuth(
            client_id=config.esi.client_id,
            callback_url=config.esi.callback_url,
            token_file=config.esi.token_file_path,
        )

    container.register_factory(ServiceKeys.ESI_AUTH, esi_auth_factory)

    # Register ESI client (lazy singleton via container)
    # Note: ESIClient is fully async-safe and thread-safe. The container
    # creates one instance that is shared across services. Each ESIClient
    # has its own httpx.AsyncClient and async locks, making concurrent
    # requests safe. Multiple independent ESIClient instances can coexist
    # if needed (e.g., for testing or multi-account scenarios).
    def esi_client_factory(c: DIContainer) -> Any:
        from data.clients import ESIClient

        config = c.resolve(ServiceKeys.CONFIG)
        return ESIClient(client_id=config.esi.client_id)

    container.register_factory(ServiceKeys.ESI_CLIENT, esi_client_factory)

    # Register repository
    def repository_factory(c: DIContainer) -> Any:
        from data.repositories import Repository

        return Repository()

    container.register_factory(ServiceKeys.REPOSITORY, repository_factory)

    # Register SDE provider
    def sde_provider_factory(c: DIContainer) -> Any:
        from data import SDEProvider
        from data.parsers import SDEJsonlParser

        config = c.resolve(ServiceKeys.CONFIG)
        parser = SDEJsonlParser(str(config.sde.sde_dir_path))
        # No progress callback in DI factory - will be set when needed
        return SDEProvider(parser, progress_callback=None)

    container.register_factory(ServiceKeys.SDE_PROVIDER, sde_provider_factory)

    # Register SDE client
    def sde_client_factory(c: DIContainer) -> Any:
        from data.clients.sde_client import SDEClient

        config = c.resolve(ServiceKeys.CONFIG)
        return SDEClient(config=config, progress_callback=None)

    container.register_factory(ServiceKeys.SDE_CLIENT, sde_client_factory)

    # Register Fuzzwork client
    def fuzzwork_client_factory(c: DIContainer) -> Any:
        from data.clients import FuzzworkClient

        return FuzzworkClient()

    container.register_factory(ServiceKeys.FUZZWORK_CLIENT, fuzzwork_client_factory)

    # Register Fuzzwork provider (lazy - initialized when CSV is fetched)
    def fuzzwork_provider_factory(c: DIContainer) -> Any:
        """Create FuzzworkProvider with parser from cached CSV.

        Note: This factory returns None if CSV is not yet downloaded.
        The provider should be initialized after fuzzwork data is fetched.
        """
        from data import FuzzworkProvider
        from data.parsers.fuzzwork_csv import FuzzworkCSVParser

        config = c.resolve(ServiceKeys.CONFIG)
        csv_path = config.app.user_data_dir / "fuzzwork" / "aggregatecsv.csv"
        if csv_path.exists():
            parser = FuzzworkCSVParser(csv_path)
            return FuzzworkProvider(parser)
        return None

    container.register_factory(ServiceKeys.FUZZWORK_PROVIDER, fuzzwork_provider_factory)

    # Register location service
    def location_service_factory(c: DIContainer) -> Any:
        from services.location_service import LocationService

        return LocationService(
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
            sde_provider=c.resolve(ServiceKeys.SDE_PROVIDER),
        )

    container.register_factory(ServiceKeys.LOCATION_SERVICE, location_service_factory)

    # Register character service
    def character_service_factory(c: DIContainer) -> Any:
        from services.character_service import CharacterService

        return CharacterService(esi_client=c.resolve(ServiceKeys.ESI_CLIENT))

    container.register_factory(ServiceKeys.CHARACTER_SERVICE, character_service_factory)

    # Register asset service
    def asset_service_factory(c: DIContainer) -> Any:
        from services.asset_service import AssetService

        return AssetService(
            sde_provider=c.resolve(ServiceKeys.SDE_PROVIDER),
            location_service=c.resolve(ServiceKeys.LOCATION_SERVICE),
            repository=c.resolve(ServiceKeys.REPOSITORY),
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
        )

    container.register_factory(ServiceKeys.ASSET_SERVICE, asset_service_factory)

    # Register wallet service
    def wallet_service_factory(c: DIContainer) -> Any:
        from services.wallet_service import WalletService

        return WalletService(
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
            repository=c.resolve(ServiceKeys.REPOSITORY),
        )

    container.register_factory(ServiceKeys.WALLET_SERVICE, wallet_service_factory)

    # Register market service
    def market_service_factory(c: DIContainer) -> Any:
        from services.market_service import MarketService

        return MarketService(
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
            repository=c.resolve(ServiceKeys.REPOSITORY),
        )

    container.register_factory(ServiceKeys.MARKET_SERVICE, market_service_factory)

    # Register contract service
    def contract_service_factory(c: DIContainer) -> Any:
        from services.contract_service import ContractService

        return ContractService(
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
            repository=c.resolve(ServiceKeys.REPOSITORY),
        )

    container.register_factory(ServiceKeys.CONTRACT_SERVICE, contract_service_factory)

    # Register industry service
    def industry_service_factory(c: DIContainer) -> Any:
        from services.industry_service import IndustryService

        return IndustryService(
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
            repository=c.resolve(ServiceKeys.REPOSITORY),
        )

    container.register_factory(ServiceKeys.INDUSTRY_SERVICE, industry_service_factory)

    # Register networth service
    def networth_service_factory(c: DIContainer) -> Any:
        from services.networth_service import NetWorthService

        return NetWorthService(
            esi_client=c.resolve(ServiceKeys.ESI_CLIENT),
            repository=c.resolve(ServiceKeys.REPOSITORY),
            fuzzwork_provider=c.resolve_optional(ServiceKeys.FUZZWORK_PROVIDER),
            settings_manager=c.resolve(ServiceKeys.SETTINGS_MANAGER),
            sde_provider=c.resolve(ServiceKeys.SDE_PROVIDER),
            location_service=c.resolve(ServiceKeys.LOCATION_SERVICE),
        )

    container.register_factory(ServiceKeys.NETWORTH_SERVICE, networth_service_factory)

    logger.info("DI container configured with default factories")
    return container
