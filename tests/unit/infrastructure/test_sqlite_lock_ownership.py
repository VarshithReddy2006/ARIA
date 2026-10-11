from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from unittest.mock import patch

from ria.domain.common.value_objects import UUIDv4
from ria.domain.sync.value_objects import RepositoryIdentity
from ria.infrastructure.storage.sqlite_lock import SQLiteRepositoryLockAdapter


def _repository() -> RepositoryIdentity:
    return RepositoryIdentity(
        repo_id=UUIDv4.generate(),
        remote_url="https://example.test/repo.git",
        name="repo",
    )


def test_expired_owner_cannot_release_successor_lease(tmp_path: Path) -> None:
    database = tmp_path / "locks.sqlite"
    first = SQLiteRepositoryLockAdapter(database)
    second = SQLiteRepositoryLockAdapter(database)
    repository = _repository()

    with patch(
        "ria.infrastructure.storage.sqlite_lock.time.monotonic", return_value=100.0
    ):
        assert first.acquire_lock(repository, ttl_seconds=10)
    with patch(
        "ria.infrastructure.storage.sqlite_lock.time.monotonic", return_value=111.0
    ):
        assert second.acquire_lock(repository, ttl_seconds=10)
        # Simulate the first worker's finally block after the successor owns the row.
        first.release_lock(repository)
        assert second.is_locked(repository)
        second.release_lock(repository)
        assert not second.is_locked(repository)


def test_shared_adapter_uses_thread_local_owner_tokens(tmp_path: Path) -> None:
    adapter = SQLiteRepositoryLockAdapter(tmp_path / "locks.sqlite")
    repository = _repository()
    first_acquired = threading.Event()
    allow_first_release = threading.Event()
    first_released = threading.Event()
    second_finished = threading.Event()
    outcome: dict[str, bool] = {}

    def first_worker() -> None:
        outcome["first_acquired"] = adapter.acquire_lock(repository, ttl_seconds=300)
        first_acquired.set()
        assert allow_first_release.wait(timeout=5)
        adapter.release_lock(repository)
        first_released.set()

    def second_worker() -> None:
        assert first_acquired.wait(timeout=5)
        # Expire the lease deterministically, without timing-dependent sleeps.
        with sqlite3.connect(tmp_path / "locks.sqlite") as connection:
            connection.execute("UPDATE repository_lock SET ttl_seconds = 0")
        outcome["second_acquired"] = adapter.acquire_lock(repository, ttl_seconds=300)
        allow_first_release.set()
        assert first_released.wait(timeout=5)
        outcome["second_still_locked"] = adapter.is_locked(repository)
        adapter.release_lock(repository)
        second_finished.set()

    first = threading.Thread(target=first_worker)
    second = threading.Thread(target=second_worker)
    first.start()
    second.start()
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert second_finished.is_set()
    assert outcome == {
        "first_acquired": True,
        "second_acquired": True,
        "second_still_locked": True,
    }


def test_failed_reacquisition_preserves_original_owner(tmp_path: Path) -> None:
    adapter = SQLiteRepositoryLockAdapter(tmp_path / "locks.sqlite")
    repository = _repository()
    assert adapter.acquire_lock(repository)
    assert not adapter.acquire_lock(repository)
    adapter.release_lock(repository)
    assert not adapter.is_locked(repository)


def test_old_schema_migrates_and_legacy_lock_waits_for_expiry(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite"
    repository = _repository()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE repository_lock ("
            "repo_id TEXT PRIMARY KEY, acquired_at REAL NOT NULL, ttl_seconds REAL NOT NULL)"
        )
        connection.execute(
            "INSERT INTO repository_lock VALUES (?, ?, ?)",
            (repository.repo_id.value, 100.0, 10.0),
        )

    adapter = SQLiteRepositoryLockAdapter(database)
    with patch(
        "ria.infrastructure.storage.sqlite_lock.time.monotonic", return_value=105.0
    ):
        with sqlite3.connect(database) as connection:
            columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(repository_lock)")
            }
        assert "owner_token" in columns
        assert adapter.is_locked(repository)
        adapter.release_lock(repository)  # This adapter did not acquire the legacy row.
        assert adapter.is_locked(repository)

    with patch(
        "ria.infrastructure.storage.sqlite_lock.time.monotonic", return_value=111.0
    ):
        assert adapter.acquire_lock(repository, ttl_seconds=10)
        assert adapter.is_locked(repository)


def test_same_thread_cannot_replace_its_unreleased_expired_handle(
    tmp_path: Path,
) -> None:
    adapter = SQLiteRepositoryLockAdapter(tmp_path / "locks.sqlite")
    repository = _repository()
    assert adapter.acquire_lock(repository, ttl_seconds=0)
    assert not adapter.acquire_lock(repository)
    adapter.release_lock(repository)
    assert adapter.acquire_lock(repository)
    adapter.release_lock(repository)


def test_concurrent_constructors_migrate_legacy_schema(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    database = tmp_path / "legacy.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE repository_lock ("
            "repo_id TEXT PRIMARY KEY, acquired_at REAL NOT NULL, ttl_seconds REAL NOT NULL)"
        )
    ready = threading.Barrier(2)

    def construct():
        ready.wait(timeout=5)
        return SQLiteRepositoryLockAdapter(database)

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(construct) for _ in range(2)]
        adapters = [future.result(timeout=10) for future in futures]
    repository = _repository()
    assert adapters[0].acquire_lock(repository)
    assert not adapters[1].acquire_lock(repository)
    adapters[0].release_lock(repository)
