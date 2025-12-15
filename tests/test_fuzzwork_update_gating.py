"""Tests for Fuzzwork update gating (REQ-005, TEST-004).

Tests verify that Fuzzwork market data updates occur only on explicit
user-initiated requests, not on startup or character add.
"""

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, Mock

import pytest

from src.data.clients.fuzzwork_client import FuzzworkClient


@pytest.fixture
def temp_cache_dir():
    """Create temporary cache directory."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.mark.asyncio
async def test_fuzzwork_no_auto_update_on_startup(temp_cache_dir):
    """Test that Fuzzwork does NOT update automatically on application startup."""
    # Create a fuzzwork client with temp cache
    client = FuzzworkClient(cache_dir=temp_cache_dir)

    # Mock the HTTP client to track if HEAD/GET requests are made
    mock_http = AsyncMock()
    client._http_client = mock_http

    # Write a fake cached CSV
    csv_path = temp_cache_dir / "aggregatecsv.csv"
    csv_path.write_text("type_id,region_id,sell_median\n34,10000002,100.0\n")

    # Write metadata indicating recent download
    metadata = {
        "last_modified": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
        "etag": "test-etag",
        "last_updated": datetime.now(UTC).isoformat(),
    }
    metadata_path = temp_cache_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata))

    # Simulate startup: fetch with check_etag=False (per implementation)
    csv_text = await client.fetch_aggregate_csv(
        force=False, check_etag=False, progress_callback=None
    )

    # Verify HTTP client was NOT called (no remote check on startup)
    mock_http.head.assert_not_called()
    mock_http.get.assert_not_called()

    # Verify we got the cached CSV
    assert csv_text is not None
    assert "34,10000002,100.0" in csv_text


@pytest.mark.asyncio
async def test_fuzzwork_explicit_refresh_checks_etag(temp_cache_dir):
    """Test that explicit refresh DOES check ETag and update if needed."""
    # Create a fuzzwork client with temp cache
    client = FuzzworkClient(cache_dir=temp_cache_dir)

    # Mock HTTP responses
    mock_http = AsyncMock()

    # Mock HEAD response with different ETag
    mock_head_response = Mock()
    mock_head_response.headers = {"etag": "new-etag-12345"}
    mock_head_response.raise_for_status = Mock()
    mock_http.head.return_value = mock_head_response

    # Mock GET response with new CSV
    mock_get_response = Mock()
    mock_get_response.headers = {
        "etag": "new-etag-12345",
        "content-encoding": "gzip",
    }
    mock_get_response.raise_for_status = Mock()

    # Mock gzipped content
    new_csv_content = "type_id,region_id,sell_median\n34,10000002,200.0\n"
    compressed_content = gzip.compress(new_csv_content.encode("utf-8"))
    mock_get_response.aiter_bytes = AsyncMock(return_value=[compressed_content])
    mock_http.get.return_value = mock_get_response

    client._http_client = mock_http

    # Write old cached CSV
    csv_path = temp_cache_dir / "aggregatecsv.csv"
    csv_path.write_text("type_id,region_id,sell_median\n34,10000002,100.0\n")

    # Write old metadata
    # Make last_modified old enough to trigger ETag check (> 31 minutes)
    old_metadata = {
        "last_modified": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
        "etag": "old-etag",
        "last_updated": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
        "last_checked": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
    }
    metadata_path = temp_cache_dir / "metadata.json"
    metadata_path.write_text(json.dumps(old_metadata))

    # Explicit refresh: fetch with check_etag=True
    csv_text = await client.fetch_aggregate_csv(
        force=False, check_etag=True, progress_callback=None
    )

    # Verify HTTP client WAS called for ETag check
    mock_http.head.assert_called_once()

    # Verify we got the NEW CSV content
    assert csv_text is not None
    assert "200.0" in csv_text


@pytest.mark.asyncio
async def test_fuzzwork_no_update_within_etag_wait_window(temp_cache_dir):
    """Test that Fuzzwork does not check ETag within the 31-minute wait window."""
    # Create a fuzzwork client
    client = FuzzworkClient(cache_dir=temp_cache_dir)

    # Mock HTTP client
    mock_http = AsyncMock()
    client._http_client = mock_http

    # Write cached CSV
    csv_path = temp_cache_dir / "aggregatecsv.csv"
    csv_path.write_text("type_id,region_id,sell_median\n34,10000002,100.0\n")

    # Write recent metadata (within 31-minute window)
    recent_metadata = {
        "last_modified": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
        "etag": "test-etag",
        "last_updated": (datetime.now(UTC) - timedelta(minutes=20)).isoformat(),
    }
    metadata_path = temp_cache_dir / "metadata.json"
    metadata_path.write_text(json.dumps(recent_metadata))

    # Try to refresh with check_etag=True, but should use cache due to recency
    csv_text = await client.fetch_aggregate_csv(
        force=False, check_etag=True, progress_callback=None
    )

    # Verify HTTP client was NOT called (too recent)
    mock_http.head.assert_not_called()
    mock_http.get.assert_not_called()

    # Verify we got the cached CSV
    assert csv_text is not None


@pytest.mark.asyncio
async def test_fuzzwork_force_download_bypasses_cache(temp_cache_dir):
    """Test that force=True always downloads fresh data."""
    # Create a fuzzwork client
    client = FuzzworkClient(cache_dir=temp_cache_dir)

    # Mock HTTP response
    mock_http = AsyncMock()

    mock_get_response = Mock()
    mock_get_response.headers = {
        "etag": "forced-etag",
        "content-encoding": "gzip",
    }
    mock_get_response.raise_for_status = Mock()

    forced_csv = "type_id,region_id,sell_median\n34,10000002,999.0\n"
    compressed = gzip.compress(forced_csv.encode("utf-8"))
    mock_get_response.aiter_bytes = AsyncMock(return_value=[compressed])
    mock_http.get.return_value = mock_get_response

    client._http_client = mock_http

    # Write old cached CSV
    csv_path = temp_cache_dir / "aggregatecsv.csv"
    csv_path.write_text("type_id,region_id,sell_median\n34,10000002,100.0\n")

    # Force download
    csv_text = await client.fetch_aggregate_csv(
        force=True, check_etag=True, progress_callback=None
    )

    # Verify GET was called
    mock_http.get.assert_called_once()

    # Verify we got forced content
    assert "999.0" in csv_text


@pytest.mark.asyncio
async def test_fuzzwork_throttles_frequent_etag_checks(temp_cache_dir):
    """Test that ETag checks are throttled to avoid excessive requests."""
    # Create client
    client = FuzzworkClient(cache_dir=temp_cache_dir)

    # Mock HTTP client
    mock_http = AsyncMock()
    client._http_client = mock_http

    # Write cached CSV
    csv_path = temp_cache_dir / "aggregatecsv.csv"
    csv_path.write_text("type_id,region_id,sell_median\n34,10000002,100.0\n")

    # Write metadata with recent ETag check (< 5 minutes ago)
    metadata = {
        # Old enough for general refresh
        "last_modified": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
        "etag": "test-etag",
        "last_updated": (datetime.now(UTC) - timedelta(minutes=35)).isoformat(),
        # Recent ETag check (should throttle)
        "last_checked": (datetime.now(UTC) - timedelta(minutes=2)).isoformat(),
    }
    metadata_path = temp_cache_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata))

    # Try to check ETag - should be throttled
    csv_text = await client.fetch_aggregate_csv(
        force=False, check_etag=True, progress_callback=None
    )

    # Verify no HTTP request was made (throttled)
    mock_http.head.assert_not_called()
    mock_http.get.assert_not_called()

    # Verify we got cached content
    assert csv_text is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
