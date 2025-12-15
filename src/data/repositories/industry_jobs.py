"""Repository functions for industry jobs.

This module provides functions for storing and querying industry job
information for characters.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from models.eve import EveIndustryJob

if TYPE_CHECKING:
    from .repository import Repository

logger = logging.getLogger(__name__)


async def save_jobs(
    repo: Repository, character_id: int, jobs: list[EveIndustryJob]
) -> int:
    """Save industry jobs for a character.

    Uses INSERT OR REPLACE to handle incremental appending without creating duplicates.
    Since job_id is unique, existing jobs are updated with their latest status.
    This allows safe repeated syncing of overlapping job history.

    Args:
        repo: Repository instance
        character_id: Character ID
        jobs: List of jobs to save

    Returns:
        Number of jobs saved (new + updated)
    """
    if not jobs:
        return 0

    # Use INSERT OR REPLACE to handle updates
    # job_id is PRIMARY KEY, so duplicates are automatically replaced with latest data
    sql = """
    INSERT OR REPLACE INTO industry_jobs (
        job_id, character_id, installer_id, facility_id, activity_id, blueprint_id,
        blueprint_type_id, blueprint_location_id, output_location_id, runs, cost,
        licensed_runs, probability, product_type_id, status, duration, start_date,
        end_date, pause_date, completed_date, completed_character_id, successful_runs,
        last_updated
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    now = datetime.now(UTC)
    params = [
        (
            job.job_id,
            character_id,
            job.installer_id,
            job.facility_id,
            job.activity_id,
            job.blueprint_id,
            job.blueprint_type_id,
            job.blueprint_location_id,
            job.output_location_id,
            job.runs,
            job.cost,
            job.licensed_runs,
            job.probability,
            job.product_type_id,
            job.status,
            job.duration,
            job.start_date,
            job.end_date,
            job.pause_date,
            job.completed_date,
            job.completed_character_id,
            job.successful_runs,
            now,
        )
        for job in jobs
    ]

    await repo.executemany(sql, params)
    logger.info("Saved %d industry jobs for character %d", len(jobs), character_id)
    return len(jobs)


async def get_active_jobs(repo: Repository, character_id: int) -> list[EveIndustryJob]:
    """Get active industry jobs for a character.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        List of active jobs
    """
    sql = """
    SELECT job_id, installer_id, facility_id, activity_id, blueprint_id,
           blueprint_type_id, blueprint_location_id, output_location_id, runs, cost,
           licensed_runs, probability, product_type_id, status, duration, start_date,
           end_date, pause_date, completed_date, completed_character_id, successful_runs
    FROM industry_jobs
    WHERE character_id = ? AND status IN ('active', 'paused')
    ORDER BY end_date ASC
    """

    rows = await repo.fetchall(sql, (character_id,))
    return [
        EveIndustryJob(
            job_id=row["job_id"],
            installer_id=row["installer_id"],
            facility_id=row["facility_id"],
            station_id=row["facility_id"],  # Use facility_id as station_id
            activity_id=row["activity_id"],
            blueprint_id=row["blueprint_id"],
            blueprint_type_id=row["blueprint_type_id"],
            blueprint_location_id=row["blueprint_location_id"],
            output_location_id=row["output_location_id"],
            runs=row["runs"],
            cost=row["cost"],
            licensed_runs=row["licensed_runs"],
            probability=row["probability"],
            product_type_id=row["product_type_id"],
            status=row["status"],
            duration=row["duration"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]),
            pause_date=datetime.fromisoformat(row["pause_date"])
            if row["pause_date"]
            else None,
            completed_date=datetime.fromisoformat(row["completed_date"])
            if row["completed_date"]
            else None,
            completed_character_id=row["completed_character_id"],
            successful_runs=row["successful_runs"],
        )
        for row in rows
    ]


async def get_jobs_by_activity(
    repo: Repository, character_id: int, activity_id: int
) -> list[EveIndustryJob]:
    """Get industry jobs for a specific activity type.

    Args:
        repo: Repository instance
        character_id: Character ID
        activity_id: Activity type (1=manufacturing, 3=research_time, etc.)

    Returns:
        List of jobs for the specified activity
    """
    sql = """
    SELECT job_id, installer_id, facility_id, activity_id, blueprint_id,
           blueprint_type_id, blueprint_location_id, output_location_id, runs, cost,
           licensed_runs, probability, product_type_id, status, duration, start_date,
           end_date, pause_date, completed_date, completed_character_id, successful_runs
    FROM industry_jobs
    WHERE character_id = ? AND activity_id = ?
    ORDER BY start_date DESC
    """

    rows = await repo.fetchall(sql, (character_id, activity_id))
    return [
        EveIndustryJob(
            job_id=row["job_id"],
            installer_id=row["installer_id"],
            facility_id=row["facility_id"],
            station_id=row["facility_id"],
            activity_id=row["activity_id"],
            blueprint_id=row["blueprint_id"],
            blueprint_type_id=row["blueprint_type_id"],
            blueprint_location_id=row["blueprint_location_id"],
            output_location_id=row["output_location_id"],
            runs=row["runs"],
            cost=row["cost"],
            licensed_runs=row["licensed_runs"],
            probability=row["probability"],
            product_type_id=row["product_type_id"],
            status=row["status"],
            duration=row["duration"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]),
            pause_date=datetime.fromisoformat(row["pause_date"])
            if row["pause_date"]
            else None,
            completed_date=datetime.fromisoformat(row["completed_date"])
            if row["completed_date"]
            else None,
            completed_character_id=row["completed_character_id"],
            successful_runs=row["successful_runs"],
        )
        for row in rows
    ]


async def get_job_history(
    repo: Repository, character_id: int, days: int = 30
) -> list[EveIndustryJob]:
    """Get industry job history for a character.

    Args:
        repo: Repository instance
        character_id: Character ID
        days: Number of days to look back

    Returns:
        List of jobs from the specified period
    """
    sql = """
    SELECT job_id, installer_id, facility_id, activity_id, blueprint_id,
           blueprint_type_id, blueprint_location_id, output_location_id, runs, cost,
           licensed_runs, probability, product_type_id, status, duration, start_date,
           end_date, pause_date, completed_date, completed_character_id, successful_runs
    FROM industry_jobs
    WHERE character_id = ? AND start_date >= datetime('now', '-' || ? || ' days')
    ORDER BY start_date DESC
    """

    rows = await repo.fetchall(sql, (character_id, days))
    return [
        EveIndustryJob(
            job_id=row["job_id"],
            installer_id=row["installer_id"],
            facility_id=row["facility_id"],
            station_id=row["facility_id"],
            activity_id=row["activity_id"],
            blueprint_id=row["blueprint_id"],
            blueprint_type_id=row["blueprint_type_id"],
            blueprint_location_id=row["blueprint_location_id"],
            output_location_id=row["output_location_id"],
            runs=row["runs"],
            cost=row["cost"],
            licensed_runs=row["licensed_runs"],
            probability=row["probability"],
            product_type_id=row["product_type_id"],
            status=row["status"],
            duration=row["duration"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]),
            pause_date=datetime.fromisoformat(row["pause_date"])
            if row["pause_date"]
            else None,
            completed_date=datetime.fromisoformat(row["completed_date"])
            if row["completed_date"]
            else None,
            completed_character_id=row["completed_character_id"],
            successful_runs=row["successful_runs"],
        )
        for row in rows
    ]


async def get_jobs_by_status(
    repo: Repository, character_id: int, status: str
) -> list[EveIndustryJob]:
    """Get industry jobs for a specific status.

    Args:
        repo: Repository instance
        character_id: Character ID
        status: Job status (active, paused, ready, delivered, cancelled)

    Returns:
        List of jobs with the specified status
    """
    sql = """
    SELECT job_id, installer_id, facility_id, activity_id, blueprint_id,
           blueprint_type_id, blueprint_location_id, output_location_id, runs, cost,
           licensed_runs, probability, product_type_id, status, duration, start_date,
           end_date, pause_date, completed_date, completed_character_id, successful_runs
    FROM industry_jobs
    WHERE character_id = ? AND status = ?
    ORDER BY end_date ASC
    """

    rows = await repo.fetchall(sql, (character_id, status))
    return [
        EveIndustryJob(
            job_id=row["job_id"],
            installer_id=row["installer_id"],
            facility_id=row["facility_id"],
            station_id=row["facility_id"],
            activity_id=row["activity_id"],
            blueprint_id=row["blueprint_id"],
            blueprint_type_id=row["blueprint_type_id"],
            blueprint_location_id=row["blueprint_location_id"],
            output_location_id=row["output_location_id"],
            runs=row["runs"],
            cost=row["cost"],
            licensed_runs=row["licensed_runs"],
            probability=row["probability"],
            product_type_id=row["product_type_id"],
            status=row["status"],
            duration=row["duration"],
            start_date=datetime.fromisoformat(row["start_date"]),
            end_date=datetime.fromisoformat(row["end_date"]),
            pause_date=datetime.fromisoformat(row["pause_date"])
            if row["pause_date"]
            else None,
            completed_date=datetime.fromisoformat(row["completed_date"])
            if row["completed_date"]
            else None,
            completed_character_id=row["completed_character_id"],
            successful_runs=row["successful_runs"],
        )
        for row in rows
    ]


async def count_active_jobs_by_activity(
    repo: Repository, character_id: int
) -> dict[int, int]:
    """Get count of active jobs per activity type.

    Args:
        repo: Repository instance
        character_id: Character ID

    Returns:
        Dict mapping activity_id to count of active jobs
    """
    sql = """
    SELECT activity_id, COUNT(*) as count
    FROM industry_jobs
    WHERE character_id = ? AND status IN ('active', 'paused')
    GROUP BY activity_id
    """

    rows = await repo.fetchall(sql, (character_id,))
    return {row["activity_id"]: row["count"] for row in rows}


__all__ = [
    "count_active_jobs_by_activity",
    "get_active_jobs",
    "get_job_history",
    "get_jobs_by_activity",
    "get_jobs_by_status",
    "save_jobs",
]
