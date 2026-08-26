"""Phase 0 Baseline Production-Contract Diagnostic Integration Test."""

import pytest
from starlette.testclient import TestClient

from backend.api import app
from backend.worker import AnalysisWorker
from infrastructure.job_executor import get_shared_local_queue


@pytest.fixture
def baseline_client(monkeypatch, tmp_path):
    """Sets up an isolated test environment with mocked queue and clean storage."""
    monkeypatch.setenv("AZURE_USE_MEMORY_QUEUE", "true")
    monkeypatch.setenv("JOB_EXECUTOR", "local")
    monkeypatch.setenv("APP_ENV", "test")

    # Mock github clone to return local temp repo with sample files
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "main.py").write_text(
        "import helper\ndef run():\n    helper.greet()\n", encoding="utf-8"
    )
    (repo_dir / "helper.py").write_text(
        "def greet():\n    print('hello')\n", encoding="utf-8"
    )

    from backend.dependencies import get_github_service

    gh = get_github_service()
    monkeypatch.setattr(
        gh, "clone_repository", lambda url, branch="main": str(repo_dir)
    )
    monkeypatch.setattr(gh, "get_local_repo_path", lambda repo_name: str(repo_dir))
    monkeypatch.setattr(
        gh,
        "extract_source_files",
        lambda p: [
            {
                "path": "main.py",
                "content": (repo_dir / "main.py").read_text(encoding="utf-8"),
            },
            {
                "path": "helper.py",
                "content": (repo_dir / "helper.py").read_text(encoding="utf-8"),
            },
        ],
    )

    # Clear shared local queue
    queue = get_shared_local_queue()
    while queue.receive_message(timeout=0.01) is not None:
        pass

    with TestClient(app) as client:
        yield client


def test_phase0_baseline_flow(baseline_client, monkeypatch, tmp_path):
    """Execute the end-to-end flow and record status of each step."""
    results = {}

    repo_url = "https://github.com/test-owner/test-repo"
    owner = "test-owner"
    repo = "test-repo"

    # Step 1: POST /api/v1/analyze
    try:
        resp = baseline_client.post(
            "/api/v1/analyze",
            json={"url": repo_url, "branch": "main", "force_rebuild": True},
        )
        if resp.status_code == 202:
            data = resp.json()
            job_id = data.get("job_id")
            results["POST /api/v1/analyze"] = ("[OK]", 202, f"job_id={job_id}")
        else:
            results["POST /api/v1/analyze"] = ("[FAIL]", resp.status_code, resp.text)
            job_id = None
    except Exception as exc:
        results["POST /api/v1/analyze"] = ("[FAIL]", 0, str(exc))
        job_id = None

    # Step 2: Worker processes queue message
    if job_id:
        worker = AnalysisWorker(use_memory_queue=True)
        try:
            processed = worker.run_once()
            if processed:
                results["Worker execution"] = ("[OK]", 200, "Job processed")
            else:
                results["Worker execution"] = (
                    "[WARN]",
                    404,
                    "No message in queue (local job executor ran)",
                )
        except Exception as exc:
            results["Worker execution"] = ("[FAIL]", 500, str(exc))

        # Step 3: GET /api/v1/analyze/{job_id} (Polling endpoint)
        try:
            poll_resp = baseline_client.get(f"/api/v1/analyze/{job_id}")
            if poll_resp.status_code == 200:
                poll_data = poll_resp.json()
                status = poll_data.get("status")
                results["GET /api/v1/analyze/{job_id}"] = (
                    "[OK]",
                    200,
                    f"status={status}",
                )
            else:
                results["GET /api/v1/analyze/{job_id}"] = (
                    "[FAIL]",
                    poll_resp.status_code,
                    poll_resp.text,
                )
        except Exception as exc:
            results["GET /api/v1/analyze/{job_id}"] = ("[FAIL]", 0, str(exc))

    # Step 4: GET /api/v1/analysis/{owner}/{repo}
    try:
        analysis_resp = baseline_client.get(f"/api/v1/analysis/{owner}/{repo}")
        if analysis_resp.status_code == 200:
            results["GET /api/v1/analysis/{owner}/{repo}"] = ("[OK]", 200, "Found")
        else:
            results["GET /api/v1/analysis/{owner}/{repo}"] = (
                "[FAIL]",
                analysis_resp.status_code,
                analysis_resp.text,
            )
    except Exception as exc:
        results["GET /api/v1/analysis/{owner}/{repo}"] = ("[FAIL]", 0, str(exc))

    # Step 5: Dependency Graph GET /api/v1/graph/{owner}/{repo}/full
    try:
        graph_resp = baseline_client.get(f"/api/v1/graph/{owner}/{repo}/full")
        if graph_resp.status_code == 200:
            results["GET /api/v1/graph/{owner}/{repo}/full"] = ("[OK]", 200, "Loaded")
        else:
            results["GET /api/v1/graph/{owner}/{repo}/full"] = (
                "[FAIL]",
                graph_resp.status_code,
                graph_resp.text,
            )
    except Exception as exc:
        results["GET /api/v1/graph/{owner}/{repo}/full"] = ("[FAIL]", 0, str(exc))

    # Step 6: Call Graph GET /api/v1/call-graph/{owner}/{repo}
    try:
        cg_resp = baseline_client.get(f"/api/v1/call-graph/{owner}/{repo}")
        if cg_resp.status_code == 200:
            results["GET /api/v1/call-graph/{owner}/{repo}"] = ("[OK]", 200, "Loaded")
        else:
            results["GET /api/v1/call-graph/{owner}/{repo}"] = (
                "[FAIL]",
                cg_resp.status_code,
                cg_resp.text,
            )
    except Exception as exc:
        results["GET /api/v1/call-graph/{owner}/{repo}"] = ("[FAIL]", 0, str(exc))

    # Step 7: API Surface GET /api/v1/api-surface/{owner}/{repo}
    try:
        api_resp = baseline_client.get(f"/api/v1/api-surface/{owner}/{repo}")
        if api_resp.status_code == 200:
            results["GET /api/v1/api-surface/{owner}/{repo}"] = ("[OK]", 200, "Loaded")
        else:
            results["GET /api/v1/api-surface/{owner}/{repo}"] = (
                "[FAIL]",
                api_resp.status_code,
                api_resp.text,
            )
    except Exception as exc:
        results["GET /api/v1/api-surface/{owner}/{repo}"] = ("[FAIL]", 0, str(exc))

    # Step 8: Reading Path POST /api/v1/reading-order
    try:
        ro_resp = baseline_client.post(
            "/api/v1/reading-order", json={"repo": f"{owner}/{repo}"}
        )
        if ro_resp.status_code == 200:
            results["POST /api/v1/reading-order"] = ("[OK]", 200, "Loaded")
        else:
            results["POST /api/v1/reading-order"] = (
                "[FAIL]",
                ro_resp.status_code,
                ro_resp.text,
            )
    except Exception as exc:
        results["POST /api/v1/reading-order"] = ("[FAIL]", 0, str(exc))

    # Step 9: Impact Analysis POST /api/v1/impact-analysis
    try:
        ia_resp = baseline_client.post(
            "/api/v1/impact-analysis",
            json={"repo": f"{owner}/{repo}", "issue": "Add authentication token check"},
        )
        if ia_resp.status_code == 200:
            results["POST /api/v1/impact-analysis"] = ("[OK]", 200, "Loaded")
        else:
            results["POST /api/v1/impact-analysis"] = (
                "[FAIL]",
                ia_resp.status_code,
                ia_resp.text,
            )
    except Exception as exc:
        results["POST /api/v1/impact-analysis"] = ("[FAIL]", 0, str(exc))

    print("\n--- PHASE 0 BASELINE PRODUCTION CONTRACT RESULTS ---")
    for k, v in results.items():
        print(f"{v[0]} {k} -> HTTP {v[1]} ({v[2]})")
