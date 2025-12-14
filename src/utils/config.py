"""Centralized configuration management for EVE Means of Profit.

This module provides application-level configuration from environment variables.

Features:
- Environment variable support via .env files
- Fallback priority: .env → hardcoded defaults
- Automatic .env.example generation from defaults
- Type-safe configuration using Pydantic
- Singleton pattern for global access

Usage:
    from utils import global_config

    # Access configuration values
    client = ESIClient(
        client_id=global_config.esi.client_id,
        datasource=global_config.esi.datasource,
        callback_url=global_config.esi.callback_url,
    )
"""

from __future__ import annotations

import sys
import threading
import tomllib
from datetime import UTC, datetime
from logging import getLogger
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = getLogger(__name__)


def _read_pyproject() -> dict:
    """Read pyproject.toml and extract project metadata."""
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    # If running in a PyInstaller bundle, try the runtime base path as well
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        frozen_path = Path(sys._MEIPASS) / "pyproject.toml"  # noqa: SLF001
        # Prefer the frozen path if it exists
        if frozen_path.exists():
            pyproject_path = frozen_path
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            project = data.get("project", {})

            # Collect common URL fields if present (homepage, repository, urls table)
            urls = {}

            # PEP 621 allows a 'urls' table under project; include it if present
            if isinstance(project.get("urls"), dict):
                for k, v in project.get("urls", {}).items():
                    if isinstance(v, str):
                        urls[str(k).lower()] = v

            # Extract first author's email if available
            email = None
            authors = project.get("authors") or []
            if isinstance(authors, list) and authors:
                first = authors[0]
                if isinstance(first, dict) and first.get("email"):
                    email = first.get("email")

            # Also allow custom tool-scoped metadata under [tool.additional_contact]
            tool_table = data.get("tool", {})
            tool_meta = {}
            if isinstance(tool_table, dict):
                tool_meta = tool_table.get("additional_contact") or {}
                # Extract referrals from [tool.referrals]
                referrals = (
                    tool_table.get("referrals", {})
                    if isinstance(tool_table, dict)
                    else {}
                )

            github = urls.get("github") or urls.get("repository")
            discord = tool_meta.get("discord") if isinstance(tool_meta, dict) else None
            eve = tool_meta.get("eve") if isinstance(tool_meta, dict) else None
            discord_invite = (
                tool_meta.get("discord_invite") if isinstance(tool_meta, dict) else None
            )

            return {
                "name": project.get("name", "eve-means-of-profit"),
                "version": project.get("version", "?.?.?"),
                "urls": urls,
                "email": email,
                "github": github,
                "discord": discord,
                "discord_invite": discord_invite,
                "eve": eve,
                "referrals": referrals,
            }
    except Exception as e:
        # Fallback to defaults if pyproject.toml can't be read
        logger.warning(f"Could not read pyproject.toml: {e}")
        return {
            "name": "eve-means-of-profit",
            "version": "?.?.?",
            "urls": {},
            "email": None,
            "github": None,
            "discord": None,
            "eve": None,
        }


# Read project metadata once at module load
_PROJECT_METADATA = _read_pyproject()


class ESIConfig(BaseSettings):
    """EVE ESI (EVE Swagger Interface) API configuration."""

    # SSO URLs
    base_login_url: str = Field(
        default="https://login.eveonline.com",
        description="Base URL for EVE SSO",
    )
    auth_url: str = Field(
        default="https://login.eveonline.com/v2/oauth/authorize",
        description="OAuth authorization endpoint",
    )
    token_url: str = Field(
        default="https://login.eveonline.com/v2/oauth/token",
        description="OAuth token endpoint",
    )
    verify_url: str = Field(
        default="https://esi.evetech.net/verify/",
        description="Token verification endpoint",
    )

    # Client credentials
    client_id: str = Field(
        default="96016d6599dd4ee18aac2bfdf86cb448",
        description="EVE application client ID from https://developers.eveonline.com/",
    )
    callback_url: str = Field(
        default="http://localhost:8080/eve-means-of-profit",
        description="OAuth callback URL (must match app registration)",
    )

    # API URLs
    esi_base_url: str = Field(
        default="https://esi.evetech.net/latest",
        description="Base URL for ESI API endpoints",
    )
    esi_spec_url: str = Field(
        default="https://esi.evetech.net/meta/openapi.json",
        description="URL for OpenAPI specification",
    )

    # Datasource
    datasource: Literal["tranquility", "singularity"] = Field(
        default="tranquility",
        description="EVE server datasource (tranquility=live, singularity=test)",
    )

    # Storage paths (relative to user_data_dir)
    cache_dir: str = Field(
        default="esi/cache",
        description="Directory for API response cache storage (relative to user_data_dir)",
    )
    token_file: str = Field(
        default="esi/tokens.json",
        description="Path to OAuth token storage file (relative to user_data_dir)",
    )
    rate_limit_file: str = Field(
        default="esi/rate_limits.json",
        description="Path to rate limit tracking file (relative to user_data_dir)",
    )

    # Cache settings
    cache_expiry_warning: int = Field(
        default=60,
        description="Seconds before cache expiry to issue warning",
        ge=0,
    )
    compatibility_date: str | None = Field(
        default="2025-11-06",
        description="ESI compatibility date (YYYY-MM-DD format) for X-Compatibility-Date header",
    )

    rate_limit_threshold_percent: float = Field(
        default=20.0,
        description="Threshold percentage (0-100) of a token bucket's capacity to trigger slowdown.",
    )

    error_limit_capacity: int = Field(
        default=10,
        description="Assumed maximum error budget for legacy error-limit headers (used with percentage threshold)",
        ge=1,
    )
    max_backoff_delay: int = Field(
        default=60,
        description="Maximum backoff delay in seconds",
        ge=1,
    )

    # ESI Scopes - Centralized scope management
    default_scopes: list[str] = Field(
        default=[
            "esi-assets.read_assets.v1",
            "esi-wallet.read_character_wallet.v1",
            "esi-markets.read_character_orders.v1",
            "esi-contracts.read_character_contracts.v1",
            "esi-skills.read_skills.v1",
            "esi-industry.read_character_jobs.v1",
            "esi-universe.read_structures.v1",
        ],
        description="Default ESI scopes requested during character authentication",
    )

    available_scopes: dict[str, str] = Field(
        default={
            "esi-assets.read_assets.v1": "View your character's assets",
            "esi-wallet.read_character_wallet.v1": "View your character's wallet",
            "esi-markets.read_character_orders.v1": "View your market orders",
            "esi-contracts.read_character_contracts.v1": "View your contracts",
            "esi-skills.read_skills.v1": "View your skills",
            "esi-industry.read_character_jobs.v1": "View your industry jobs",
            "esi-universe.read_structures.v1": "View structure names (requires docking access)",
            "esi-wallet.read_corporation_wallets.v1": "View corporation wallet (for corp tracking)",
            "esi-assets.read_corporation_assets.v1": "View corporation assets (for corp tracking)",
            "esi-markets.read_corporation_orders.v1": "View corporation market orders",
            "esi-contracts.read_corporation_contracts.v1": "View corporation contracts",
            "esi-industry.read_corporation_jobs.v1": "View corporation industry jobs",
        },
        description="Available ESI scopes with user-friendly descriptions",
    )

    model_config = SettingsConfigDict(
        env_prefix="ESI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cache_dir_path(self) -> Path:
        """Resolved cache directory path (writable, uses user_data_dir when bundled)."""
        path = Path(self.cache_dir)
        if path.is_absolute():
            return path
        # Import here to avoid circular dependency during module load
        return get_config().app.user_data_dir / self.cache_dir

    @property
    def token_file_path(self) -> Path:
        """Resolved token file path (writable, uses user_data_dir when bundled)."""
        path = Path(self.token_file)
        if path.is_absolute():
            return path
        return get_config().app.user_data_dir / self.token_file

    @property
    def rate_limit_file_path(self) -> Path:
        """Resolved rate limit file path (writable, uses user_data_dir when bundled)."""
        path = Path(self.rate_limit_file)
        if path.is_absolute():
            return path
        return get_config().app.user_data_dir / self.rate_limit_file

    @field_validator("compatibility_date")
    @classmethod
    def validate_compatibility_date(cls, v: str | None) -> str | None:
        """Validate compatibility date format and ensure it's not in the future."""
        if v is None or v == "":
            return None

        # Basic YYYY-MM-DD format check
        if len(v) != 10 or v[4] != "-" or v[7] != "-":
            raise ValueError(
                f"compatibility_date must be in YYYY-MM-DD format, got: {v}"
            )

        # Validate it's a valid date and not in the future
        try:
            parsed_date = datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=UTC).date()
        except ValueError as e:
            raise ValueError(
                f"compatibility_date must be a valid date in YYYY-MM-DD format: {e}"
            ) from e

        today = datetime.now(UTC).date()
        if parsed_date > today:
            raise ValueError(
                f"compatibility_date cannot be in the future. Got {v}, today is {today}"
            )

        return v


class SDEConfig(BaseSettings):
    """Static Data Export (SDE) configuration."""

    sde_dir: str = Field(
        default="sde/",
        description="Directory containing SDE JSONL files (relative to data_dir)",
    )

    # RIFT endpoint
    rift_download_url_template: str = Field(
        default="https://sde.riftforeve.online/assets/eve-online-static-data-{build_id}-enhanced-jsonl.zip",
        description="Template URL for downloading enhanced SDE from RIFT (format with build_id)",
    )

    # CCP endpoints
    ccp_latest_url: str = Field(
        default="https://developers.eveonline.com/static-data/tranquility/latest.jsonl",
        description="URL for latest SDE build metadata from CCP",
    )
    ccp_changes_url_template: str = Field(
        default="https://developers.eveonline.com/static-data/tranquility/changes/{build_id}.jsonl",
        description="Template URL for CCP SDE changes feed (format with build_id)",
    )

    model_config = SettingsConfigDict(
        env_prefix="SDE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def sde_dir_path(self) -> Path:
        """Resolved SDE data directory path.

        When frozen (PyInstaller), looks for data beside the executable.
        In development, uses the project data directory.
        """
        path = Path(self.sde_dir)
        if path.is_absolute():
            return path
        # Always use user_data_dir which points to the correct location in both modes
        return get_config().app.user_data_dir / self.sde_dir


class AppConfig(BaseSettings):
    """Application-wide configuration."""

    name: str = Field(
        default_factory=lambda: _PROJECT_METADATA["name"],
        description="Application name (from pyproject.toml)",
    )
    version: str = Field(
        default_factory=lambda: _PROJECT_METADATA["version"],
        description="Application version (from pyproject.toml)",
    )
    user_agent: str = Field(
        default="",
        description="HTTP User-Agent header (auto-generated if empty)",
    )
    contact_email: str | None = Field(
        default_factory=lambda: _PROJECT_METADATA.get("email"),
        description="Contact email derived from first pyproject author",
    )
    contact_github: str | None = Field(
        default_factory=lambda: _PROJECT_METADATA.get("github"),
        description="Primary GitHub/repository URL from pyproject",
    )
    contact_discord: str | None = Field(
        default_factory=lambda: _PROJECT_METADATA.get("discord"),
        description="Optional Discord contact from pyproject urls",
    )
    contact_eve: str | None = Field(
        default_factory=lambda: _PROJECT_METADATA.get("eve"),
        description="Optional EVE character/contact from pyproject urls",
    )
    contact_discord_invite: str | None = Field(
        default_factory=lambda: _PROJECT_METADATA.get("discord_invite"),
        description="Discord invite link from pyproject [tool.additional_contact]",
    )

    referrals: dict[str, str] = Field(
        default_factory=lambda: _PROJECT_METADATA.get("referrals", {}),
        description="Referral links and codes from pyproject.toml [tool.referrals]",
    )

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="WARNING",
        description="Logging level",
    )

    # Project paths
    project_root: Path = Field(
        # Make project_root runtime-aware: when frozen, prefer the extracted
        # runtime base path so that file operations (like writing .env.example)
        # target a writable location next to the executable.
        default_factory=lambda: Path(sys._MEIPASS)  # noqa: SLF001
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        else Path(__file__).parent.parent.parent,
        description="Project root directory",
    )
    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent / "data",
        description="Data directory (development only - use user_data_dir for writable files)",
    )

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def runtime_base_path(self) -> Path:
        """Get base path for bundled resources (PyInstaller-aware).

        Returns:
            Path to bundled resources when frozen (PyInstaller), otherwise project root.
        """
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            # Running in PyInstaller bundle - return temporary extraction directory
            return Path(sys._MEIPASS)  # noqa: SLF001
        return self.project_root

    @property
    def user_data_dir(self) -> Path:
        """Get user data directory for writable files.

        Returns a 'data' directory next to the executable (when frozen) or
        next to the project root (in development).

        Returns:
            Path to directory for cache, tokens, logs, and other writable data.
        """
        if getattr(sys, "frozen", False):
            # When frozen (PyInstaller), place data dir next to the executable
            # sys.executable is the path to the .exe file
            app_dir = Path(sys.executable).parent / "data"
        else:
            # In development, use project data dir
            app_dir = self.data_dir

        # Ensure directory exists
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir

    @property
    def user_settings_file(self) -> Path:
        """Get path to viewer settings JSON file.

        Returns:
            Path to user_settings.json in user_data_dir.
        """
        return self.user_data_dir / "user_settings.json"

    @property
    def computed_user_agent(self) -> str:
        """Generate User-Agent header if not explicitly set."""
        if self.user_agent:
            return self.user_agent
        # Build a rich user-agent including optional metadata from pyproject
        parts = [f"{self.name}/{self.version}"]

        extra_parts = []

        # Prefer explicit contact fields from AppConfig (derived from pyproject)
        if self.contact_github:
            extra_parts.append(self.contact_github)
        elif _PROJECT_METADATA.get("urls"):
            # Fall back to urls.repository or urls.homepage
            urls = _PROJECT_METADATA.get("urls") or {}
            primary = urls.get("repository") or urls.get("homepage")
            if primary:
                extra_parts.append(primary)

        if self.contact_email:
            extra_parts.append(f"{self.contact_email}")

        if self.contact_discord:
            extra_parts.append(f"discord:{self.contact_discord}")

        if self.contact_eve:
            extra_parts.append(f"eve:{self.contact_eve}")

        if extra_parts:
            parts.append(f"(+{'; '.join(extra_parts)})")

        return " ".join(parts)


class Config:
    """Main configuration container with auto-initialization."""

    def __init__(self) -> None:
        """Initialize configuration from environment and defaults."""
        self.app = AppConfig()
        self.esi = ESIConfig()
        self.sde = SDEConfig()

        # Ensure .env.example is up to date
        self._update_env_example()

    def _update_env_example(self) -> None:
        """Update .env.example with current default values."""
        env_example_path = self.app.project_root / ".env.example"

        # Generate example content from all config sections
        lines = [
            "# EVE Means of Profit - Environment Configuration",
            "# Copy this file to .env and customize the values",
            "#",
            "# Priority: .env > hardcoded defaults",
            "",
            "# ============================================================================",
            "# Application Settings",
            "# ============================================================================",
            "",
        ]

        # App config
        for field_name, field_info in AppConfig.model_fields.items():
            if field_name in ("project_root", "data_dir"):
                continue  # Skip computed paths

            # Get actual default value (handle default_factory)
            if field_info.default_factory:
                try:
                    default = field_info.default_factory()
                except Exception:
                    default = None
            else:
                default = field_info.default

            description = field_info.description or ""
            env_var = f"APP_{field_name.upper()}"

            lines.append(f"# {description}")
            # For the user_agent field, prefer the computed value so the
            # example shows a useful User-Agent even when the default is
            # an empty string.
            if field_name == "user_agent":
                try:
                    ua = self.app.computed_user_agent
                except Exception:
                    ua = default or ""
                lines.append(f"# {env_var}={ua}")
            else:
                # Show empty defaults explicitly when None
                if default is None:
                    lines.append(f"# {env_var}=")
                else:
                    lines.append(f"# {env_var}={default}")
            lines.append("")

        lines.extend(
            [
                "# ============================================================================",
                "# ESI API Settings",
                "# ============================================================================",
                "",
            ]
        )

        # ESI config
        for field_name, field_info in ESIConfig.model_fields.items():
            default = field_info.default
            description = field_info.description or ""
            env_var = f"ESI_{field_name.upper()}"

            lines.append(f"# {description}")
            if default is None or default == "":
                lines.append(f"# {env_var}=")
            else:
                lines.append(f"# {env_var}={default}")
            lines.append("")

        lines.extend(
            [
                "# ============================================================================",
                "# SDE (Static Data Export) Settings",
                "# ============================================================================",
                "",
            ]
        )

        # SDE config
        for field_name, field_info in SDEConfig.model_fields.items():
            default = field_info.default
            description = field_info.description or ""
            env_var = f"SDE_{field_name.upper()}"

            lines.append(f"# {description}")
            lines.append(f"# {env_var}={default}")
            lines.append("")

        # Write to file. Try the preferred location first; if that fails and
        # we weren't already targeting project_root, attempt a fallback to
        # project_root so the example is created where the developer expects
        # it.
        content = "\n".join(lines)
        try:
            env_example_path.parent.mkdir(parents=True, exist_ok=True)
            env_example_path.write_text(content, encoding="utf-8")
            return
        except Exception as first_exc:
            logger.warning(
                f"Could not write .env.example to {env_example_path}: {first_exc}"
            )

        # If we tried user_data_dir and failed, try project root as a final
        # fallback (don't re-raise; this is non-fatal).
        try:
            fallback_path = Path(__file__).parent.parent.parent / ".env.example"
            fallback_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_path.write_text(content, encoding="utf-8")
            logger.info(f"Wrote fallback .env.example to {fallback_path}")
        except Exception as final_exc:
            logger.warning(
                f"Could not update .env.example in fallback location: {final_exc}"
            )

    def reload(self) -> None:
        """Reload configuration from environment variables."""
        self.__init__()

    def __repr__(self) -> str:
        """String representation of config."""
        return f"Config(\n  app={self.app},\n  esi={self.esi},\n  sde={self.sde}\n)"


# Global configuration instance (singleton)
_config_instance: Config | None = None
_config_lock: threading.Lock | None = None


def _get_config_lock() -> threading.Lock:
    """Get the config lock, creating it lazily."""
    global _config_lock  # noqa: PLW0603
    if _config_lock is None:
        _config_lock = threading.Lock()
    return _config_lock


def get_config(config: Config | None = None) -> Config:
    """Get the global configuration instance (lazy initialization).

    Args:
        config: Optional config instance to use instead of singleton.
                If provided on first call, sets the singleton.
                Useful for dependency injection.

    Returns:
        Global Config instance
    """
    global _config_instance  # noqa: PLW0603

    if config is not None:
        with _get_config_lock():
            _config_instance = config
        return _config_instance

    if _config_instance is None:
        with _get_config_lock():
            if _config_instance is None:
                _config_instance = Config()

    # Type checker needs assurance - will always be set at this point
    assert _config_instance is not None
    return _config_instance


# Convenience function to reload config
def reload_config() -> Config:
    """Reload configuration from environment.

    Returns:
        Reloaded Config instance
    """
    global _config_instance  # noqa: PLW0603
    with _get_config_lock():
        _config_instance = Config()
    return _config_instance


def reset_config() -> None:
    """Reset the global config instance.

    Primarily for testing.
    """
    global _config_instance  # noqa: PLW0603
    with _get_config_lock():
        _config_instance = None


# Create the global config instance for convenience
global_config = get_config()
