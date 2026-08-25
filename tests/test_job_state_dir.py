"""Regression test for JOB_STATE_DIR configuration and precedence."""

import json
import os
import time

from backend.routers.repositories import (
    _get_jobs_dir,
    get_job_state,
    set_job_state,
    _LOCAL_JOBS,
)


def test_job_state_dir_environment_variable_precedence(monkeypatch, tmp_path):
    """Verify JOB_STATE_DIR takes precedence over SQLITE_DB_PATH."""
    dedicated_jobs = tmp_path / "custom_jobs_dir"
    fake_sqlite = tmp_path / "somewhere_else" / "repo_understanding.db"

    monkeypatch.setenv("JOB_STATE_DIR", str(dedicated_jobs))
    monkeypatch.setenv("SQLITE_DB_PATH", str(fake_sqlite))

    resolved = _get_jobs_dir()
    assert resolved == str(dedicated_jobs)
    assert os.path.exists(dedicated_jobs)


def test_job_state_persistence_uses_job_state_dir(monkeypatch, tmp_path):
    """Verify get_job_state and set_job_state read and write to JOB_STATE_DIR."""
    custom_jobs = tmp_path / "shared_jobs"
    monkeypatch.setenv("JOB_STATE_DIR", str(custom_jobs))
    monkeypatch.setattr(
        "backend.routers.repositories._get_modal_jobs_dict", lambda: None
    )

    job_id = "test-job-dedicated-dir-001"
    _LOCAL_JOBS.pop(job_id, None)

    state = {
        "job_id": job_id,
        "status": "running",
        "progress": 42,
        "current_phase": "parsing",
        "started_at": time.time(),
    }

    set_job_state(job_id, state)

    expected_file = custom_jobs / f"{job_id}.json"
    assert expected_file.exists()

    with open(expected_file, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["job_id"] == job_id
    assert disk_data["progress"] == 42

    # Clear memory cache and ensure get_job_state reads from custom_jobs
    _LOCAL_JOBS.pop(job_id, None)
    retrieved = get_job_state(job_id)
    assert retrieved is not None
    assert retrieved["job_id"] == job_id
    assert retrieved["progress"] == 42


def test_job_state_dir_fallback_when_unset(monkeypatch, tmp_path):
    """Verify fallback behavior when JOB_STATE_DIR is unset."""
    monkeypatch.delenv("JOB_STATE_DIR", raising=False)

    fake_db = tmp_path / "db" / "repo_understanding.db"
    monkeypatch.setenv("SQLITE_DB_PATH", str(fake_db))

    resolved = _get_jobs_dir()
    expected_dir = os.path.join(os.path.dirname(os.path.abspath(str(fake_db))), "jobs")
    assert resolved == expected_dir
    assert os.path.exists(expected_dir)
