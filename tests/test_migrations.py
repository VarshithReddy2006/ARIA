import os
import pytest
from backend.settings import settings
from storage.migrations import run_migrations, get_db_connection, get_applied_versions


@pytest.fixture(autouse=True)
def temp_db_path(tmp_path, monkeypatch):
    # Override settings.sqlite_db_path to a temporary file
    db_file = tmp_path / "test_repo_understanding.db"
    monkeypatch.setattr(settings, "sqlite_db_path", str(db_file))
    yield
    # Cleanup database file after test
    if db_file.exists():
        try:
            os.remove(db_file)
        except OSError:
            pass


def test_run_migrations_initializes_db():
    # Verify DB file doesn't exist yet
    assert not os.path.exists(settings.sqlite_db_path)

    # Run migrations
    run_migrations()

    # Verify DB file is created
    assert os.path.exists(settings.sqlite_db_path)

    # Verify table schema exists and migration version is recorded
    conn = get_db_connection()
    try:
        applied = get_applied_versions(conn)
        assert 1 in applied

        # Query repositories table to ensure it was created
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='repositories'"
        )
        assert cursor.fetchone() is not None
    finally:
        conn.close()


def test_migrations_are_idempotent():
    # Run migrations first time
    run_migrations()

    # Run migrations second time (should be idempotent and not fail)
    run_migrations()

    # Count how many migration files exist
    from storage.migrations import MIGRATIONS_DIR

    expected_count = 0
    if os.path.exists(MIGRATIONS_DIR):
        expected_count = len(
            [f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")]
        )

    conn = get_db_connection()
    try:
        applied = get_applied_versions(conn)
        assert len(applied) == expected_count
        for i in range(1, expected_count + 1):
            assert i in applied
    finally:
        conn.close()


def test_concurrent_migrations_same_db():
    """Verify that multiple concurrent callers of run_migrations() against the same DB succeed without locking."""
    import concurrent.futures

    errors = []

    def _worker_migrate():
        try:
            run_migrations()
        except Exception as e:
            errors.append(e)

    # Spawn 8 threads simultaneously attempting migration
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker_migrate) for _ in range(8)]
        concurrent.futures.wait(futures)

    assert not errors, f"Concurrent migrations encountered errors: {errors}"

    conn = get_db_connection()
    try:
        applied = get_applied_versions(conn)
        assert len(applied) >= 3
        # Verify no duplicate entries in schema_migrations
        cursor = conn.cursor()
        cursor.execute(
            "SELECT version, COUNT(*) FROM schema_migrations GROUP BY version HAVING COUNT(*) > 1"
        )
        duplicates = cursor.fetchall()
        assert not duplicates, (
            f"Found duplicate migration version records: {duplicates}"
        )
    finally:
        conn.close()


def test_concurrent_api_and_worker_startup_against_same_db():
    """Verify that concurrent API migration and worker embedding cache init/access operate safely without locks."""
    import concurrent.futures
    from services.embedding_service import (
        EmbeddingService,
        _save_embeddings_to_cache_bulk,
        _get_cached_embeddings_bulk,
    )

    errors = []

    def _api_task():
        try:
            run_migrations()
        except Exception as e:
            errors.append(("api", e))

    def _worker_task(worker_id: int):
        try:
            _ = EmbeddingService(model_name="test-concurrent-model")
            records = [
                {
                    "chunk_hash": f"chunk_{worker_id}_{i}",
                    "embedding": [0.1 * i, 0.2 * i],
                    "model_name": "test-concurrent-model",
                    "model_version": "1.5",
                }
                for i in range(5)
            ]
            _save_embeddings_to_cache_bulk(records)
            res = _get_cached_embeddings_bulk(
                [f"chunk_{worker_id}_0"], "test-concurrent-model"
            )
            assert f"chunk_{worker_id}_0" in res
        except Exception as e:
            errors.append((f"worker_{worker_id}", e))

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(_api_task),
            executor.submit(_api_task),
            executor.submit(_worker_task, 1),
            executor.submit(_worker_task, 2),
            executor.submit(_worker_task, 3),
            executor.submit(_api_task),
        ]
        concurrent.futures.wait(futures)

    assert not errors, f"Concurrent API/Worker startup encountered errors: {errors}"
