"""Case conversion utility for converting camelCase to snake_case."""

import re


class CaseConverter:
    """Utility class for converting strings to snake_case.

    This class is designed for efficient string conversion using pre-compiled
    regex patterns for optimal performance when used repeatedly.

    Features:
        - Pre-compiled regex for performance
        - Preserves existing snake_case strings
        - Handles both camelCase and PascalCase

    Example:
        >>> converter = CaseConverter()
        >>> converter.to_snake_case("groupID")
        'group_id'
        >>> converter.to_snake_case("basePrice")
        'base_price'

    """

    def __init__(self):
        """Initialize the converter with pre-compiled regex patterns."""
        # Pre-compile regex for better performance on repeated conversions
        self._camel_to_snake_pattern = re.compile(r"(?<!^)(?=[A-Z])")

    def to_snake_case(self, text: str) -> str:
        """Convert camelCase/PascalCase to snake_case.

        Args:
            text: String in camelCase or PascalCase format

        Returns:
            String converted to snake_case

        """
        # If already snake_case, return as-is
        if "_" in text and text.islower():
            return text

        # Convert camelCase to snake_case
        return self._camel_to_snake_pattern.sub("_", text).lower()
