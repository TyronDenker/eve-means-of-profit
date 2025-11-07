"""Configuration management for EVE Means of Profit.

This module provides centralized configuration using Pydantic for validation,
including path management that works both in development and when packaged
with PyInstaller.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_base_path() -> Path:
    """Get the base path for the application.

    This works correctly both in development and when frozen by PyInstaller.
    When frozen, uses sys._MEIPASS. Otherwise, uses the project root.

    Returns:
        Path to the application base directory

    """
    if getattr(sys, "frozen", False):
        # Running as compiled executable (PyInstaller)
        # sys._MEIPASS is the temporary folder PyInstaller creates
        return Path(getattr(sys, "_MEIPASS", ""))
    # Running in development
    # Go up from src/utils/config.py to project root
    return Path(__file__).parent.parent.parent


class PathSettings(BaseModel):
    """Path configuration settings."""

    base_path: Path = Field(default_factory=get_base_path)
    data_path: Path | None = Field(default=None)
    sde_path: Path | None = Field(default=None)
    fuzzwork_path: Path | None = Field(default=None)  # Added fuzzwork_path
    esi_cache_dir: Path | None = Field(default=None)
    esi_token_file: Path | None = Field(default=None)

    @model_validator(mode="after")
    def resolve_all_paths(self) -> PathSettings:
        """Resolve all paths from environment variables or defaults.

        Priority: explicit value > environment variable > computed default
        All dependent paths are based on data_path.
        """
        # Resolve data_path first
        if self.data_path is None:
            env_data = os.environ.get("EVE_DATA_PATH")
            self.data_path = Path(env_data) if env_data else self.base_path / "data"

        # Resolve dependent paths
        if self.sde_path is None:
            env_sde = os.environ.get("EVE_SDE_PATH")
            self.sde_path = Path(env_sde) if env_sde else self.data_path / "sde"

        if self.fuzzwork_path is None:  # Resolve fuzzwork_path
            env_fuzzwork = os.environ.get("EVE_FUZZWORK_PATH")
            self.fuzzwork_path = (
                Path(env_fuzzwork) if env_fuzzwork else self.data_path / "fuzzwork"
            )

        if self.esi_cache_dir is None:
            env_cache = os.environ.get("EVE_ESI_CACHE_DIR")
            self.esi_cache_dir = (
                Path(env_cache) if env_cache else self.data_path / "esi" / "cache"
            )

        if self.esi_token_file is None:
            env_token = os.environ.get("EVE_ESI_TOKEN_FILE")
            self.esi_token_file = (
                Path(env_token) if env_token else self.data_path / "esi" / "tokens.json"
            )

        return self


class APISettings(BaseModel):
    """ESI API configuration settings."""

    client_id: str | None = Field(default=None)
    redirect_uri: str = Field(default="http://localhost:8080/eve-means-of-profit")
    base_url: str = Field(default="https://esi.evetech.net/latest")
    user_agent: str = Field(
        default="eve-means-of-profit/0.1.0 (tyronevedenker@gmail.com; "
        "+https://github.com/TyronDenker/eve-means-of-profit; "
        "discord:tyrondenker; eve:Tyron Denker)"
    )
    rate_limit_threshold: int = Field(default=10, ge=1, le=100)

    @field_validator("client_id", mode="before")
    @classmethod
    def resolve_client_id(cls, v: str | None) -> str | None:
        """Resolve client ID from environment or value."""
        if v is not None:
            return v
        return os.environ.get("EVE_ESI_CLIENT_ID")

    @field_validator("redirect_uri", mode="before")
    @classmethod
    def resolve_redirect_uri(cls, v: str | None) -> str:
        """Resolve redirect URI from environment or default."""
        return os.environ.get(
            "EVE_ESI_REDIRECT_URI", v or "http://localhost:8080/eve-means-of-profit"
        )

    @field_validator("base_url", mode="before")
    @classmethod
    def resolve_base_url(cls, v: str | None) -> str:
        """Resolve base URL from environment or default."""
        return os.environ.get("EVE_ESI_BASE_URL", v or "https://esi.evetech.net/latest")

    @field_validator("user_agent", mode="before")
    @classmethod
    def resolve_user_agent(cls, v: str | None) -> str:
        """Resolve user agent from environment or default."""
        default_ua = (
            "eve-means-of-profit/0.1.0 (tyronevedenker@gmail.com; "
            "+https://github.com/TyronDenker/eve-means-of-profit; "
            "discord:tyrondenker; eve:Tyron Denker)"
        )
        return os.environ.get("EVE_ESI_USER_AGENT", v or default_ua)

    @field_validator("rate_limit_threshold", mode="before")
    @classmethod
    def resolve_rate_limit_threshold(cls, v: int | str | None) -> int:
        """Resolve rate limit threshold from environment or default."""
        if v is not None:
            return int(v) if isinstance(v, str) else v

        env_val = os.environ.get("EVE_ESI_RATE_LIMIT_THRESHOLD")
        return int(env_val) if env_val else 10


class CacheSettings(BaseModel):
    """Cache configuration settings."""

    enable_cache: bool = Field(default=True)
    cache_all_on_startup: bool = Field(default=False)

    @field_validator("enable_cache", mode="before")
    @classmethod
    def resolve_enable_cache(cls, v: bool | str | None) -> bool:
        """Resolve enable cache from environment or default."""
        if v is not None:
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes")
            return bool(v)

        env_val = os.environ.get("EVE_ENABLE_CACHE", "true")
        return env_val.lower() in ("true", "1", "yes")

    @field_validator("cache_all_on_startup", mode="before")
    @classmethod
    def resolve_cache_all_on_startup(cls, v: bool | str | None) -> bool:
        """Resolve cache all on startup from environment or default."""
        if v is not None:
            if isinstance(v, str):
                return v.lower() in ("true", "1", "yes")
            return bool(v)

        env_val = os.environ.get("EVE_CACHE_ALL_ON_STARTUP", "false")
        return env_val.lower() in ("true", "1", "yes")


class LoggingSettings(BaseModel):
    """Logging configuration settings."""

    log_level: str = Field(default="INFO")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    @field_validator("log_level", mode="before")
    @classmethod
    def resolve_log_level(cls, v: str | None) -> str:
        """Resolve log level from environment or default."""
        level = os.environ.get("EVE_LOG_LEVEL", v or "INFO").upper()
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        return level if level in valid_levels else "INFO"

    @field_validator("log_format", mode="before")
    @classmethod
    def resolve_log_format(cls, v: str | None) -> str:
        """Resolve log format from environment or default."""
        default_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        return os.environ.get("EVE_LOG_FORMAT", v or default_format)


class AppSettings(BaseSettings):
    """Main application settings combining all configuration sections."""

    model_config = SettingsConfigDict(
        env_prefix="EVE_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Nested configuration sections
    paths: PathSettings = Field(default_factory=PathSettings)
    api: APISettings = Field(default_factory=APISettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)

    # App metadata
    app_name: str = Field(default="eve-means-of-profit")
    app_version: str = Field(default="0.1.0")
    environment: str = Field(default="development")

    @field_validator("environment", mode="before")
    @classmethod
    def resolve_environment(cls, v: str | None) -> str:
        """Resolve environment from environment variable or default."""
        return os.environ.get("EVE_ENVIRONMENT", v or "development")


# Global settings instance (lazy loaded)
_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """Get the global settings instance (singleton pattern).

    Returns:
        AppSettings instance

    """
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = AppSettings()
    return _settings


# Simple alias for easier access
# Usage: Config.paths.sde_path, Config.api.client_id, etc.
Config = get_settings()
