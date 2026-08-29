"""Production tests for ARIA repository analysis retrieval and self-healing job fallback.

Covers:
- Test 1: Normal Cache Hit (in-memory store -> HTTP 200)
- Test 2: Completed Job Recovery (cache miss & stale disk -> fallback to JOB_STATE_DIR -> HTTP 200)
- Test 3: Multiple Successful Jobs (selects latest timestamp)
- Test 4: Failed / Queued / Running / Partial Jobs Ignored (HTTP 404)
- Test 5: Cache Persistence Failure Resilience (write failure does not block HTTP 200)
- Test 6: API Restart Resilience (fresh memory + job in JOB_STATE_DIR -> HTTP 200)
- Test 7: Repository URL Normalization (canonical matching across HTTPS, SSH, .git)
- Test 8: Architecture Summary Signature verification
"""

import json
import logging
import os
import time
from unittest.mock import AsyncMock, patch
import pytest
from starlette.testclient import TestClient

from backend.api import app
from backend.dependencies import (
    ANALYSIS_STORE,
    AnalysisStoreDict,
    normalize_repo_name,
    persist_analysis_store_sync,
    recover_analysis_from_jobs,
)
from models.schemas import ArchitectureSummary, RepositoryAnalysis
from services.architecture_summary_service import generate_architecture_summary


def _create_mock_analysis(owner: str, name: str) -> dict:
    repo_name = f"{owner}/{name}"
    analysis = RepositoryAnalysis(
        structure={".": ["README.md", "main.py"]},
        dependencies=["fastapi", "pydantic"],
        tech_stack=["Python"],
        metadata={
            "owner": owner,
            "name": name,
            "local_path": f"/tmp/{name}",
        },
    )
    architecture = ArchitectureSummary(
        summary=f"Architecture summary for {repo_name}",
        reading_order=["main.py"],
        relationships=[],
    )
    return {
        "analysis": analysis,
        "architecture": architecture,
    }


def _create_job_file(
    directory: str,
    job_id: str,
    repo_url: str,
    status: str,
    completed_at: float,
    owner: str = "VarshithReddy2006",
    name: str = "ARIA",
    include_analysis: bool = True,
) -> str:
    repo_name = f"{owner}/{name}"
    job_data = {
        "job_id": job_id,
        "status": status,
        "repo_url": repo_url,
        "repo": {
            "owner": owner,
            "name": name,
            "url": repo_url,
        },
        "completed_at": completed_at,
        "updated_at": completed_at,
        "result": {
            "repo": repo_name,
            "owner": owner,
            "name": name,
            "status": status,
            "analysis": {
                "structure": {".": ["README.md", "main.py"]},
                "dependencies": ["fastapi", "pydantic"],
                "tech_stack": ["Python"],
                "metadata": {
                    "owner": owner,
                    "name": name,
                    "local_path": f"/tmp/{name}",
                    "job_id": job_id,
                },
            } if include_analysis else None,
            "architecture": {
                "summary": f"Architecture summary for {repo_name} from job {job_id}",
                "reading_order": ["main.py"],
                "relationships": [],
            } if include_analysis else None,
        } if include_analysis else None,
    }
    file_path = os.path.join(directory, f"{job_id}.json")
    with open(file_path, "w", encoding="utf-8") as fh:
        json.dump(job_data, fh, indent=2)
    return file_path


# ---------------------------------------------------------------------------
# Test 1: Normal Cache Hit
# ---------------------------------------------------------------------------
def test_1_normal_cache_hit():
    """Test 1: Repository exists in ANALYSIS_STORE -> returns HTTP 200."""
    owner, name = "VarshithReddy2006", "ARIA"
    repo_name = f"{owner}/{name}"
    store = AnalysisStoreDict()
    store[repo_name] = _create_mock_analysis(owner, name)

    with patch("backend.dependencies.ANALYSIS_STORE", store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", store):
            with TestClient(app) as client:
                res = client.get(f"/api/v1/analysis/{owner}/{name}")
                assert res.status_code == 200
                data = res.json()
                assert "analysis" in data
                assert "architecture" in data
                assert data["analysis"]["metadata"]["owner"] == owner
                assert data["analysis"]["metadata"]["name"] == name


# ---------------------------------------------------------------------------
# Test 2: Completed Job Recovery
# ---------------------------------------------------------------------------
def test_2_completed_job_recovery(tmp_path, monkeypatch):
    """Test 2: Repository missing from in-memory and disk cache, valid completed job exists -> HTTP 200."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    store_file = tmp_path / "analysis_store.json"
    # Empty store file
    store_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JOB_STATE_DIR", str(jobs_dir))
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    job_id = "63c7b91b6a0c440ba063e11e539626ba"
    _create_job_file(
        directory=str(jobs_dir),
        job_id=job_id,
        repo_url="https://github.com/VarshithReddy2006/ARIA",
        status="completed",
        completed_at=time.time(),
        owner="VarshithReddy2006",
        name="ARIA",
    )

    empty_store = AnalysisStoreDict()
    with patch("backend.dependencies.ANALYSIS_STORE", empty_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", empty_store):
            with TestClient(app) as client:
                res = client.get("/api/v1/analysis/VarshithReddy2006/ARIA")
                assert res.status_code == 200
                data = res.json()
                assert data["analysis"]["metadata"]["owner"] == "VarshithReddy2006"
                assert data["analysis"]["metadata"]["name"] == "ARIA"
                assert data["analysis"]["metadata"]["job_id"] == job_id
                assert "63c7b91b6a0c440ba063e11e539626ba" in data["architecture"]["summary"]

                # Verify store file was self-healed on disk
                disk_data = json.loads(store_file.read_text(encoding="utf-8"))
                assert "VarshithReddy2006/ARIA" in disk_data


# ---------------------------------------------------------------------------
# Test 3: Multiple Successful Jobs (Latest Selected)
# ---------------------------------------------------------------------------
def test_3_multiple_successful_jobs_latest_selected(tmp_path, monkeypatch):
    """Test 3: Multiple completed successful jobs exist -> select the latest completed job."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    store_file = tmp_path / "analysis_store.json"
    store_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JOB_STATE_DIR", str(jobs_dir))
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    # Older job
    _create_job_file(
        directory=str(jobs_dir),
        job_id="job_old_111",
        repo_url="https://github.com/VarshithReddy2006/ARIA",
        status="completed",
        completed_at=1000.0,
    )
    # Newer job
    _create_job_file(
        directory=str(jobs_dir),
        job_id="job_new_999",
        repo_url="https://github.com/VarshithReddy2006/ARIA",
        status="completed",
        completed_at=2000.0,
    )

    empty_store = AnalysisStoreDict()
    with patch("backend.dependencies.ANALYSIS_STORE", empty_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", empty_store):
            with TestClient(app) as client:
                res = client.get("/api/v1/analysis/VarshithReddy2006/ARIA")
                assert res.status_code == 200
                data = res.json()
                assert data["analysis"]["metadata"]["job_id"] == "job_new_999"
                assert "job_new_999" in data["architecture"]["summary"]


# ---------------------------------------------------------------------------
# Test 4: Failed / Queued / Running / Partial Jobs Ignored
# ---------------------------------------------------------------------------
def test_4_failed_and_incomplete_jobs_ignored(tmp_path, monkeypatch):
    """Test 4: Only failed, queued, running, or partial jobs exist -> returns HTTP 404."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    store_file = tmp_path / "analysis_store.json"
    store_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JOB_STATE_DIR", str(jobs_dir))
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    for status, jid in [
        ("failed", "job_fail"),
        ("queued", "job_queue"),
        ("running", "job_run"),
        ("partial", "job_part"),
    ]:
        _create_job_file(
            directory=str(jobs_dir),
            job_id=jid,
            repo_url="https://github.com/VarshithReddy2006/ARIA",
            status=status,
            completed_at=5000.0,
        )

    empty_store = AnalysisStoreDict()
    with patch("backend.dependencies.ANALYSIS_STORE", empty_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", empty_store):
            with TestClient(app) as client:
                res = client.get("/api/v1/analysis/VarshithReddy2006/ARIA")
                assert res.status_code == 404
                assert "has not been analysed yet" in res.json()["detail"]


# ---------------------------------------------------------------------------
# Test 5: Cache Persistence Failure Resilience
# ---------------------------------------------------------------------------
def test_5_cache_persistence_failure_resilience(tmp_path, monkeypatch, caplog):
    """Test 5: Recovery succeeds but disk write fails -> HTTP 200 still returned and error logged."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    store_file = tmp_path / "analysis_store.json"
    store_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JOB_STATE_DIR", str(jobs_dir))
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    _create_job_file(
        directory=str(jobs_dir),
        job_id="job_persist_err",
        repo_url="https://github.com/VarshithReddy2006/ARIA",
        status="completed",
        completed_at=time.time(),
    )

    empty_store = AnalysisStoreDict()
    with patch("backend.dependencies.ANALYSIS_STORE", empty_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", empty_store):
            with patch(
                "backend.dependencies.persist_analysis_store_sync",
                side_effect=IOError("Simulated Disk Full on Persistence"),
            ):
                with patch(
                    "backend.dependencies.logger.error"
                ) as mock_logger_error:
                    with TestClient(app) as client:
                        res = client.get("/api/v1/analysis/VarshithReddy2006/ARIA")
                        assert res.status_code == 200
                        data = res.json()
                        assert data["analysis"]["metadata"]["owner"] == "VarshithReddy2006"
                        assert data["analysis"]["metadata"]["name"] == "ARIA"
                        # Verify failure was logged with traceback/context
                        assert mock_logger_error.called
                        log_msg = mock_logger_error.call_args[0][0]
                        assert "Failed to persist self-healed analysis store" in log_msg


# ---------------------------------------------------------------------------
# Test 6: API Restart Resilience
# ---------------------------------------------------------------------------
def test_6_api_restart_resilience(tmp_path, monkeypatch):
    """Test 6: Simulated API restart (empty memory store, job exists in JOB_STATE_DIR) -> HTTP 200."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    store_file = tmp_path / "analysis_store.json"
    store_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JOB_STATE_DIR", str(jobs_dir))
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    _create_job_file(
        directory=str(jobs_dir),
        job_id="job_restart_test",
        repo_url="https://github.com/VarshithReddy2006/ARIA",
        status="completed",
        completed_at=time.time(),
    )

    # Clean cold start store
    restart_store = AnalysisStoreDict()
    with patch("backend.dependencies.ANALYSIS_STORE", restart_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", restart_store):
            with TestClient(app) as client:
                res = client.get("/api/v1/analysis/VarshithReddy2006/ARIA")
                assert res.status_code == 200
                data = res.json()
                assert data["analysis"]["metadata"]["job_id"] == "job_restart_test"


# ---------------------------------------------------------------------------
# Test 7: Repository URL Normalization
# ---------------------------------------------------------------------------
def test_7_repository_url_normalization(tmp_path, monkeypatch):
    """Test 7: Verify equivalent repository formats resolve to the same completed job."""
    jobs_dir = tmp_path / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    store_file = tmp_path / "analysis_store.json"
    store_file.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("JOB_STATE_DIR", str(jobs_dir))
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    _create_job_file(
        directory=str(jobs_dir),
        job_id="job_norm_test",
        repo_url="https://github.com/VarshithReddy2006/ARIA",
        status="completed",
        completed_at=time.time(),
    )

    # 1. Test normalize_repo_name helper directly
    assert normalize_repo_name("VarshithReddy2006/ARIA") == "varshithreddy2006/aria"
    assert (
        normalize_repo_name("https://github.com/VarshithReddy2006/ARIA")
        == "varshithreddy2006/aria"
    )
    assert (
        normalize_repo_name("https://github.com/VarshithReddy2006/ARIA.git")
        == "varshithreddy2006/aria"
    )
    assert (
        normalize_repo_name("git@github.com:VarshithReddy2006/ARIA.git")
        == "varshithreddy2006/aria"
    )
    assert (
        normalize_repo_name({"owner": "VarshithReddy2006", "name": "ARIA"})
        == "varshithreddy2006/aria"
    )

    # 2. Test recovery with various casing and formats
    empty_store = AnalysisStoreDict()
    with patch("backend.dependencies.ANALYSIS_STORE", empty_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", empty_store):
            recovered = recover_analysis_from_jobs("git@github.com:VarshithReddy2006/ARIA.git")
            assert recovered is not None
            assert recovered["analysis"].metadata["job_id"] == "job_norm_test"


# ---------------------------------------------------------------------------
# Test 8: Architecture Summary Signature
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_8_architecture_summary_signature():
    """Test 8: Verify generate_architecture_summary accepts exact signature (repo_name, tech_stack, file_paths)."""
    with patch("services.llm.ProviderFactory.get_provider") as mock_get_provider:
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = json.dumps(
            {
                "summary": "Verified Architecture Summary",
                "reading_order": ["src/main.py"],
                "relationships": [
                    {
                        "source": "src/main.py",
                        "target": "models/schemas.py",
                        "relationship_type": "imports",
                        "description": "Schema imports",
                    }
                ],
            }
        )
        mock_get_provider.return_value = mock_provider

        # Call using explicit keyword arguments matching signature
        result = await generate_architecture_summary(
            repo_name="VarshithReddy2006/ARIA",
            tech_stack=["Python", "FastAPI"],
            file_paths=["src/main.py", "models/schemas.py"],
        )

        assert isinstance(result, ArchitectureSummary)
        assert result.summary == "Verified Architecture Summary"
        assert result.reading_order == ["src/main.py"]
        assert len(result.relationships) == 1
        assert result.relationships[0].source == "src/main.py"
