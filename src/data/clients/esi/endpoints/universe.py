"""Structure-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveStructure

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class UniverseEndpoints:
    """Handles all universe-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        structure_info: EveStructure = await client.universe.get_structure_info(
            structure_id=1234567890, character_id=123456789
        )
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize structure endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_structure_info(
        self,
        structure_id: int,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> EveStructure:
        """Get information about a structure.

        This endpoint requires authentication and the character must be on
        the structure's ACL (access control list) to view its information.

        Args:
            structure_id: Structure ID to get information for
            character_id: Character ID for authentication
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            Validated EveStructure model with structure information

        Raises:
            ValueError: If character not authenticated
            HTTPError: If character doesn't have access to structure info
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/universe/structures/{structure_id}/"

        data, _ = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug("Retrieved structure info for structure %d", structure_id)
        return EveStructure.model_validate(data)
