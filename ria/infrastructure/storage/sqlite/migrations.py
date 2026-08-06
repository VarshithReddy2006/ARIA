"""Schema migration runner.

Applies numbered SQL files from ``sql/`` in ascending order, recording each in a
ledger table so that a migration is applied exactly once.

Design choices
--------------
Forward-only
    There are no down migrations. A down migration is a promise to reverse a
    schema change safely, which is rarely true once data exists. Recovery from a
    bad migration is a forward migration.
Checksummed
    Each applied migration's SHA-256 is recorded. If a file's content changes
    after it has been applied, the runner refuses to proceed rather than leaving
    two deployments with silently divergent schemas — the failure mode that makes
    a schema drift investigation take days.
Transactional per migration
    Each file runs inside one transaction, so a failure leaves the schema at the
    previous version rather than half-migrated.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

from ria.domain.errors import StorageError
from ria.observability.logging import get_logger
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider

__all__ = ["Migration", "MigrationRunner", "SQL_DIRECTORY", "split_statements"]

_LOGGER = get_logger(__name__)

#: Directory containing the numbered migration files.
SQL_DIRECTORY = Path(__file__).parent / "sql"

_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS ria_schema_migration (
    version     INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL,
    checksum    TEXT    NOT NULL,
    applied_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
)
"""


def split_statements(sql: str) -> Sequence[str]:
    """Split a SQL script into individual executable statements.

    Semicolons inside single-quoted literals and inside ``--`` line comments are not
    treated as separators, so a statement containing either is not split
    incorrectly. Doubled quotes (``''``) inside a literal are handled, since that is
    SQLite's escape form.

    Public and separately tested because a splitter that is subtly wrong corrupts a
    schema migration, and that failure is far cheaper to catch in a unit test than
    in a deployment.

    Args:
        sql: Script contents.

    Returns:
        Non-empty statements in source order, with surrounding whitespace removed.
    """
    statements: List[str] = []
    buffer: List[str] = []
    in_string = False
    in_comment = False
    index = 0
    length = len(sql)

    while index < length:
        character = sql[index]

        if in_comment:
            buffer.append(character)
            if character == "\n":
                in_comment = False
            index += 1
            continue

        if in_string:
            buffer.append(character)
            if character == "'":
                # A doubled quote is an escaped quote, not a terminator.
                if index + 1 < length and sql[index + 1] == "'":
                    buffer.append(sql[index + 1])
                    index += 2
                    continue
                in_string = False
            index += 1
            continue

        if character == "-" and index + 1 < length and sql[index + 1] == "-":
            in_comment = True
            buffer.append(sql[index : index + 2])
            index += 2
            continue

        if character == "'":
            in_string = True
            buffer.append(character)
            index += 1
            continue

        if character == ";":
            statement = "".join(buffer).strip()
            if statement:
                statements.append(statement)
            buffer = []
            index += 1
            continue

        buffer.append(character)
        index += 1

    trailing = "".join(buffer).strip()
    if trailing:
        statements.append(trailing)
    return tuple(statements)


@dataclass(frozen=True)
class Migration:
    """One migration file.

    Attributes:
        version: Numeric version parsed from the filename prefix.
        name: Descriptive name parsed from the filename.
        path: Location of the file.
        sql: File contents.
    """

    version: int
    name: str
    path: Path
    sql: str

    @property
    def checksum(self) -> str:
        """SHA-256 of the file contents, used to detect post-hoc edits."""
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


class MigrationRunner:
    """Discovers and applies pending migrations.

    Args:
        connections: Provider of the connection to migrate.
        sql_directory: Directory to discover migration files in.
    """

    def __init__(
        self, connections: ConnectionProvider, *, sql_directory: Path = SQL_DIRECTORY
    ) -> None:
        self._connections = connections
        self._sql_directory = sql_directory

    def discover(self) -> Sequence[Migration]:
        """Load every migration file, ordered by version ascending.

        Returns:
            The discovered migrations.

        Raises:
            StorageError: If the directory is absent, a filename does not follow
                the ``NNNN_name.sql`` convention, or a version is duplicated.
        """
        if not self._sql_directory.is_dir():
            raise StorageError(
                "migration directory not found", {"path": str(self._sql_directory)}
            )
        migrations: List[Migration] = []
        seen: dict = {}
        for path in sorted(self._sql_directory.glob("*.sql")):
            version, name = self._parse_filename(path)
            if version in seen:
                raise StorageError(
                    "duplicate migration version",
                    {"version": version, "first": seen[version], "second": path.name},
                )
            seen[version] = path.name
            migrations.append(
                Migration(
                    version=version,
                    name=name,
                    path=path,
                    sql=path.read_text(encoding="utf-8"),
                )
            )
        return tuple(sorted(migrations, key=lambda migration: migration.version))

    def applied(self) -> Sequence[Tuple[int, str, str]]:
        """List migrations already recorded in the ledger.

        Returns:
            Tuples of ``(version, name, checksum)`` ordered by version.
        """
        connection = self._connections.connection()
        connection.execute(_LEDGER_DDL)
        rows = connection.execute(
            "SELECT version, name, checksum FROM ria_schema_migration ORDER BY version"
        ).fetchall()
        return tuple((row["version"], row["name"], row["checksum"]) for row in rows)

    def current_version(self) -> int:
        """Highest applied migration version, or zero if none are applied."""
        applied = self.applied()
        return applied[-1][0] if applied else 0

    def run(self) -> Sequence[Migration]:
        """Apply every pending migration.

        Idempotent: calling it when nothing is pending performs no writes and
        returns an empty sequence.

        Returns:
            The migrations applied by this call, in order.

        Raises:
            StorageError: If a previously applied migration's content has changed,
                or if a migration fails to apply.
        """
        connection = self._connections.connection()
        discovered = self.discover()
        applied = {version: checksum for version, _, checksum in self.applied()}

        self._verify_checksums(discovered, applied)

        performed: List[Migration] = []
        for migration in discovered:
            if migration.version in applied:
                continue
            self._apply(connection, migration)
            performed.append(migration)

        if performed:
            _LOGGER.info(
                "schema migrations applied",
                extra={
                    "count": len(performed),
                    "versions": [migration.version for migration in performed],
                    "database": str(self._connections.database_path),
                },
            )
        return tuple(performed)

    # -- internals --------------------------------------------------------

    @staticmethod
    def _parse_filename(path: Path) -> Tuple[int, str]:
        """Parse a migration filename into its version and name.

        Args:
            path: Migration file path, expected to be ``NNNN_name.sql``.

        Returns:
            The parsed version and name.

        Raises:
            StorageError: If the filename does not follow the convention.
        """
        stem = path.stem
        version_text, separator, name = stem.partition("_")
        if not separator or not version_text.isdigit() or not name:
            raise StorageError(
                "migration filename must follow the NNNN_name.sql convention",
                {"filename": path.name},
            )
        return int(version_text), name

    @staticmethod
    def _verify_checksums(
        discovered: Sequence[Migration], applied: "dict[int, str]"
    ) -> None:
        """Refuse to proceed if an applied migration's content has changed.

        Args:
            discovered: Migrations found on disk.
            applied: Version to checksum mapping from the ledger.

        Raises:
            StorageError: On any mismatch.
        """
        for migration in discovered:
            recorded = applied.get(migration.version)
            if recorded is not None and recorded != migration.checksum:
                raise StorageError(
                    "applied migration has been modified; schema integrity cannot be assured",
                    {
                        "version": migration.version,
                        "name": migration.name,
                        "recorded_checksum": recorded,
                        "file_checksum": migration.checksum,
                    },
                )

    def _apply(self, connection: sqlite3.Connection, migration: Migration) -> None:
        """Apply one migration inside a single transaction.

        Statements are executed individually rather than through
        :meth:`sqlite3.Connection.executescript`, because ``executescript`` issues
        an implicit ``COMMIT`` before running and would therefore discard the
        surrounding transaction. Without the transaction, a migration that failed
        halfway would leave the schema partially applied and the ledger empty —
        the worst possible state, because the next run would attempt the whole
        migration again against a half-migrated schema.

        Args:
            connection: Connection to apply against.
            migration: Migration to apply.

        Raises:
            StorageError: If the migration fails. The transaction is rolled back so
                the schema remains at the previous version.
        """
        try:
            connection.execute("BEGIN")
            for statement in split_statements(migration.sql):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO ria_schema_migration (version, name, checksum) VALUES (?, ?, ?)",
                (migration.version, migration.name, migration.checksum),
            )
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                # A rollback failure means the transaction was already closed by
                # the driver; the original error is the one worth reporting.
                pass
            raise StorageError(
                "migration failed to apply",
                {
                    "version": migration.version,
                    "name": migration.name,
                    "reason": str(exc),
                },
            ) from exc
