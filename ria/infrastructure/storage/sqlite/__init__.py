"""SQLite implementation of the facts store.

Implements the facts store of SDD section 6.2 and the persistence ports of
``ria.ports.repositories``. SQLite rather than a client-server database at this
stage because the system runs single-node until the extraction seams of SDD
section 6.1 are triggered by measured pressure, and the schema is written so that
the migration to PostgreSQL is a mapper and connection change rather than a
redesign.

Contents
--------
``connection``
    Per-thread connections with the pragmas required for concurrent read while
    writing.
``migrations``
    Forward-only, checksummed migration runner.
``mappers``
    The single translation point between domain entities and rows.
``repository_repository``, ``commit_repository``, ``branch_repository``,
``file_unit_repository``
    One adapter per aggregate root.
``unit_of_work``
    Transaction boundary spanning all four adapters.
"""

from __future__ import annotations

from ria.infrastructure.storage.sqlite.branch_repository import SqliteBranchStore
from ria.infrastructure.storage.sqlite.commit_repository import SqliteCommitStore
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.file_unit_repository import SqliteFileUnitStore
from ria.infrastructure.storage.sqlite.migrations import (
    SQL_DIRECTORY,
    Migration,
    MigrationRunner,
)
from ria.infrastructure.storage.sqlite.repository_repository import (
    SqliteRepositoryStore,
)
from ria.infrastructure.storage.sqlite.unit_of_work import (
    SqliteUnitOfWork,
    SqliteUnitOfWorkFactory,
)

__all__ = [
    "SQL_DIRECTORY",
    "ConnectionProvider",
    "Migration",
    "MigrationRunner",
    "SqliteBranchStore",
    "SqliteCommitStore",
    "SqliteFileUnitStore",
    "SqliteRepositoryStore",
    "SqliteUnitOfWork",
    "SqliteUnitOfWorkFactory",
]
