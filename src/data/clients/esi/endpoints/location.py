"""Location-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveLocation

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class LocationEndpoints:
    """Handles all location-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        location: EveLocation = await client.location.get_character_location(
            character_id
        )
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize location endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_character_location(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> tuple[EveLocation, dict]:
        """
        Get a character's current location.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            Tuple of (validated EveLocation model, response headers)

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/location/"
        data, headers = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug("Retrieved location for character %d", character_id)
        return EveLocation.model_validate(data), headers
