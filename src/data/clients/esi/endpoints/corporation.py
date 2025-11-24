"""Corporation-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveCorporationProject

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class CorporationEndpoints:
    """Handles all corporation-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        projects: list[EveProject] = await client.corporations.get_projects(corp_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize corporation endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_projects(
        self,
        corporation_id: int,
        character_id: int | None = None,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> list[EveCorporationProject]:
        """Get corporation projects (all pages combined).

        Args:
            corporation_id: Corporation ID
            character_id: Optional character ID for authentication
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveProject models

        Note:
            This endpoint uses cursor-based pagination.
        """
        owner_id = character_id if character_id and self._client.auth else None
        path = f"/corporations/{corporation_id}/projects"
        # Use the base host without the '/latest' prefix and NO trailing slash
        full_url = f"https://esi.evetech.net/corporations/{corporation_id}/projects"

        # Collect all pages
        all_projects = []
        async for page_data in self._client.paginated_request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=owner_id,
            full_url=full_url,
        ):
            # Cursor pagination may return:
            # 1. A list of projects
            # 2. A dict with 'cursor' and potentially other keys with project data
            # 3. Empty response (cursor only, no projects)

            if isinstance(page_data, list):
                # Direct list of projects
                all_projects.extend(page_data)
            elif isinstance(page_data, dict):
                # Check for 'items' key (some cursor endpoints)
                if "items" in page_data:
                    all_projects.extend(page_data["items"])
                # Check if this looks like a project object (has required fields)
                elif "project_id" in page_data:
                    all_projects.append(page_data)
                # Otherwise it's likely just cursor metadata (no actual projects)
                # Skip it silently

        logger.info(
            "Retrieved %d projects for corporation %d",
            len(all_projects),
            corporation_id,
        )
        # Only validate if we have data to validate
        if all_projects:
            return [
                EveCorporationProject.model_validate(project)
                for project in all_projects
            ]
        return []
