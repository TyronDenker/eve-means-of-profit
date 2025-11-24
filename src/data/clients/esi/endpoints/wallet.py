"""Wallet-related ESI endpoints."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.eve import EveJournalEntry, EveTransaction

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class WalletEndpoints:
    """Handles all wallet-related ESI endpoints.

    Example:
        ```python
        client = ESIClient(client_id="...")
        transactions = await client.wallet.get_transactions(character_id)
        journal = await client.wallet.get_journal(character_id)
        ```
    """

    def __init__(self, client: ESIClient):
        """Initialize wallet endpoints with ESI client.

        Args:
            client: ESI client instance for HTTP operations
        """
        self._client = client

    async def get_transactions(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> list[EveTransaction]:
        """Get wallet transactions for a character.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveTransaction models

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/wallet/transactions/"

        data, _ = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )

        logger.debug(
            "Retrieved %d transactions for character %d",
            len(data) if isinstance(data, list) else 0,
            character_id,
        )
        return (
            [EveTransaction.model_validate(tx) for tx in data]
            if isinstance(data, list)
            else []
        )

    async def get_journal(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> list[EveJournalEntry]:
        """Get wallet journal for a character.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            List of validated EveJournalEntry models

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/wallet/journal/"

        # Wallet journal can be paginated
        all_entries: list[dict] = []
        async for page_data in self._client.paginated_request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        ):
            if isinstance(page_data, list):
                all_entries.extend(page_data)

        logger.debug(
            "Retrieved %d journal entries for character %d",
            len(all_entries),
            character_id,
        )
        return [EveJournalEntry.model_validate(entry) for entry in all_entries]
