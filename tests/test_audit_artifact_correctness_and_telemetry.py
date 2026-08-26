"""Regression test suite for Phase 3, 4, 5: Artifact Correctness, Telemetry, and Timers."""

import time
from core.job_state import JobStatus, JobState
from backend.routers.repositories import PipelineTimer


def test_job_state_partial_status_and_phase_tracking():
    """Verify JobStatus.PARTIAL and phase tracking fields on JobState."""
    assert JobStatus.PARTIAL.value == "partial"

    state = JobState(
        job_id="test-job-123",
        request_id="req-123",
        repo_url="https://github.com/test-owner/test-repo",
    )

    state.transition_to(
        status=JobStatus.PARTIAL,
        step_id="complete",
        message="Analysis completed with partial artifact status",
        successful_phases=[
            "clone",
            "detect",
            "parse",
            "embed",
            "symbol_index",
            "dependency_graph",
        ],
        failed_phases=["call_graph"],
        phase_errors={"call_graph": "Tree-sitter parse timeout"},
    )

    assert state.status == JobStatus.PARTIAL
    assert state.completed_at is not None
    assert state.step_id == "complete"
    assert "call_graph" in state.failed_phases
    assert state.phase_errors["call_graph"] == "Tree-sitter parse timeout"


def test_pipeline_timer_derived_phase_durations():
    """Verify PipelineTimer aggregates Chunk, Embedding, and Chroma into Chunk_Embed_Index correctly."""
    timer = PipelineTimer()
    timer.start("Clone")
    time.sleep(0.01)
    timer.stop("Clone")

    timer.start("Chunk")
    time.sleep(0.01)
    timer.stop("Chunk")

    timer.start("Embedding")
    time.sleep(0.01)
    timer.stop("Embedding")

    timer.start("Chroma")
    time.sleep(0.01)
    timer.stop("Chroma")

    chunk_embed_index_dur = timer.get_phase_duration("Chunk_Embed_Index")
    assert chunk_embed_index_dur >= 0.03
    assert timer.get_phase_duration("Clone") >= 0.01

    report = timer.format_report()
    assert "Repository Analysis Performance Report" in report
    assert "Chunk, Embed & Index" in report
    assert "Total Active Compute" in report
