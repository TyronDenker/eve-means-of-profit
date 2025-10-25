"""Configuration management for EVE Means of Profit.

This module provides centralized configuration, including path management
that works both in development and when packaged with PyInstaller.
"""

import os
import sys
from pathlib import Path


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
    else:
        # Running in development
        # Go up from src/utils/config.py to project root
        return Path(__file__).parent.parent.parent


def get_data_path() -> Path:
    """Get the data directory path.

    Returns:
        Path to the data directory

    """
    # Check if DATA_PATH environment variable is set (for custom locations)
    env_path = os.environ.get("EVE_DATA_PATH")
    if env_path:
        return Path(env_path)

    # Default to data/ in base path
    return get_base_path() / "data"


def get_sde_path() -> Path:
    """Get the SDE data directory path.

    Returns:
        Path to the SDE data directory (contains .jsonl files)

    """
    # Check if SDE_PATH environment variable is set
    env_path = os.environ.get("EVE_SDE_PATH")
    if env_path:
        return Path(env_path)

    # Default to data/sde in base path
    return get_data_path() / "sde"


class Config:
    """Application configuration container.

    This class provides access to all configuration values including paths.
    Use this instead of hardcoded paths for PyInstaller compatibility.
    """

    # Path configuration
    BASE_PATH: Path = get_base_path()
    DATA_PATH: Path = get_data_path()
    SDE_PATH: Path = get_sde_path()

    # Logging configuration
    LOG_LEVEL: str = os.environ.get("EVE_LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Cache configuration
    ENABLE_CACHE: bool = os.environ.get("EVE_ENABLE_CACHE", "true").lower() == "true"
    CACHE_ALL_ON_STARTUP: bool = (
        os.environ.get("EVE_CACHE_ALL_ON_STARTUP", "false").lower() == "true"
    )

    @classmethod
    def validate_paths(cls) -> list[str]:
        """Validate that all required paths exist.

        Returns:
            List of error messages (empty if all paths are valid)

        """
        errors: list[str] = []

        if not cls.BASE_PATH.exists():
            errors.append(f"Base path does not exist: {cls.BASE_PATH}")

        if not cls.DATA_PATH.exists():
            errors.append(f"Data path does not exist: {cls.DATA_PATH}")

        if not cls.SDE_PATH.exists():
            errors.append(f"SDE path does not exist: {cls.SDE_PATH}")

        return errors

    @classmethod
    def get_sde_file_path(cls, filename: str) -> Path:
        """Get the full path to an SDE JSONL file.

        Args:
            filename: Name of the JSONL file (e.g., 'types.jsonl')

        Returns:
            Full path to the file

        """
        return cls.SDE_PATH / filename

    @classmethod
    def print_config(cls) -> None:
        """Print current configuration for debugging."""
        print("=" * 60)
        print("EVE Means of Profit - Configuration")
        print("=" * 60)
        print(f"BASE_PATH: {cls.BASE_PATH}")
        print(f"DATA_PATH: {cls.DATA_PATH}")
        print(f"SDE_PATH: {cls.SDE_PATH}")
        print(f"LOG_LEVEL: {cls.LOG_LEVEL}")
        print(f"ENABLE_CACHE: {cls.ENABLE_CACHE}")
        print(f"CACHE_ALL_ON_STARTUP: {cls.CACHE_ALL_ON_STARTUP}")
        print(f"Frozen (PyInstaller): {getattr(sys, 'frozen', False)}")

        # Validation
        errors = cls.validate_paths()
        if errors:
            print("\nPath Validation Errors:")
            for error in errors:
                print(f"  ❌ {error}")
        else:
            print("\nAll paths validated successfully")
        print("=" * 60)


# Convenience aliases
BASE_PATH = Config.BASE_PATH
DATA_PATH = Config.DATA_PATH
SDE_PATH = Config.SDE_PATH
