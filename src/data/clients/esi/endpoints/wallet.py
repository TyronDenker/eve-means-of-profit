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
    ) -> tuple[list[EveTransaction], dict]:
        """
        Get wallet transactions for a character.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            A tuple containing a list of validated EveTransaction models and the response headers.

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )
        path = f"/characters/{character_id}/wallet/transactions/"
        data, headers = await self._client.request(
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
        validated = (
            [EveTransaction.model_validate(tx) for tx in data]
            if isinstance(data, list)
            else []
        )
        return validated, headers

    async def get_journal(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> tuple[list[EveJournalEntry], dict]:
        """
        Get wallet journal for a character (all pages combined).

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            A tuple containing a list of validated EveJournalEntry models and the response headers from the first page.

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )

        path = f"/characters/{character_id}/wallet/journal/"

        all_entries: list[dict] = []
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
            all_entries.extend(first_page_data)

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
                all_entries.extend(page_data)

        logger.debug(
            "Retrieved %d journal entries for character %d",
            len(all_entries),
            character_id,
        )

        # Return the verified model with id renamed to journal_id
        validated = [
            EveJournalEntry.model_validate({**entry, "journal_id": entry.pop("id")})
            for entry in all_entries
        ]

        return validated, first_headers or {}

    async def get_balance(
        self,
        character_id: int,
        use_cache: bool = True,
        bypass_cache: bool = False,
    ) -> tuple[float, dict]:
        """
        Get current wallet balance for a character.

        Args:
            character_id: Character ID
            use_cache: Whether to use cache
            bypass_cache: Force fresh fetch

        Returns:
            A tuple containing the current wallet balance in ISK and the response headers.

        Raises:
            ValueError: If character not authenticated
        """
        if not self._client.auth:
            raise ValueError(
                "Authentication required. Initialize ESIClient with client_id "
                "and call authenticate_character() first."
            )
        path = f"/characters/{character_id}/wallet/"
        data, headers = await self._client.request(
            "GET",
            path,
            use_cache=(use_cache and not bypass_cache),
            owner_id=character_id,
        )
        balance = float(data) if data else 0.0
        logger.debug(
            "Retrieved wallet balance %.2f ISK for character %d",
            balance,
            character_id,
        )
        return balance, headers
