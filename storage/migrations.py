"""Lightweight database migration and versioning tool for SQLite."""

import os
import sqlite3
import logging
from typing import List, Tuple
from core.config import settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def get_db_connection() -> sqlite3.Connection:
    """Gets a connection to the SQLite database, creating parent dirs if needed."""
    os.makedirs(os.path.dirname(settings.sqlite_db_path), exist_ok=True)
    return sqlite3.connect(settings.sqlite_db_path)


def initialize_migrations_table(conn: sqlite3.Connection) -> None:
    """Creates the schema_migrations table to track applied migrations."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_applied_versions(conn: sqlite3.Connection) -> List[int]:
    """Gets the list of applied migration versions."""
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
    return [row[0] for row in cursor.fetchall()]


def run_migrations() -> None:
    """Scans for pending SQL migrations in storage/migrations/ and applies them."""
    conn = get_db_connection()
    try:
        initialize_migrations_table(conn)
        applied = get_applied_versions(conn)

        # Discover migrations
        migrations: List[Tuple[int, str]] = []
        if os.path.exists(MIGRATIONS_DIR):
            for filename in os.listdir(MIGRATIONS_DIR):
                if filename.endswith(".sql"):
                    try:
                        # Extract version prefix (e.g. 0001 from 0001_initial.sql)
                        parts = filename.split("_", 1)
                        version = int(parts[0])
                        migrations.append(
                            (version, os.path.join(MIGRATIONS_DIR, filename))
                        )
                    except ValueError:
                        logger.warning(
                            "Skipping migration file with invalid name format: %s",
                            filename,
                        )

        # Sort migrations sequentially by version number
        migrations.sort(key=lambda x: x[0])

        for version, filepath in migrations:
            if version not in applied:
                logger.info(
                    "Applying database migration version %d (%s)...",
                    version,
                    os.path.basename(filepath),
                )
                with open(filepath, "r", encoding="utf-8") as fh:
                    sql_content = fh.read()

                with conn:
                    # Execute migration SQL script
                    conn.executescript(sql_content)
                    # Record the migration as applied
                    conn.execute(
                        "INSERT INTO schema_migrations (version) VALUES (?)",
                        (version,),
                    )
                logger.info("Migration version %d applied successfully.", version)
    except Exception as exc:
        logger.error("Failed to run database migrations: %s", exc, exc_info=True)
        raise
    finally:
        conn.close()
