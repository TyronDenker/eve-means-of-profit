"""Contracts-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveContract, EveContractItem

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class ContractsEndpoints:
    """Handles all contracts-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        contracts = await client.contracts.get_contracts(character_id)
        items = await client.contracts.get_items(character_id, contract_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize contracts endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_contracts(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> tuple[list[EveContract], dict]:
        """Get contracts for a character (all pages combined).

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            tuple of (contracts, headers)

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/contracts/"

        all_contracts: list[dict] = []
        first_headers: dict | None = None

        # Always fetch first page directly to get headers (for cache expiry)
        first_page_data, first_headers = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
            params={"page": 1},
        )
        if isinstance(first_page_data, list):
            all_contracts.extend(first_page_data)

        # Get total pages from headers
        x_pages = first_headers.get("x-pages", "1")
        try:
            total_pages = int(x_pages)
        except (ValueError, TypeError):
            total_pages = 1

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            page_data, _ = await self._client.request(
                "GET",
                path,
                use_cache=(use_cache and not bypass_cache),
                owner_id=character_id,
                params={"page": page},
            )
            if isinstance(page_data, list):
                all_contracts.extend(page_data)

        logger.debug(
            "Retrieved %d contracts for character %d",
            len(all_contracts),
            character_id,
        )
        validated = [EveContract.model_validate(contract) for contract in all_contracts]
        return validated, first_headers or {}

    async def get_items(
        self,
        character_id: int,
        contract_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> list[EveContractItem]:
        """Get items in a specific contract.

        Args:
            character_id: Character ID
            contract_id: Contract ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveContractItem models

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/contracts/{contract_id}/items/"

        data, _ = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug(
            "Retrieved %d items for contract %d",
            len(data) if isinstance(data, list) else 0,
            contract_id,
        )
        if isinstance(data, list):
            # Validate items and set contract_id (not provided by ESI)
            items = []
            for item in data:
                validated = EveContractItem.model_validate(item)
                validated.contract_id = contract_id
                items.append(validated)
            return items
        return []
