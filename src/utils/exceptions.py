"""Custom exception hierarchy for EVE Means of Profit.

Provides structured exception classes for different error scenarios.
"""

from __future__ import annotations


class EMoPException(Exception):
    """Base exception for all EVE Means of Profit errors."""

    pass


class ConfigurationError(EMoPException):
    """Exception raised for configuration-related errors."""

    pass


class DataProviderError(EMoPException):
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


class ServiceError(EMoPException):
    """Base exception for service layer errors."""

    pass


class RepositoryError(EMoPException):
    """Base exception for repository/database errors."""

    pass
