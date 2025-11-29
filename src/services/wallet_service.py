"""Framework-agnostic wallet application service."""

from __future__ import annotations

import logging
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
