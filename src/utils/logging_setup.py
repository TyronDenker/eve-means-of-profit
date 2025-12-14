"""Logging configuration with file rotation support.

Provides centralized logging setup with optional file output and rotation.
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from utils.settings_manager import SettingsManager


def setup_logging(
    settings_manager: SettingsManager | None = None,
    log_level: str | None = None,
    user_data_dir: Path | None = None,
) -> None:
    """Configure application logging with file output and rotation.

    Args:
        settings_manager: Optional settings manager for logging preferences.
        log_level: Logging level override (defaults to settings or INFO).
        user_data_dir: Directory for log files (defaults to config user_data_dir).
    """
    from utils.config import get_config

    config = get_config()

    # Determine log level
    if log_level is None:
        if settings_manager:
            log_level = settings_manager.get_logging_level()
        else:
            log_level = config.app.log_level

    # Convert string to logging level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler (always present)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # File handler (if enabled in settings)
    save_to_file = True
    if settings_manager:
        save_to_file = settings_manager.get_logging_save_to_file()

    if save_to_file:
        # Determine log directory
        if user_data_dir is None:
            user_data_dir = config.app.user_data_dir

        log_dir = user_data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create rotating file handler
        log_file = log_dir / f"emop_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.log"

        # Use rotating handler (10 MB max size, keep last N backups)
        retention_count = 7
        if settings_manager:
            retention_count = settings_manager.get_logging_retention_count()

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=retention_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Clean up old log files
        _cleanup_old_logs(log_dir, retention_count)

        logging.info(f"Logging to file: {log_file}")

    logging.info(f"Logging configured with level: {log_level}")


def _cleanup_old_logs(log_dir: Path, keep_count: int) -> None:
    """Remove old log files, keeping only the most recent ones.

    Args:
        log_dir: Directory containing log files.
        keep_count: Number of most recent log files to keep.
    """
    try:
        log_files = sorted(
            log_dir.glob("emop_*.log*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        # Delete files beyond keep_count
        for log_file in log_files[keep_count:]:
            try:
                log_file.unlink()
                logging.debug(f"Deleted old log file: {log_file}")
            except Exception as e:
                logging.warning(f"Failed to delete old log file {log_file}: {e}")
    except Exception as e:
        logging.warning(f"Failed to cleanup old log files: {e}")
