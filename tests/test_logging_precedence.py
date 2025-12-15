"""Tests for logging level precedence (REQ-001, TEST-001).

Tests verify deterministic log level resolution order:
1. CLI/explicit parameter
2. APP_LOG_LEVEL environment variable
3. User preferences (settings_manager)
4. Config defaults
"""

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest

from src.utils.config import get_config
from src.utils.logging_setup import setup_logging
from src.utils.settings_manager import SettingsManager, reset_settings_manager


@pytest.fixture
def temp_settings_dir():
    """Create temporary directory for settings files."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_settings_manager(temp_settings_dir):
    """Create a mock settings manager with controlled log level."""
    reset_settings_manager()

    # Patch the settings file path
    with patch("src.utils.settings_manager.get_config") as mock_config:
        mock_app_config = Mock()
        mock_app_config.user_settings_file = temp_settings_dir / "user_settings.json"
        mock_app_config.user_data_dir = temp_settings_dir
        mock_config.return_value.app = mock_app_config

        manager = SettingsManager()
        yield manager

    reset_settings_manager()


def test_logging_precedence_explicit_parameter(
    temp_settings_dir, mock_settings_manager
):
    """Test that explicit log_level parameter has highest priority."""
    # Set user preference to WARNING
    mock_settings_manager.set_logging_level("WARNING")

    # Set env var to INFO
    os.environ["APP_LOG_LEVEL"] = "INFO"

    try:
        # Call setup_logging with explicit DEBUG level
        setup_logging(
            settings_manager=mock_settings_manager,
            log_level="DEBUG",
            user_data_dir=temp_settings_dir,
        )

        # Verify root logger is set to DEBUG (explicit param wins)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG
    finally:
        # Clean up
        del os.environ["APP_LOG_LEVEL"]


def test_logging_precedence_environment_variable(
    temp_settings_dir, mock_settings_manager
):
    """Test that APP_LOG_LEVEL env var takes priority over user prefs."""
    # Set user preference to WARNING
    mock_settings_manager.set_logging_level("WARNING")

    # Set env var to INFO
    os.environ["APP_LOG_LEVEL"] = "INFO"

    try:
        # Call setup_logging without explicit level
        setup_logging(
            settings_manager=mock_settings_manager,
            log_level=None,
            user_data_dir=temp_settings_dir,
        )

        # Verify root logger is set to INFO (env var wins over user prefs)
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
    finally:
        # Clean up
        del os.environ["APP_LOG_LEVEL"]


def test_logging_precedence_user_preferences(temp_settings_dir, mock_settings_manager):
    """Test that user preferences are used when no explicit or env override."""
    # Set user preference to ERROR
    mock_settings_manager.set_logging_level("ERROR")

    # Ensure no env var
    if "APP_LOG_LEVEL" in os.environ:
        del os.environ["APP_LOG_LEVEL"]

    # Call setup_logging without explicit level
    setup_logging(
        settings_manager=mock_settings_manager,
        log_level=None,
        user_data_dir=temp_settings_dir,
    )

    # Verify root logger is set to ERROR (user prefs used)
    root_logger = logging.getLogger()
    assert root_logger.level == logging.ERROR


def test_logging_precedence_config_defaults(temp_settings_dir):
    """Test that config defaults are used when no other source is available."""
    # Ensure no env var
    if "APP_LOG_LEVEL" in os.environ:
        del os.environ["APP_LOG_LEVEL"]

    # Call setup_logging without settings_manager or explicit level
    setup_logging(
        settings_manager=None,
        log_level=None,
        user_data_dir=temp_settings_dir,
    )

    # Verify root logger uses config default (WARNING)
    config = get_config()
    expected_level = getattr(logging, config.app.log_level.upper())
    root_logger = logging.getLogger()
    assert root_logger.level == expected_level


def test_logging_precedence_all_combinations(temp_settings_dir, mock_settings_manager):
    """Test comprehensive combinations to verify precedence order."""
    test_cases = [
        # (explicit, env, user_pref, expected)
        ("DEBUG", "INFO", "WARNING", logging.DEBUG),  # Explicit wins
        (None, "INFO", "WARNING", logging.INFO),  # Env wins over user pref
        (None, None, "ERROR", logging.ERROR),  # User pref used
    ]

    for explicit, env, user_pref, expected in test_cases:
        # Reset logger
        root_logger = logging.getLogger()
        root_logger.handlers.clear()

        # Set user preference
        if user_pref:
            mock_settings_manager.set_logging_level(user_pref)

        # Set/unset env var
        if env:
            os.environ["APP_LOG_LEVEL"] = env
        elif "APP_LOG_LEVEL" in os.environ:
            del os.environ["APP_LOG_LEVEL"]

        # Call setup_logging
        setup_logging(
            settings_manager=mock_settings_manager,
            log_level=explicit,
            user_data_dir=temp_settings_dir,
        )

        # Verify
        assert root_logger.level == expected, (
            f"Failed for (explicit={explicit}, env={env}, user_pref={user_pref}): "
            f"expected {expected}, got {root_logger.level}"
        )

    # Clean up
    if "APP_LOG_LEVEL" in os.environ:
        del os.environ["APP_LOG_LEVEL"]


def test_logging_level_case_insensitivity(temp_settings_dir):
    """Test that log level strings are case-insensitive."""
    # Test lowercase
    setup_logging(
        settings_manager=None,
        log_level="debug",
        user_data_dir=temp_settings_dir,
    )
    assert logging.getLogger().level == logging.DEBUG

    # Test uppercase
    logging.getLogger().handlers.clear()
    setup_logging(
        settings_manager=None,
        log_level="DEBUG",
        user_data_dir=temp_settings_dir,
    )
    assert logging.getLogger().level == logging.DEBUG

    # Test mixed case
    logging.getLogger().handlers.clear()
    setup_logging(
        settings_manager=None,
        log_level="DeBuG",
        user_data_dir=temp_settings_dir,
    )
    assert logging.getLogger().level == logging.DEBUG


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
