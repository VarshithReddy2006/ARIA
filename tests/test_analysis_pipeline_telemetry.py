"""Regression and validation test suite for Repository Analysis Pipeline Telemetry,
Resumability, and Idempotent Qdrant Indexing.
"""

import time
import uuid
import pytest

from backend.routers.repositories import (
    emit_phase_telemetry,
    set_job_state,
    get_job_state,
)
from memory.qdrant_store import QdrantStore
from utils.memory_tracker import MemoryTracker


class TestPipelineTelemetryAndResilience:
    def test_structured_telemetry_emission(self):
        """Verify structured telemetry schema emits valid payload."""
        event = emit_phase_telemetry(
            repo="fastapi/fastapi",
            phase="embedding",
            status="running",
            items_processed=10496,
            items_total=10753,
            elapsed_seconds=160.5,
            memory_mb=468.2,
            request_id="test-req-123",
        )
        assert event["event"] == "analysis_phase"
        assert event["repo"] == "fastapi/fastapi"
        assert event["phase"] == "embedding"
        assert event["status"] == "running"
        assert event["items_processed"] == 10496
        assert event["items_total"] == 10753
        assert event["elapsed_seconds"] == 160.5
        assert event["memory_mb"] == 468.2
        assert event["request_id"] == "test-req-123"
        assert "timestamp" in event

    def test_job_state_lifecycle_transitions(self):
        """Verify clean job state tracking through all standard phases."""
        job_id = "test-job-" + uuid.uuid4().hex
        phases = [
            ("queued", "clone", 0),
            ("running", "clone", 5),
            ("running", "parse", 25),
            ("running", "chunk", 45),
            ("running", "embed", 60),
            ("running", "index", 75),
            ("running", "graphs", 85),
            ("running", "report", 95),
            ("completed", "answer", 100),
        ]
        for status, step_id, progress in phases:
            set_job_state(
                job_id,
                {
                    "job_id": job_id,
                    "status": status,
                    "step_id": step_id,
                    "progress": progress,
                    "repo": {
                        "owner": "fastapi",
                        "name": "fastapi",
                        "full_name": "fastapi/fastapi",
                    },
                },
            )
            state = get_job_state(job_id)
            assert state is not None
            assert state["status"] == status
            assert state["step_id"] == step_id
            assert state["progress"] == progress

    def test_qdrant_idempotent_indexing(self, tmp_path):
        """Verify re-indexing the same chunks does not produce duplicate points."""
        pytest.importorskip("qdrant_client")
        store = QdrantStore(persist_directory=str(tmp_path / "qdrant"))
        repo_name = "test/repo"
        version = "v1"
        chunks = [
            {
                "path": "fastapi/main.py",
                "content": "app = FastAPI()",
                "chunk_id": 0,
                "category": "production",
                "source_priority": 1.0,
                "is_entry_point": True,
            },
            {
                "path": "fastapi/routing.py",
                "content": "class APIRoute: pass",
                "chunk_id": 1,
                "category": "production",
                "source_priority": 1.0,
                "is_entry_point": False,
            },
        ]
        embeddings = [[0.1] * 384, [0.2] * 384]

        # First indexing
        staged_1 = store.stage_repository_batch(repo_name, version, chunks, embeddings)
        assert staged_1 == 2
        store.publish_repository_version(repo_name, version)

        files = store.get_indexed_files(repo_name)
        assert len(files) == 2

        # Second indexing of same version/chunks (idempotency check)
        staged_2 = store.stage_repository_batch(repo_name, version, chunks, embeddings)
        assert staged_2 == 2
        store.publish_repository_version(repo_name, version)

        # File count should still be exactly 2
        files_after = store.get_indexed_files(repo_name)
        assert len(files_after) == 2

    def test_memory_tracker_metrics(self):
        """Verify memory tracker records counts and stays within reasonable bounds."""
        tracker = MemoryTracker(repo_name="fastapi/fastapi")
        for _ in range(100):
            tracker.record_file(1024)
            tracker.record_chunk(5)
            tracker.record_embeddings_indexed(5)

        assert tracker.files_processed == 100
        assert tracker.chunks_processed == 500
        assert tracker.embeddings_indexed == 500
        rss = tracker.log_phase("test_phase")
        assert rss >= 0.0

    def test_failure_recovery_and_retry(self):
        """Verify simulated job failure updates state cleanly and subsequent retry succeeds."""
        job_id = "test-fail-" + uuid.uuid4().hex
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "status": "failed",
                "step_id": "embed",
                "error": "Simulated embedding timeout",
                "progress": 45,
            },
        )
        failed_state = get_job_state(job_id)
        assert failed_state["status"] == "failed"
        assert failed_state["error"] == "Simulated embedding timeout"

        # Retry job with new run
        set_job_state(
            job_id,
            {
                "job_id": job_id,
                "status": "running",
                "step_id": "clone",
                "error": None,
                "progress": 10,
            },
        )
        retry_state = get_job_state(job_id)
        assert retry_state["status"] == "running"
        assert retry_state["error"] is None

    def test_pipeline_timer_formatting(self):
        """Verify PipelineTimer formats clean non-overlapping report."""
        from backend.routers.repositories import PipelineTimer

        timer = PipelineTimer()
        timer.start("Clone")
        time.sleep(0.01)
        timer.stop("Clone")

        timer.start("Parse")
        time.sleep(0.01)
        timer.stop("Parse")

        report = timer.format_report()
        assert "Repository Analysis Performance Report" in report
        assert "Clone" in report
        assert "Total Active Compute" in report
