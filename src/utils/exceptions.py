"""Custom exception hierarchy for EVE Means of Profit.

Provides structured exception classes for different error scenarios.
"""

from __future__ import annotations


class EMoPError(Exception):
    """Base exception for all EVE Means of Profit errors."""

    pass


class ConfigurationError(EMoPError):
    """Exception raised for configuration-related errors."""

    pass


class DataProviderError(EMoPError):
    """Base exception for data provider errors."""

    pass


class SDEError(DataProviderError):
    """Exception raised for SDE-related errors."""

    pass


class SDEDownloadError(SDEError):
    """Exception raised when SDE download fails."""

    pass


class SDEParseError(SDEError):
    """Exception raised when SDE parsing fails."""

    pass


class ESIError(DataProviderError):
    """Base exception for ESI API errors."""

    pass


class ESIRateLimitError(ESIError):
    """Exception raised when ESI rate limit is hit (429)."""

    pass


class ESIServerError(ESIError):
    """Exception raised for ESI server errors (5xx)."""

    pass


class ServiceError(EMoPError):
    """Base exception for service layer errors."""

    pass


class RepositoryError(EMoPError):
    """Base exception for repository/database errors."""

    pass
