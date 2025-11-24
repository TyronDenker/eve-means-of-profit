"""Unified SQLite repository for all application data.

This module provides a single, centralized repository for managing:
- Database connections and schema initialization
- Asset tracking and history
- Market price tracking
- Net worth snapshots
- Wallet transactions, contracts, industry jobs
- Future data storage needs

The repository pattern consolidates all database operations while keeping
access methods organized in separate modules (assets.py, prices.py, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

from utils import global_config

from . import schemas

logger = logging.getLogger(__name__)


class Repository:
    """Unified repository for all application data storage.

    This class manages the single SQLite database connection and provides
    core database operations. Specific data access methods are organized
    in separate modules (assets.py, prices.py) that use this repository.

    Usage:
        repo = Repository()
        await repo.initialize()

        # Use with asset access methods
        from data.repositories import assets
        snapshot_id = await assets.save_snapshot(repo, character_id, asset_list)

        # Use with price access methods
        from data.repositories import prices
        latest = await prices.get_latest_jita_price(repo, type_id)
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        """Initialize repository with database connection.

        Args:
            db_path: Path to the SQLite database file. If None, uses default
                location in user data directory.
        """
        if db_path is None:
            db_path = global_config.app.user_data_dir / "data.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get or create a database connection.

        Returns:
            Active SQLite connection
        """
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                isolation_level="DEFERRED",  # Enable transactions for batching
            )
            self._conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
            # Performance optimizations for bulk inserts
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA cache_size = -64000")  # 64MB cache

        return self._conn

    async def execute(
        self, sql: str, parameters: tuple[Any, ...] | dict[str, Any] = ()
    ) -> sqlite3.Cursor:
        """Execute a SQL statement asynchronously.

        Args:
            sql: SQL statement to execute
            parameters: Parameters for the SQL statement

        Returns:
            Cursor with results
        """
        async with self._lock:
            conn = self._get_connection()
            return await asyncio.to_thread(conn.execute, sql, parameters)

    async def executemany(
        self, sql: str, parameters: list[tuple[Any, ...]] | list[dict[str, Any]]
    ) -> sqlite3.Cursor:
        """Execute a SQL statement with multiple parameter sets.

        Automatically wraps in a transaction for batch performance.

        Args:
            sql: SQL statement to execute
            parameters: List of parameter sets

        Returns:
            Cursor with results
        """
        async with self._lock:
            conn = self._get_connection()

            def _executemany_with_transaction():
                try:
                    cursor = conn.executemany(sql, parameters)
                    conn.commit()
                    return cursor
                except Exception:
                    conn.rollback()
                    raise

            return await asyncio.to_thread(_executemany_with_transaction)

    async def fetchall(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[Any]:
        """Execute query and fetch all results.

        Args:
            sql: SQL query to execute
            parameters: Parameters for the query

        Returns:
            List of result rows
        """
        cursor = await self.execute(sql, parameters)
        return cursor.fetchall()

    async def fetchone(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any | None:
        """Execute query and fetch one result.

        Args:
            sql: SQL query to execute
            parameters: Parameters for the query

        Returns:
            Single result row or None
        """
        cursor = await self.execute(sql, parameters)
        return cursor.fetchone()

    async def commit(self) -> None:
        """Commit current transaction."""
        async with self._lock:
            if self._conn:
                await asyncio.to_thread(self._conn.commit)

    async def rollback(self) -> None:
        """Rollback current transaction."""
        async with self._lock:
            if self._conn:
                await asyncio.to_thread(self._conn.rollback)

    async def close(self) -> None:
        """Close the database connection."""
        async with self._lock:
            if self._conn:
                await asyncio.to_thread(self._conn.close)
                self._conn = None
                self._initialized = False

    async def initialize(self) -> None:
        """Initialize the repository and ensure schema is created.

        This is safe to call multiple times - it will only initialize once.
        """
        if self._initialized:
            return

        # Always (re)apply schema to ensure new tables/indexes exist.
        # Statements use IF NOT EXISTS, so this is fast and idempotent.
        await self.initialize_schema()

        self._initialized = True

    async def initialize_schema(self) -> None:
        """Initialize database schema with all required tables."""
        logger.info("Initializing database schema at %s", self.db_path)

        for sql_statement in schemas.ALL_TABLES:
            # Split by semicolons to handle multiple statements
            statements = [s.strip() for s in sql_statement.split(";") if s.strip()]
            for stmt in statements:
                try:
                    await self.execute(stmt)
                except sqlite3.Error as e:
                    logger.error("Failed to execute schema statement: %s", e)
                    logger.debug("Statement was: %s", stmt)
                    raise

        await self.commit()
        logger.info("Database schema initialized successfully")

    async def vacuum(self) -> None:
        """Vacuum the database to reclaim space and optimize."""
        logger.info("Vacuuming database...")
        await self.execute("VACUUM")
        logger.info("Database vacuum complete")

    async def get_table_info(self, table_name: str) -> list[Any]:
        """Get information about a table's schema.

        Args:
            table_name: Name of the table to inspect

        Returns:
            List of column information
        """
        return await self.fetchall(f"PRAGMA table_info({table_name})")

    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        result = await self.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        return result is not None


__all__ = ["Repository"]
