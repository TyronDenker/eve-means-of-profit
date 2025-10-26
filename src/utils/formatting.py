"""Formatting utilities for EVE Online data display."""


def format_number(value: float | int | None, decimals: int = 0) -> str:
    """Format a number with thousand separators.

    Args:
        value: The number to format
        decimals: Number of decimal places to show

    Returns:
        Formatted string with commas as thousand separators

    """
    if value is None:
        return "N/A"

    if decimals > 0:
        return f"{value:,.{decimals}f}"
    return f"{int(value):,}"


def format_currency(value: float | None, include_isk: bool = True) -> str:
    """Format ISK currency values.

    Args:
        value: The ISK amount to format
        include_isk: Whether to append " ISK" suffix

    Returns:
        Formatted currency string

    """
    if value is None:
        return "N/A"

    formatted = format_number(value, decimals=2)
    if include_isk:
        return f"{formatted} ISK"
    return formatted


def format_time(seconds: int | None) -> str:
    """Format time in seconds to human-readable format.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string (e.g., "1h 30m 45s")

    """
    if seconds is None or seconds == 0:
        return "N/A"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts)


def format_volume(value: float | None) -> str:
    """Format volume in m³.

    Args:
        value: Volume in cubic meters

    Returns:
        Formatted volume string

    """
    if value is None:
        return "N/A"

    if value < 1:
        return f"{value:.4f} m³"
    elif value < 1000:
        return f"{value:.2f} m³"
    else:
        return f"{format_number(value, decimals=2)} m³"


def format_mass(value: float | None) -> str:
    """Format mass in kg.

    Args:
        value: Mass in kilograms

    Returns:
        Formatted mass string

    """
    if value is None:
        return "N/A"

    if value < 1:
        return f"{value:.4f} kg"
    elif value < 1000:
        return f"{value:.2f} kg"
    elif value < 1_000_000:
        # Convert to tons
        return f"{value / 1000:.2f} tons"
    else:
        return f"{format_number(value, decimals=2)} kg"
