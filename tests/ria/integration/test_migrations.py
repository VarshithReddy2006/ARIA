"""Integration tests for the schema migration runner.

The runner's guarantees are forward-only application, exactly-once execution,
checksum verification, and per-migration transactionality. Each is tested against a
real SQLite file, because the failure modes being guarded against — a half-applied
schema, two deployments with divergent schemas — only manifest against a real
database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

import pytest

from ria.domain.errors import StorageError
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import (
    SQL_DIRECTORY,
    MigrationRunner,
)


@pytest.fixture
def connections(tmp_path: Path) -> Iterator[ConnectionProvider]:
    """A connection provider over a fresh database file."""
    provider = ConnectionProvider(tmp_path / "ria.db")
    yield provider
    provider.close()


@pytest.fixture
def runner(connections: ConnectionProvider) -> MigrationRunner:
    """A runner over the shipped migration directory."""
    return MigrationRunner(connections)


def table_names(connections: ConnectionProvider) -> set:
    """Read the set of table names present in the database.

    Args:
        connections: Provider of the connection to inspect.
    """
    rows = (
        connections.connection()
        .execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        .fetchall()
    )
    return {row["name"] for row in rows}


class TestDiscovery:
    """Loading migration files from disk."""

    def test_discovers_the_shipped_migrations(self, runner: MigrationRunner) -> None:
        """Every numbered file in the SQL directory is discovered."""
        discovered = runner.discover()
        assert len(discovered) >= 1
        assert discovered[0].version == 1
        assert discovered[0].name == "repository_foundation"

    def test_orders_by_version_ascending(self, runner: MigrationRunner) -> None:
        """Ordering is numeric so version 10 follows version 9, not version 1."""
        versions = [migration.version for migration in runner.discover()]
        assert versions == sorted(versions)

    def test_rejects_a_missing_directory(self, connections: ConnectionProvider) -> None:
        """A missing migration directory is a configuration fault, not an empty set.

        Treating it as empty would silently start against an unmigrated database.
        """
        with pytest.raises(StorageError, match="migration directory not found"):
            MigrationRunner(connections, sql_directory=Path("no/such/dir")).discover()

    def test_rejects_a_malformed_filename(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """A filename without a numeric prefix has no defined order."""
        directory = tmp_path / "sql"
        directory.mkdir()
        (directory / "create_things.sql").write_text("SELECT 1;", encoding="utf-8")
        with pytest.raises(StorageError, match="NNNN_name.sql"):
            MigrationRunner(connections, sql_directory=directory).discover()

    def test_rejects_a_duplicate_version(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """Two files claiming one version would apply in an undefined order."""
        directory = tmp_path / "sql"
        directory.mkdir()
        (directory / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
        (directory / "0001_second.sql").write_text("SELECT 2;", encoding="utf-8")
        with pytest.raises(StorageError, match="duplicate migration version"):
            MigrationRunner(connections, sql_directory=directory).discover()

    def test_checksum_reflects_content(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """A file's checksum changes when its content changes."""
        directory = tmp_path / "sql"
        directory.mkdir()
        path = directory / "0001_thing.sql"
        path.write_text("SELECT 1;", encoding="utf-8")
        first = MigrationRunner(connections, sql_directory=directory).discover()[0]
        path.write_text("SELECT 2;", encoding="utf-8")
        second = MigrationRunner(connections, sql_directory=directory).discover()[0]
        assert first.checksum != second.checksum


class TestApplication:
    """Applying migrations."""

    def test_creates_every_expected_table(
        self, runner: MigrationRunner, connections: ConnectionProvider
    ) -> None:
        """The foundation migration creates the Milestone 1 entity tables."""
        runner.run()
        names = table_names(connections)
        assert {
            "ria_repository",
            "ria_commit",
            "ria_branch",
            "ria_file_unit",
            "ria_schema_migration",
        } <= names

    def test_does_not_touch_legacy_tables(
        self, runner: MigrationRunner, connections: ConnectionProvider
    ) -> None:
        """The ``ria_`` prefix keeps the two migration chains independent.

        A deployment could point both at one file; the prefix means neither chain
        can alter the other's schema.
        """
        runner.run()
        assert all(name.startswith("ria_") for name in table_names(connections))

    def test_records_what_it_applied(self, runner: MigrationRunner) -> None:
        """The ledger records version, name and checksum for each migration."""
        applied = runner.run()
        recorded = runner.applied()
        assert len(recorded) == len(applied)
        assert recorded[0][0] == 1
        assert recorded[0][2] == applied[0].checksum

    def test_reports_the_current_version(self, runner: MigrationRunner) -> None:
        """The current version is zero before any run and the highest after."""
        assert runner.current_version() == 0
        runner.run()
        assert runner.current_version() == runner.discover()[-1].version

    def test_is_idempotent(self, runner: MigrationRunner) -> None:
        """A second run applies nothing and performs no writes.

        Required because the composition root migrates on every start; a
        non-idempotent runner would fail every restart.
        """
        first = runner.run()
        second = runner.run()
        assert len(first) >= 1
        assert second == ()

    def test_applies_only_pending_migrations(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """A migration added after a run is applied on the next run alone."""
        directory = tmp_path / "sql"
        directory.mkdir()
        (directory / "0001_first.sql").write_text(
            "CREATE TABLE ria_a (x TEXT);", encoding="utf-8"
        )
        runner = MigrationRunner(connections, sql_directory=directory)
        runner.run()

        (directory / "0002_second.sql").write_text(
            "CREATE TABLE ria_b (y TEXT);", encoding="utf-8"
        )
        applied = runner.run()
        assert [migration.version for migration in applied] == [2]
        assert {"ria_a", "ria_b"} <= table_names(connections)

    def test_migration_is_transactional(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """A failing migration leaves the schema at the previous version.

        Statements run individually inside an explicit transaction rather than
        through ``executescript``, which would commit implicitly and leave a
        half-applied schema with an empty ledger — the worst possible state, since
        the next run would retry the whole migration against a partial schema.
        """
        directory = tmp_path / "sql"
        directory.mkdir()
        (directory / "0001_broken.sql").write_text(
            "CREATE TABLE ria_ok (x TEXT);\nTHIS IS NOT SQL;", encoding="utf-8"
        )
        runner = MigrationRunner(connections, sql_directory=directory)
        with pytest.raises(StorageError, match="migration failed to apply"):
            runner.run()
        assert "ria_ok" not in table_names(connections)
        assert runner.current_version() == 0


class TestChecksumVerification:
    """Detection of post-hoc edits to an applied migration."""

    def test_refuses_to_proceed_when_an_applied_file_changed(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """Editing an applied migration halts the runner.

        Without this, two deployments would silently hold different schemas at the
        same recorded version, and diagnosing the divergence would take days.
        """
        directory = tmp_path / "sql"
        directory.mkdir()
        path = directory / "0001_thing.sql"
        path.write_text("CREATE TABLE ria_a (x TEXT);", encoding="utf-8")
        runner = MigrationRunner(connections, sql_directory=directory)
        runner.run()

        path.write_text("CREATE TABLE ria_a (x TEXT, y TEXT);", encoding="utf-8")
        with pytest.raises(StorageError, match="has been modified") as caught:
            runner.run()
        assert "recorded_checksum" in caught.value.context
        assert "file_checksum" in caught.value.context

    def test_verification_precedes_application(
        self, connections: ConnectionProvider, tmp_path: Path
    ) -> None:
        """A tampered earlier migration blocks a valid later one.

        Verification runs over the whole set before anything is applied, so the
        database is never advanced past a schema whose history is in doubt.
        """
        directory = tmp_path / "sql"
        directory.mkdir()
        first = directory / "0001_first.sql"
        first.write_text("CREATE TABLE ria_a (x TEXT);", encoding="utf-8")
        runner = MigrationRunner(connections, sql_directory=directory)
        runner.run()

        first.write_text("CREATE TABLE ria_a (x TEXT, y TEXT);", encoding="utf-8")
        (directory / "0002_second.sql").write_text(
            "CREATE TABLE ria_b (y TEXT);", encoding="utf-8"
        )
        with pytest.raises(StorageError, match="has been modified"):
            runner.run()
        assert "ria_b" not in table_names(connections)


class TestSchemaShape:
    """Properties of the applied schema that the adapters depend on."""

    def test_shipped_directory_is_the_default(self) -> None:
        """The runner defaults to the packaged SQL directory."""
        assert SQL_DIRECTORY.is_dir()

    def test_foreign_keys_are_enforced(
        self, runner: MigrationRunner, connections: ConnectionProvider
    ) -> None:
        """Cascade deletes depend on foreign key enforcement being on.

        SQLite disables it by default, and a declared-but-unenforced foreign key is
        worse than none: it implies a guarantee the database is not providing.
        """
        runner.run()
        row = connections.connection().execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1

    def test_journal_mode_is_write_ahead_logging(
        self, runner: MigrationRunner, connections: ConnectionProvider
    ) -> None:
        """Readers must proceed during an index build to meet the latency target."""
        runner.run()
        row = connections.connection().execute("PRAGMA journal_mode").fetchone()
        assert str(row[0]).lower() == "wal"

    def test_at_most_one_default_branch_per_repository(
        self, runner: MigrationRunner, connections: ConnectionProvider
    ) -> None:
        """The partial unique index permits many branches and one default."""
        runner.run()
        connection = connections.connection()
        connection.execute(
            "INSERT INTO ria_repository (repository_id, moniker, origin_url, "
            "default_branch, tenant_id, status, index_policy, languages, frameworks, "
            "size_metrics, registered_at, updated_at) VALUES "
            "('r1', 'repo:github.com:a/b', 'https://x', 'main', 't', 'registered', "
            "'{}', '[]', '[]', '{}', '2026-01-01T00:00:00+00:00', "
            "'2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO ria_branch (repository_id, name, head_sha, is_default, "
            "updated_at) VALUES ('r1', 'main', 'a', 1, '2026-01-01T00:00:00+00:00')"
        )
        connection.execute(
            "INSERT INTO ria_branch (repository_id, name, head_sha, is_default, "
            "updated_at) VALUES ('r1', 'feature', 'b', 0, '2026-01-01T00:00:00+00:00')"
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ria_branch (repository_id, name, head_sha, is_default, "
                "updated_at) VALUES ('r1', 'other', 'c', 1, "
                "'2026-01-01T00:00:00+00:00')"
            )

    def test_degraded_repository_must_state_a_reason(
        self, runner: MigrationRunner, connections: ConnectionProvider
    ) -> None:
        """The database enforces the same invariant as the entity.

        A direct write through another client cannot introduce silent degradation.
        """
        runner.run()

        with pytest.raises(sqlite3.IntegrityError):
            connections.connection().execute(
                "INSERT INTO ria_repository (repository_id, moniker, origin_url, "
                "default_branch, tenant_id, status, index_policy, languages, "
                "frameworks, size_metrics, registered_at, updated_at) VALUES "
                "('r2', 'repo:github.com:a/c', 'https://x', 'main', 't', 'degraded', "
                "'{}', '[]', '[]', '{}', '2026-01-01T00:00:00+00:00', "
                "'2026-01-01T00:00:00+00:00')"
            )
