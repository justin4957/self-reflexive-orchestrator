"""Database management for analytics and tracking.

Provides SQLite-based storage for operation tracking, success/failure metrics,
and historical data analysis.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .logger import AuditLogger


class DatabaseError(Exception):
    """Base exception for database errors."""

    pass


class Database:
    """Manages SQLite database for analytics and tracking.

    Responsibilities:
    - Initialize database schema
    - Provide connection management
    - Execute queries safely
    - Handle migrations
    - Ensure data integrity
    """

    SCHEMA_VERSION = 2

    def __init__(self, db_path: str, logger: AuditLogger):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file
            logger: Audit logger instance
        """
        self.db_path = Path(db_path)
        self.logger = logger
        self._ensure_directory()
        self._initialize_schema()

    def _ensure_directory(self):
        """Ensure database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _initialize_schema(self):
        """Initialize database schema if not exists."""
        with self.connection() as conn:
            cursor = conn.cursor()

            # Create schema version table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Check current version
            cursor.execute("SELECT MAX(version) FROM schema_version")
            result = cursor.fetchone()
            current_version = result[0] if result[0] is not None else 0

            if current_version < self.SCHEMA_VERSION:
                self._apply_migrations(conn, current_version)

    def _apply_migrations(self, conn: sqlite3.Connection, from_version: int):
        """Apply database migrations.

        Args:
            conn: Database connection
            from_version: Current schema version
        """
        cursor = conn.cursor()

        if from_version < 1:
            # Migration 1: Initial schema
            self._create_initial_schema(cursor)
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (1,))
            conn.commit()

            self.logger.info(
                "database_migration_applied",
                from_version=from_version,
                to_version=1,
            )

        if from_version < 2:
            # Migration 2: Add repository context table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS repository_context (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    context_data TEXT NOT NULL,
                    last_updated TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (2,))
            conn.commit()

            self.logger.info("database_migration_applied", from_version=1, to_version=2)

    def _create_initial_schema(self, cursor: sqlite3.Cursor):
        """Create initial database schema.

        Args:
            cursor: Database cursor
        """
        # Operations table - tracks all orchestrator operations
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_type TEXT NOT NULL,
                operation_id TEXT,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                duration_seconds REAL,
                success BOOLEAN NOT NULL,
                error_message TEXT,
                error_type TEXT,
                retry_count INTEGER DEFAULT 0,
                context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Issue processing table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS issue_processing (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                issue_number INTEGER NOT NULL,
                complexity INTEGER,
                files_changed INTEGER,
                lines_added INTEGER,
                lines_deleted INTEGER,
                tests_added INTEGER,
                success BOOLEAN NOT NULL,
                failure_reason TEXT,
                time_to_completion_seconds REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (operation_id) REFERENCES operations (id)
            )
        """
        )

        # Code generation table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS code_generation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                issue_number INTEGER,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                tokens_used INTEGER,
                cost REAL,
                first_attempt_success BOOLEAN,
                retry_count INTEGER DEFAULT 0,
                test_pass_rate REAL,
                error_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (operation_id) REFERENCES operations (id)
            )
        """
        )

        # PR management table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS pr_management (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                pr_number INTEGER NOT NULL,
                issue_number INTEGER,
                created BOOLEAN DEFAULT TRUE,
                merged BOOLEAN DEFAULT FALSE,
                ci_passed BOOLEAN,
                review_approved BOOLEAN,
                time_to_merge_seconds REAL,
                ci_failure_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (operation_id) REFERENCES operations (id)
            )
        """
        )

        # Roadmap tracking table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS roadmap_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id INTEGER NOT NULL,
                proposals_generated INTEGER,
                proposals_validated INTEGER,
                proposals_approved INTEGER,
                issues_created INTEGER,
                issues_implemented INTEGER,
                average_proposal_quality REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (operation_id) REFERENCES operations (id)
            )
        """
        )

        # Create indexes for common queries
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_operations_type_success
            ON operations (operation_type, success)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_operations_started_at
            ON operations (started_at)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_issue_processing_issue
            ON issue_processing (issue_number)
        """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pr_management_pr
            ON pr_management (pr_number)
        """
        )

    @contextmanager
    def connection(self):
        """Context manager for database connections.

        Yields:
            sqlite3.Connection: Database connection

        Example:
            with db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM operations")
        """
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
            )
            conn.row_factory = sqlite3.Row  # Access columns by name
            yield conn
        except sqlite3.Error as e:
            self.logger.error(
                "database_error",
                error=str(e),
                operation="connection",
            )
            if conn:
                conn.rollback()
            raise DatabaseError(f"Database error: {e}")
        finally:
            if conn:
                conn.close()

    def execute(
        self, query: str, params: tuple = (), fetch_one: bool = False
    ) -> Optional[Any]:
        """Execute a query and return results.

        Args:
            query: SQL query to execute
            params: Query parameters
            fetch_one: If True, fetch only one result

        Returns:
            Query results or None

        Raises:
            DatabaseError: If query execution fails
        """
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if query.strip().upper().startswith("SELECT"):
                if fetch_one:
                    return cursor.fetchone()
                return cursor.fetchall()
            else:
                conn.commit()
                return cursor.lastrowid

    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query multiple times with different parameters.

        Args:
            query: SQL query to execute
            params_list: List of parameter tuples

        Returns:
            Number of rows affected

        Raises:
            DatabaseError: If query execution fails
        """
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount

    def get_table_stats(self) -> Dict[str, int]:
        """Get row counts for all tables.

        Returns:
            Dictionary mapping table names to row counts
        """
        stats = {}
        tables = [
            "operations",
            "issue_processing",
            "code_generation",
            "pr_management",
            "roadmap_tracking",
        ]

        with self.connection() as conn:
            cursor = conn.cursor()
            for table in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                result = cursor.fetchone()
                stats[table] = result[0] if result else 0

        return stats

    def vacuum(self):
        """Optimize database by vacuuming."""
        with self.connection() as conn:
            conn.execute("VACUUM")
        self.logger.info("database_vacuumed", db_path=str(self.db_path))

    def backup(self, backup_path: str):
        """Create a backup of the database.

        Args:
            backup_path: Path for backup file
        """
        backup_file = Path(backup_path)
        backup_file.parent.mkdir(parents=True, exist_ok=True)

        with self.connection() as conn:
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn)
            backup_conn.close()

        self.logger.info(
            "database_backup_created",
            source=str(self.db_path),
            backup=backup_path,
        )

    def reset(self):
        """Reset database by dropping all data.

        WARNING: This will delete all tracked data!
        """
        with self.connection() as conn:
            cursor = conn.cursor()

            # Get all tables
            cursor.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
            )
            tables = [row[0] for row in cursor.fetchall()]

            # Drop all tables
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")

            conn.commit()

        # Reinitialize schema
        self._initialize_schema()

        self.logger.warning("database_reset", tables_dropped=len(tables))

    def save_repository_context(self, context_data: str, last_updated: str):
        """Save repository context to database.

        Args:
            context_data: JSON-serialized context data
            last_updated: Timestamp of last update
        """
        with self.connection() as conn:
            cursor = conn.cursor()

            # Delete old context (keep only latest)
            cursor.execute("DELETE FROM repository_context")

            # Insert new context
            cursor.execute(
                """
                INSERT INTO repository_context (context_data, last_updated)
                VALUES (?, ?)
            """,
                (context_data, last_updated),
            )

            conn.commit()

        self.logger.info("repository_context_saved", last_updated=last_updated)

    def load_repository_context(self) -> Optional[Dict[str, Any]]:
        """Load repository context from database.

        Returns:
            Context dictionary, or None if not found
        """
        import json

        with self.connection() as conn:
            cursor = conn.cursor()

            # Disable timestamp parsing for this query
            results = self.execute(
                """
                SELECT context_data, last_updated
                FROM repository_context
                ORDER BY created_at DESC
                LIMIT 1
            """,
                (),
            )

            if results:
                result = results[0]
                context_data = json.loads(result["context_data"])
                context_data["last_updated"] = result["last_updated"]
                self.logger.info(
                    "repository_context_loaded", last_updated=result["last_updated"]
                )
                return context_data

        return None
