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
    ) -> tuple[list[EveCorporationProject], dict]:
        """
        Get corporation projects (all pages combined).

        Args:
            corporation_id: Corporation ID
            character_id: Optional character ID for authentication
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            Tuple of (list of validated EveProject models, response headers from first page)

        Note:
            This endpoint uses cursor-based pagination.
        """
        owner_id = character_id if character_id and self._client.auth else None
        path = f"/corporations/{corporation_id}/projects"
        # Use the base host without the '/latest' prefix and NO trailing slash
        full_url = f"https://esi.evetech.net/corporations/{corporation_id}/projects"

        # Collect all pages
        all_projects = []
        # Manually fetch first page to get headers
        first_data, first_headers = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=owner_id,
            full_url=full_url,
        )
        # Handle first page data
        if isinstance(first_data, list):
            all_projects.extend(first_data)
        elif isinstance(first_data, dict):
            if "items" in first_data:
                all_projects.extend(first_data["items"])
            elif "project_id" in first_data:
                all_projects.append(first_data)
        # Use paginated_request for additional pages (if any)
        async for page_data in self._client.paginated_request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=owner_id,
            full_url=full_url,
        ):
            if isinstance(page_data, list):
                all_projects.extend(page_data)
            elif isinstance(page_data, dict):
                if "items" in page_data:
                    all_projects.extend(page_data["items"])
                elif "project_id" in page_data:
                    all_projects.append(page_data)
        logger.info(
            "Retrieved %d projects for corporation %d",
            len(all_projects),
            corporation_id,
        )
        validated = (
            [EveCorporationProject.model_validate(project) for project in all_projects]
            if all_projects
            else []
        )
        return validated, first_headers
