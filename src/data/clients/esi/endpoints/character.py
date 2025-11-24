"""Character-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class CharacterEndpoints:
    """Handles all character-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize character endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client
