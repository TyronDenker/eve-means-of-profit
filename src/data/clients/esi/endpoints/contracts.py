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
    ) -> list[EveContract]:
        """Get contracts for a character (all pages combined).

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveContract models

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/contracts/"

        # Contracts can be paginated
        all_contracts: list[dict] = []
        async for page_data in self._client.paginated_request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        ):
            if isinstance(page_data, list):
                all_contracts.extend(page_data)

        logger.debug(
            "Retrieved %d contracts for character %d",
            len(all_contracts),
            character_id,
        )
        return [EveContract.model_validate(contract) for contract in all_contracts]

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
        return (
            [EveContractItem.model_validate(item) for item in data]
            if isinstance(data, list)
            else []
        )
