"""Industry-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveIndustryJob

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class IndustryEndpoints:
    """Handles all industry-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        jobs = await client.industry.get_jobs(character_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize industry endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_jobs(
        self,
        character_id: int,
        include_completed: bool = False,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> list[EveIndustryJob]:
        """Get industry jobs for a character.

        Args:
            character_id: Character ID
            include_completed: Include completed jobs
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveIndustryJob models

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/industry/jobs/"

        params = {}
        if include_completed:
            params["include_completed"] = "true"

        data, _ = await self._client.request(
            "GET",
            path,
            params=params,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug(
            "Retrieved %d industry jobs for character %d",
            len(data) if isinstance(data, list) else 0,
            character_id,
        )
        return (
            [EveIndustryJob.model_validate(job) for job in data]
            if isinstance(data, list)
            else []
        )
