"""End-to-end cold-start simulation test (Phase 4).

Validates that ARIA can start from a completely clean, blank environment
(zero SQLite state, zero snapshots, zero Qdrant collections, zero cached clones)
and perform full repository intelligence analysis, persistence, and idempotent re-runs.
"""

import uuid
from unittest.mock import patch, MagicMock

from backend.routers.repositories import (
    execute_repository_analysis,
)
from storage.migrations import run_migrations, get_db_connection
from storage.snapshot_store import JsonSnapshotStore
from memory.qdrant_store import QdrantStore


class TestCleanColdStartSimulation:
    def test_complete_clean_cold_start_pipeline(self, tmp_path, monkeypatch):
        """Simulate fresh container cold start and end-to-end analysis."""
        # 1. Isolate storage paths to clean temporary directory
        clean_data_dir = tmp_path / "app_data"
        clean_data_dir.mkdir()
        clean_db_path = str(clean_data_dir / "repo_understanding.db")
        clean_qdrant_dir = str(clean_data_dir / "qdrant")
        clean_snapshots_dir = str(clean_data_dir / "snapshots")

        monkeypatch.setenv("SQLITE_DB_PATH", clean_db_path)
        monkeypatch.setattr("core.config.settings.sqlite_db_path", clean_db_path)

        # 2. Run SQLite migrations from scratch
        run_migrations()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        assert "schema_migrations" in tables
        assert "embedding_cache" in tables
        conn.close()

        # 3. Create simulated clean repo
        clean_repo_dir = tmp_path / "mock_project"
        clean_repo_dir.mkdir()
        (clean_repo_dir / "main.py").write_text(
            "import utils\ndef main():\n    return utils.helper()\n",
            encoding="utf-8",
        )
        (clean_repo_dir / "utils.py").write_text(
            "def helper():\n    return 'clean_cold_start_ok'\n",
            encoding="utf-8",
        )

        repo_name = "test-org/cold-start-repo"
        repo_url = f"https://github.com/{repo_name}"
        job_id = "cold-start-job-" + uuid.uuid4().hex

        # 4. Execute repository analysis with clean vector store
        import importlib.util

        if importlib.util.find_spec("qdrant_client") is not None:
            store = QdrantStore(persist_directory=clean_qdrant_dir)
        else:
            store = MagicMock()
            store.stage_repository_batch = MagicMock(return_value=2)
            store.publish_repository_version = MagicMock()
            store.get_indexed_files = MagicMock(return_value=["main.py", "utils.py"])
        snapshot_store = JsonSnapshotStore(base_dir=clean_snapshots_dir)

        progress_history = []

        def on_progress(event):
            progress_history.append(event.get("step_id"))

        with (
            patch(
                "backend.routers.repositories.github_service.clone_repository",
                return_value=str(clean_repo_dir),
            ),
            patch(
                "backend.routers.repositories.detect_tech_stack_and_deps",
                return_value=(["Python"], ["utils"]),
            ),
            patch("backend.routers.repositories.chroma_store", store),
            patch("backend.dependencies.chroma_store", store),
            patch("backend.routers.repositories.snapshot_store", snapshot_store),
        ):
            result = execute_repository_analysis(
                repo_url=repo_url,
                branch="main",
                force_rebuild=True,
                progress_callback=on_progress,
                request_id="cold-start-req",
                job_id=job_id,
            )

            assert result["repo"] == repo_name
            assert "Python" in result["analysis"]["tech_stack"]
            assert len(progress_history) >= 5

            # Verify vectors were indexed
            indexed_files = store.get_indexed_files(repo_name)
            assert len(indexed_files) >= 1

            # 5. Test Idempotency: Second identical run produces zero duplicated state
            result_second = execute_repository_analysis(
                repo_url=repo_url,
                branch="main",
                force_rebuild=False,
                progress_callback=None,
                request_id="cold-start-req-2",
                job_id="cold-start-job-2",
            )
            assert result_second["repo"] == repo_name
            indexed_files_after = store.get_indexed_files(repo_name)
            assert len(indexed_files_after) == len(indexed_files)
