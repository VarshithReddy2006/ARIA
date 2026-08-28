"""Lightweight database migration and versioning tool for SQLite."""

import logging
import os
import random
import sqlite3
import time
from typing import List, Optional, Tuple
from core.config import settings

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_BUSY_TIMEOUT_MS = 60000


def get_db_connection(
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
) -> sqlite3.Connection:
    """Gets a connection to the SQLite database with WAL mode and generous busy timeout."""
    db_path = settings.sqlite_db_path
    db_dir = os.path.dirname(os.path.abspath(db_path))
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=timeout)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms};")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except Exception as exc:
        logger.debug("Pragma configuration note: %s", exc)
    return conn


def initialize_migrations_table(conn: sqlite3.Connection) -> None:
    """Creates the schema_migrations table to track applied migrations."""
    try:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("COMMIT;")
    except sqlite3.OperationalError as exc:
        if "cannot start a transaction within a transaction" in str(exc).lower():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        else:
            try:
                conn.execute("ROLLBACK;")
            except Exception:
                pass
            raise
    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        raise


def get_applied_versions(conn: sqlite3.Connection) -> List[int]:
    """Gets the list of applied migration versions."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [row[0] for row in cursor.fetchall()]
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc).lower():
            return []
        raise


def _apply_migrations_with_lock(conn: sqlite3.Connection) -> None:
    """Executes schema initialization and pending migrations within an immediate write transaction."""
    conn.execute("BEGIN IMMEDIATE;")
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        applied = [row[0] for row in cursor.fetchall()]

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

                # Execute individual statements within the immediate transaction
                for statement in sql_content.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        conn.execute(stmt)

                # Record the migration as applied
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (?)",
                    (version,),
                )
                logger.info("Migration version %d applied successfully.", version)

        conn.execute("COMMIT;")
    except Exception:
        try:
            conn.execute("ROLLBACK;")
        except Exception:
            pass
        raise


def run_migrations(max_retries: int = 5, initial_delay: float = 0.5) -> None:
    """Scans for pending SQL migrations in storage/migrations/ and applies them idempotently.

    Uses BEGIN IMMEDIATE for exclusive migration lock acquisition and exponential backoff
    with jitter to handle concurrent startups across multiple API replicas.
    """
    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = get_db_connection()
            _apply_migrations_with_lock(conn)
            return
        except sqlite3.OperationalError as exc:
            err_msg = str(exc).lower()
            if "locked" in err_msg or "busy" in err_msg:
                last_error = exc
                if attempt < max_retries:
                    delay = initial_delay * (2 ** (attempt - 1)) + random.uniform(
                        0.05, 0.25
                    )
                    logger.warning(
                        "Database locked during migration attempt %d/%d. Retrying in %.2fs: %s",
                        attempt,
                        max_retries,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                    continue
            logger.error("Failed to run database migrations: %s", exc, exc_info=True)
            raise
        except Exception as exc:
            logger.error("Failed to run database migrations: %s", exc, exc_info=True)
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    if last_error is not None:
        raise last_error
