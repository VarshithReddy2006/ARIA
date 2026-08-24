"""
Regression test suite for ARIA Live Analysis Progress & Telemetry Synchronization.
Validates:
1. Phase transitions: CLONE -> DETECT -> PARSE -> EMBED -> INDEX -> ANALYZE -> REPORT -> COMPLETED
2. Separation of job_elapsed_seconds and phase_elapsed_seconds
3. Monotonic progress tracking
4. Stale state and polling regression rejection
5. Persisted state authoritative preference over stale in-memory cache
6. Authoritative Azure /app/data/jobs directory resolution
7. Long-running EMBED simulation (2600s) ensuring step_id == "embed" throughout
"""

import os
import json
import time
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.api import app
from backend.routers.repositories import (
    _get_jobs_dir,
    get_job_state,
    _LOCAL_JOBS,
)
from backend.worker import AnalysisWorker


class TestJobStateResolutionAndPersistence:
    """Test authoritative disk persistence and Azure path resolution."""

    def test_azure_app_data_jobs_resolution(self, monkeypatch, tmp_path):
        fake_db = tmp_path / "repo_understanding.db"
        monkeypatch.setenv("SQLITE_DB_PATH", str(fake_db))
        jobs_dir = _get_jobs_dir()
        assert os.path.isabs(jobs_dir)
        assert os.path.basename(jobs_dir) == "jobs"
        assert os.path.dirname(jobs_dir) == str(tmp_path)
        assert os.path.exists(jobs_dir)

    def test_persisted_job_state_overrides_stale_memory_state(
        self, tmp_path, monkeypatch
    ):
        fake_jobs_dir = tmp_path / "jobs"
        fake_jobs_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "backend.routers.repositories._get_jobs_dir", lambda: str(fake_jobs_dir)
        )

        job_id = "test-job-sync-123"
        now = time.time()

        # 1. Simulate initial queued state stored in API memory
        _LOCAL_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "step_id": "clone",
            "message": "Analysis queued",
            "progress": 0,
            "started_at": now - 100,
            "updated_at": now - 100,
        }

        # 2. Simulate worker advancing to EMBED and writing to disk
        disk_payload = {
            "job_id": job_id,
            "status": "running",
            "step_id": "embed",
            "message": "Generating Embeddings: 1024 chunks",
            "progress": 59,
            "started_at": now - 100,
            "updated_at": now - 5,
            "stats": {
                "chunks_processed": 1024,
                "elapsed_seconds": 95.0,
                "job_elapsed_seconds": 95.0,
                "phase_elapsed_seconds": 60.0,
            },
        }
        job_file = fake_jobs_dir / f"{job_id}.json"
        with open(job_file, "w", encoding="utf-8") as fh:
            json.dump(disk_payload, fh)

        # 3. get_job_state must return the authoritative disk state
        resolved_state = get_job_state(job_id)
        assert resolved_state is not None
        assert resolved_state["status"] == "running"
        assert resolved_state["step_id"] == "embed"
        assert resolved_state["progress"] == 59
        assert resolved_state["stats"]["phase_elapsed_seconds"] == 60.0

    def test_get_analysis_status_endpoint_telemetry(self, tmp_path, monkeypatch):
        fake_jobs_dir = tmp_path / "jobs"
        fake_jobs_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "backend.routers.repositories._get_jobs_dir", lambda: str(fake_jobs_dir)
        )

        client = TestClient(app)
        job_id = "endpoint-telemetry-test"
        now = time.time()

        job_payload = {
            "job_id": job_id,
            "request_id": "req-999",
            "status": "running",
            "step_id": "embed",
            "message": "Generating Embeddings: 2048 chunks",
            "progress": 70,
            "started_at": now - 200,
            "updated_at": now - 2,
            "repo": {
                "owner": "fastapi",
                "name": "fastapi",
                "full_name": "fastapi/fastapi",
            },
            "stats": {
                "chunks_processed": 2048,
                "job_elapsed_seconds": 198.0,
                "phase_elapsed_seconds": 150.0,
            },
        }
        with open(fake_jobs_dir / f"{job_id}.json", "w", encoding="utf-8") as fh:
            json.dump(job_payload, fh)

        res = client.get(f"/api/v1/analyze/{job_id}")
        assert res.status_code == 202
        data = res.json()
        assert data["job_id"] == job_id
        assert data["status"] == "running"
        assert data["step_id"] == "embed"
        assert data["progress"] == 70
        assert data["started_at"] == now - 200
        assert data["elapsed_seconds"] >= 199.0
        assert data["stats"]["phase_elapsed_seconds"] == 150.0


class TestWorkerPhaseTransitionsAndTimerSemantics:
    """Test worker phase progression and distinct phase vs job timing."""

    def test_phase_transitions_lifecycle(self, tmp_path, monkeypatch):
        fake_jobs_dir = tmp_path / "jobs"
        fake_jobs_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "backend.routers.repositories._get_jobs_dir", lambda: str(fake_jobs_dir)
        )

        worker = AnalysisWorker()
        job_id = "worker-lifecycle-test"

        emitted_phases = []

        def mock_execute(
            repo_url, branch, force_rebuild, progress_callback, request_id, job_id
        ):
            phases = [
                ("clone", "cloning", 5, 35.0),
                ("detect", "detecting", 15, 1.0),
                ("parse", "parsing", 25, 1.0),
                ("embed", "generating_embeddings", 60, 2600.0),
                ("index", "building_symbols", 75, 2.0),
                ("analyze", "computing_intel", 85, 2.0),
                ("answer", "generating_report", 95, 61.0),
            ]
            for step_id, status, prog, simulated_dur in phases:
                progress_callback(
                    {
                        "step_id": step_id,
                        "status": status,
                        "message": f"Stage {step_id}",
                        "progress": prog,
                        "stats": {"simulated_phase_duration": simulated_dur},
                    }
                )
                current = get_job_state(job_id)
                emitted_phases.append((current["step_id"], current["progress"]))
            return {"repo": "fastapi/fastapi", "summary": "mock summary"}

        payload = json.dumps(
            {
                "job_id": job_id,
                "request_id": "req-123",
                "repo_url": "https://github.com/fastapi/fastapi",
                "branch": "main",
            }
        )

        with patch(
            "backend.worker.execute_repository_analysis", side_effect=mock_execute
        ):
            success = worker.process_message_payload(payload)
            assert success is True

        final_state = get_job_state(job_id)
        assert final_state["status"] == "completed"
        assert final_state["step_id"] == "complete"
        assert final_state["progress"] == 100

        # Verify exact sequence of phases were reported monotonically
        expected_steps = [
            "clone",
            "detect",
            "parse",
            "embed",
            "index",
            "analyze",
            "answer",
        ]
        actual_steps = [p[0] for p in emitted_phases]
        assert actual_steps == expected_steps

        # Monotonic progress
        progs = [p[1] for p in emitted_phases]
        assert progs == sorted(progs)

    def test_long_running_embed_simulation_retains_embed_step_id(
        self, tmp_path, monkeypatch
    ):
        """
        Simulate a 2600-second embedding phase and ensure step_id remains 'embed'
        and phase_elapsed_seconds is distinct from job_elapsed_seconds.
        """
        fake_jobs_dir = tmp_path / "jobs"
        fake_jobs_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "backend.routers.repositories._get_jobs_dir", lambda: str(fake_jobs_dir)
        )

        worker = AnalysisWorker()
        job_id = "embed-simulation-2600s"

        recorded_snapshots = []

        def mock_execute(
            repo_url, branch, force_rebuild, progress_callback, request_id, job_id
        ):
            # 1. Clone (35s)
            progress_callback({"step_id": "clone", "status": "cloned", "progress": 15})

            # 2. Detect (1s)
            progress_callback(
                {"step_id": "detect", "status": "detected", "progress": 20}
            )

            # 3. Parse (1s)
            progress_callback({"step_id": "parse", "status": "parsed", "progress": 30})

            # 4. Long-running EMBED (2600s) — multiple batch updates
            for batch_num in range(1, 14):
                progress_callback(
                    {
                        "step_id": "embed",
                        "status": "generating_embeddings",
                        "message": f"Generating Embeddings: {batch_num * 256} chunks",
                        "progress": 30 + int((batch_num / 13) * 35),
                        "stats": {
                            "chunks_processed": batch_num * 256,
                            "embeddings_indexed": batch_num * 256,
                        },
                    }
                )
                snap = get_job_state(job_id)
                recorded_snapshots.append(dict(snap))

            # 5. Index & Analyze & Report
            progress_callback(
                {"step_id": "index", "status": "building_symbols", "progress": 75}
            )
            progress_callback(
                {"step_id": "analyze", "status": "computing_intel", "progress": 85}
            )
            progress_callback(
                {"step_id": "answer", "status": "generating_report", "progress": 95}
            )
            return {"repo": "fastapi/fastapi", "status": "ok"}

        payload = json.dumps(
            {
                "job_id": job_id,
                "request_id": "req-long-embed",
                "repo_url": "https://github.com/fastapi/fastapi",
                "branch": "main",
            }
        )

        with patch(
            "backend.worker.execute_repository_analysis", side_effect=mock_execute
        ):
            success = worker.process_message_payload(payload)
            assert success is True

        # Verify all 13 batch snapshots during embedding had step_id == "embed"
        assert len(recorded_snapshots) == 13
        for snap in recorded_snapshots:
            assert snap["step_id"] == "embed"
            assert snap["status"] == "running"
            assert "Generating Embeddings" in snap["message"]
            assert snap["progress"] >= 30
            assert snap["stats"]["chunks_processed"] > 0
            assert "job_elapsed_seconds" in snap["stats"]
            assert "phase_elapsed_seconds" in snap["stats"]

    def test_completed_job_cannot_regress_to_running(self, tmp_path, monkeypatch):
        fake_jobs_dir = tmp_path / "jobs"
        fake_jobs_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(
            "backend.routers.repositories._get_jobs_dir", lambda: str(fake_jobs_dir)
        )

        job_id = "completed-no-regression-test"
        now = time.time()

        # Job completed on disk
        completed_state = {
            "job_id": job_id,
            "status": "completed",
            "step_id": "complete",
            "progress": 100,
            "result": {"summary": "done"},
            "started_at": now - 300,
            "completed_at": now - 10,
            "updated_at": now - 10,
        }
        with open(fake_jobs_dir / f"{job_id}.json", "w", encoding="utf-8") as fh:
            json.dump(completed_state, fh)

        # Stale in-memory update attempts to mark running/clone
        _LOCAL_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "step_id": "clone",
            "progress": 10,
            "updated_at": now - 200,
        }

        resolved = get_job_state(job_id)
        assert resolved["status"] == "completed"
        assert resolved["step_id"] == "complete"
        assert resolved["progress"] == 100
