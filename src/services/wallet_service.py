"""Framework-agnostic wallet application service."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from data.repositories import Repository, journal, transactions
from models.eve import EveJournalEntry, EveTransaction

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class WalletService:
    """Business logic for wallet transaction and journal management."""

    def __init__(self, esi_client: ESIClient, repository: Repository):
        self._esi_client = esi_client
        self._repo = repository

    async def sync_transactions(self, character_id: int):
        """Sync wallet transactions"""
        result = await self._esi_client.wallet.get_transactions(
            character_id, use_cache=True, bypass_cache=False
        )
        if isinstance(result, tuple):
            txs, headers = result
        else:
            txs = result
            headers = {}
        count = await transactions.save_transactions(self._repo, character_id, txs)
        etag = headers.get("etag")
        expires = headers.get("expires")
        if etag or expires:
            logger.info(
                "Synced %d transactions for character %d (etag=%s expires=%s)",
                count,
                character_id,
                etag,
                expires,
            )
        else:
            logger.info("Synced %d transactions for character %d", count, character_id)

    async def sync_journal(self, character_id: int):
        """Sync wallet journal entries"""
        result = await self._esi_client.wallet.get_journal(
            character_id, use_cache=True, bypass_cache=False
        )
        # Handle (validated, headers) tuple or just validated list
        if isinstance(result, tuple):
            entries, headers = result
        else:
            entries = result
            headers = {}
        count = await journal.save_journal_entries(self._repo, character_id, entries)
        etag = headers.get("etag")
        expires = headers.get("expires")
        if etag or expires:
            logger.info(
                "Synced %d journal entries for character %d (etag=%s expires=%s)",
                count,
                character_id,
                etag,
                expires,
            )
        else:
            logger.info(
                "Synced %d journal entries for character %d", count, character_id
            )

    async def get_transaction_history(
        self, character_id: int, days: int = 30
    ) -> list[EveTransaction]:
        return await transactions.get_transactions(self._repo, character_id, limit=100)

    async def get_journal_history(
        self, character_id: int, days: int = 30
    ) -> list[EveJournalEntry]:
        return await journal.get_journal_entries(self._repo, character_id, limit=100)

    async def get_journal_by_date_range(
        self, character_id: int, start_date: datetime, end_date: datetime
    ) -> list[EveJournalEntry]:
        """Get journal entries within a date range.

        Args:
            character_id: Character ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of journal entries in the date range
        """
        return await journal.get_entries_by_date_range(
            self._repo, character_id, start_date, end_date
        )

    async def get_journal_by_types(
        self, character_id: int, ref_types: list[str]
    ) -> list[EveJournalEntry]:
        """Get journal entries of specified types.

        Args:
            character_id: Character ID
            ref_types: List of reference types to filter

        Returns:
            List of journal entries of the specified types
        """
        return await journal.get_entries_by_types(self._repo, character_id, ref_types)

    async def get_transactions_by_date_range(
        self, character_id: int, start_date: datetime, end_date: datetime
    ) -> list[EveTransaction]:
        """Get transactions within a date range.

        Args:
            character_id: Character ID
            start_date: Start date (inclusive)
            end_date: End date (inclusive)

        Returns:
            List of transactions in the date range
        """
        return await transactions.get_transactions_by_date_range(
            self._repo, character_id, start_date, end_date
        )

    async def get_transactions_by_type(
        self, character_id: int, type_id: int
    ) -> list[EveTransaction]:
        """Get all transactions for a specific item type.

        Args:
            character_id: Character ID
            type_id: Item type ID

        Returns:
            List of transactions for the type
        """
        return await transactions.get_transactions_by_type(
            self._repo, character_id, type_id
        )
