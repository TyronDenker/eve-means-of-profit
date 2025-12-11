"""Framework-agnostic application service for contract operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from data.repositories import Repository, contracts
from models.eve import EveContract, EveContractItem

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class ContractService:
    """Business logic for contract management."""

    def __init__(self, esi_client: ESIClient, repository: Repository):
        self._esi_client = esi_client
        self._repo = repository

    async def sync_contracts(self, character_id: int):
        """Sync contracts and their items for a character.

        This will append/update contracts and also fetch and persist all contract items.
        """
        result = await self._esi_client.contracts.get_contracts(
            character_id, use_cache=True, bypass_cache=False
        )
        # Handle (validated, headers) tuple or just validated list
        if isinstance(result, tuple):
            contract_list, headers = result
        else:
            contract_list = result
            headers = {}
        count = await contracts.save_contracts(self._repo, character_id, contract_list)

        # Ensure contract items are saved as well
        saved_items = 0
        for c in contract_list:
            try:
                items = await self._esi_client.contracts.get_items(
                    character_id, c.contract_id, use_cache=True, bypass_cache=False
                )
                await contracts.save_contract_items(self._repo, c.contract_id, items)
                saved_items += len(items)
            except Exception:
                logger.debug(
                    "Failed to sync items for contract %d",
                    getattr(c, "contract_id", -1),
                    exc_info=True,
                )

        etag = headers.get("etag")
        expires = headers.get("expires")
        if etag or expires:
            logger.info(
                "Synced %d contracts (%d items) for %d (etag=%s expires=%s)",
                count,
                saved_items,
                character_id,
                etag,
                expires,
            )
        else:
            logger.info(
                "Synced %d contracts (%d items) for %d",
                count,
                saved_items,
                character_id,
            )

    async def sync_contract_items(self, character_id: int, contract_id: int):
        """Sync contract items and return (count, items)."""
        items = await self._esi_client.contracts.get_items(
            character_id, contract_id, use_cache=True, bypass_cache=False
        )
        count = await contracts.save_contract_items(self._repo, contract_id, items)
        logger.info(
            "Synced %d items for contract %d",
            count,
            contract_id,
        )

    async def get_contracts(self, character_id: int) -> list[EveContract]:
        return await contracts.get_contracts(self._repo, character_id)

    async def get_active_contracts(self, character_id: int) -> list[EveContract]:
        return await contracts.get_active_contracts(self._repo, character_id)

    async def get_contract_items(self, contract_id: int) -> list[EveContractItem]:
        return await contracts.get_contract_items(self._repo, contract_id)
