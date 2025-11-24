"""Framework-agnostic industry application service."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from data.repositories import Repository, industry_jobs
from models.eve import EveIndustryJob

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)


class IndustryService:
    """Business logic for industry job management."""

    def __init__(self, esi_client: ESIClient, repository: Repository):
        self._esi_client = esi_client
        self._repo = repository

    async def sync_jobs(self, character_id: int, include_completed: bool = False):
        jobs = await self._esi_client.industry.get_jobs(
            character_id,
            include_completed=include_completed,
            use_cache=True,
            bypass_cache=False,
        )
        count = await industry_jobs.save_jobs(self._repo, character_id, jobs)
        logger.info("Synced %d industry jobs for %d", count, character_id)

    async def get_active_jobs(self, character_id: int) -> list[EveIndustryJob]:
        return await industry_jobs.get_active_jobs(self._repo, character_id)

    async def get_jobs_by_activity(
        self, character_id: int, activity_id: int
    ) -> list[EveIndustryJob]:
        return await industry_jobs.get_jobs_by_activity(
            self._repo, character_id, activity_id
        )

    async def get_job_history(
        self, character_id: int, days: int = 30
    ) -> list[EveIndustryJob]:
        return await industry_jobs.get_job_history(self._repo, character_id, days)
