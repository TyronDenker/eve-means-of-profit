"""Skills-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class SkillsEndpoints:
    """Handles all skills-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        skills = await client.skills.get_skills(character_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize skills endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_skills(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> tuple[dict, dict]:
        """Get character skills.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            Tuple of (skills data dict, response headers)

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/skills/"
        data, headers = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug(
            "Retrieved %d skills for character %d",
            len(data.get("skills", [])) if isinstance(data, dict) else 0,
            character_id,
        )
        return data, headers
