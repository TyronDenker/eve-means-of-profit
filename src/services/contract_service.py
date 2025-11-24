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
        """Sync contracts and return (count, contracts)."""
        contract_list = await self._esi_client.contracts.get_contracts(
            character_id, use_cache=True, bypass_cache=False
        )
        count = await contracts.save_contracts(self._repo, character_id, contract_list)
        logger.info("Synced %d contracts for %d", count, character_id)

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
