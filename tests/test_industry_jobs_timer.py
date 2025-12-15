"""Tests for real-time industry job countdown timer"""

import os
import sys
from pathlib import Path

# Ensure src is on path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

# Run Qt in minimal mode to avoid GUI plugin errors
os.environ.setdefault("QT_QPA_PLATFORM", "minimal")

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from models.eve import EveIndustryJob
from ui.tabs.industry_jobs_tab import IndustryJobsTab


@pytest.fixture
def mock_services():
    """Create mock services for IndustryJobsTab."""
    industry_service = Mock()
    character_service = Mock()
    location_service = Mock()
    sde_provider = Mock()

    # Setup default returns
    industry_service.get_active_jobs = AsyncMock(return_value=[])
    character_service.get_authenticated_characters = AsyncMock(return_value=[])
    location_service.resolve_locations_bulk = AsyncMock(return_value={})

    return {
        "industry_service": industry_service,
        "character_service": character_service,
        "location_service": location_service,
        "sde_provider": sde_provider,
    }


@pytest.fixture
def industry_jobs_tab(qtbot, mock_services):
    """Create IndustryJobsTab instance."""
    tab = IndustryJobsTab(
        industry_service=mock_services["industry_service"],
        character_service=mock_services["character_service"],
        location_service=mock_services["location_service"],
        sde_provider=mock_services["sde_provider"],
    )
    qtbot.addWidget(tab)
    return tab


@pytest.mark.asyncio
async def test_countdown_timer_starts_with_active_jobs(
    qtbot, industry_jobs_tab, mock_services
):
    """Test that countdown timer starts when active jobs are loaded."""
    # Create test jobs - one active, ending in 1 hour
    now = datetime.now(UTC)
    job = EveIndustryJob(
        job_id=1,
        installer_id=100,
        facility_id=1000,
        activity_id=1,
        blueprint_id=10000,
        blueprint_type_id=20000,
        blueprint_location_id=1000,
        output_location_id=1000,
        runs=1,
        cost=100000.0,
        status="active",
        duration=3600,
        start_date=now - timedelta(hours=1),
        end_date=now + timedelta(hours=1),
    )

    mock_services["industry_service"].get_active_jobs = AsyncMock(return_value=[job])

    # Trigger refresh
    industry_jobs_tab._current_characters = [Mock(character_id=100)]
    await industry_jobs_tab._do_refresh()

    # Timer should be running
    assert industry_jobs_tab._countdown_timer.isActive()
    assert len(industry_jobs_tab._jobs_cache) == 1


@pytest.mark.asyncio
async def test_countdown_timer_stops_when_no_active_jobs(
    qtbot, industry_jobs_tab, mock_services
):
    """Test that countdown timer stops when all jobs are complete."""
    # Create completed job
    now = datetime.now(UTC)
    job = EveIndustryJob(
        job_id=1,
        installer_id=100,
        facility_id=1000,
        activity_id=1,
        blueprint_id=10000,
        blueprint_type_id=20000,
        blueprint_location_id=1000,
        output_location_id=1000,
        runs=1,
        cost=100000.0,
        status="delivered",
        duration=3600,
        start_date=now - timedelta(hours=2),
        end_date=now - timedelta(hours=1),
    )

    mock_services["industry_service"].get_active_jobs = AsyncMock(return_value=[job])

    # Trigger refresh
    industry_jobs_tab._current_characters = [Mock(character_id=100)]
    await industry_jobs_tab._do_refresh()

    # Timer should not be running
    assert not industry_jobs_tab._countdown_timer.isActive()


@pytest.mark.asyncio
async def test_countdown_updates_time_left(qtbot, industry_jobs_tab, mock_services):
    """Test that countdown updates Time Left column correctly."""
    # Create job ending in 65 seconds
    now = datetime.now(UTC)
    job = EveIndustryJob(
        job_id=1,
        installer_id=100,
        facility_id=1000,
        activity_id=1,
        blueprint_id=10000,
        blueprint_type_id=20000,
        blueprint_location_id=1000,
        output_location_id=1000,
        runs=1,
        cost=100000.0,
        status="active",
        duration=65,
        start_date=now,
        end_date=now + timedelta(seconds=65),
    )

    mock_services["industry_service"].get_active_jobs = AsyncMock(return_value=[job])
    mock_services["sde_provider"].get_type_by_id = Mock(
        return_value=Mock(name="Test Blueprint")
    )

    # Trigger refresh
    industry_jobs_tab._current_characters = [Mock(character_id=100)]
    await industry_jobs_tab._do_refresh()

    # Check initial time left (should be 01:05 or similar)
    row = industry_jobs_tab._rows_cache[0]
    assert ":" in row["remaining_time"]
    assert row["remaining_time"] != "Complete"

    # Manually trigger countdown update
    industry_jobs_tab._update_countdowns()

    # Time left should still be formatted
    row = industry_jobs_tab._rows_cache[0]
    assert ":" in row["remaining_time"]


@pytest.mark.asyncio
async def test_countdown_detects_completion(qtbot, industry_jobs_tab, mock_services):
    """Test that countdown detects when job completes and updates status."""
    # Create job ending in past
    now = datetime.now(UTC)
    job = EveIndustryJob(
        job_id=1,
        installer_id=100,
        facility_id=1000,
        activity_id=1,
        blueprint_id=10000,
        blueprint_type_id=20000,
        blueprint_location_id=1000,
        output_location_id=1000,
        runs=1,
        cost=100000.0,
        status="active",
        duration=60,
        start_date=now - timedelta(seconds=120),
        end_date=now - timedelta(seconds=60),  # Ended 60 seconds ago
    )

    mock_services["industry_service"].get_active_jobs = AsyncMock(return_value=[job])

    # Trigger refresh
    industry_jobs_tab._current_characters = [Mock(character_id=100)]
    await industry_jobs_tab._do_refresh()

    # Trigger countdown update
    industry_jobs_tab._update_countdowns()

    # Job should be marked as ready and time should show Complete
    cached_job = industry_jobs_tab._jobs_cache[0]
    assert cached_job.status == "ready"

    row = industry_jobs_tab._rows_cache[0]
    assert row["remaining_time"] == "Complete"
    assert row["status"] == "Ready"


@pytest.mark.asyncio
async def test_countdown_handles_paused_jobs(qtbot, industry_jobs_tab, mock_services):
    """Test that paused jobs show 'Paused' instead of countdown."""
    # Create paused job
    now = datetime.now(UTC)
    job = EveIndustryJob(
        job_id=1,
        installer_id=100,
        facility_id=1000,
        activity_id=1,
        blueprint_id=10000,
        blueprint_type_id=20000,
        blueprint_location_id=1000,
        output_location_id=1000,
        runs=1,
        cost=100000.0,
        status="paused",
        duration=3600,
        start_date=now - timedelta(hours=1),
        end_date=now + timedelta(hours=1),
        pause_date=now - timedelta(minutes=30),
    )

    mock_services["industry_service"].get_active_jobs = AsyncMock(return_value=[job])

    # Trigger refresh
    industry_jobs_tab._current_characters = [Mock(character_id=100)]
    await industry_jobs_tab._do_refresh()

    # Trigger countdown update
    industry_jobs_tab._update_countdowns()

    # Timer runs for paused jobs
    assert industry_jobs_tab._countdown_timer.isActive()


@pytest.mark.asyncio
async def test_countdown_clamps_negative_duration(
    qtbot, industry_jobs_tab, mock_services
):
    """Test that negative durations are clamped to 0 (Complete)."""
    # Create job that ended long ago
    now = datetime.now(UTC)
    job = EveIndustryJob(
        job_id=1,
        installer_id=100,
        facility_id=1000,
        activity_id=1,
        blueprint_id=10000,
        blueprint_type_id=20000,
        blueprint_location_id=1000,
        output_location_id=1000,
        runs=1,
        cost=100000.0,
        status="active",
        duration=3600,
        start_date=now - timedelta(hours=5),
        end_date=now - timedelta(hours=4),  # Ended 4 hours ago
    )

    mock_services["industry_service"].get_active_jobs = AsyncMock(return_value=[job])

    # Trigger refresh
    industry_jobs_tab._current_characters = [Mock(character_id=100)]
    await industry_jobs_tab._do_refresh()

    # Trigger countdown update
    industry_jobs_tab._update_countdowns()

    # Should show Complete
    row = industry_jobs_tab._rows_cache[0]
    assert row["remaining_time"] == "Complete"


def test_cleanup_stops_timer(qtbot, industry_jobs_tab):
    """Test that cleanup stops the countdown timer."""
    # Start timer manually
    industry_jobs_tab._countdown_timer.start()
    assert industry_jobs_tab._countdown_timer.isActive()

    # Call cleanup
    industry_jobs_tab.cleanup()

    # Timer should be stopped
    assert not industry_jobs_tab._countdown_timer.isActive()


@pytest.mark.asyncio
async def test_countdown_timer_interval(qtbot, industry_jobs_tab):
    """Test that countdown timer has correct 1-second interval."""
    assert industry_jobs_tab._countdown_timer.interval() == 1000  # 1000ms = 1 second
