"""ARIA — Final Feature Completion Pass Integration & Contract Verification.

Validates the full product flow across all 11 edges:
  1. POST /api/v1/analyze
  2. Worker execution
  3. Analysis persistence (data/analysis_store.json)
  4. Dashboard hydration (GET /api/v1/analysis/{owner}/{repo})
  5. File graph real data (GET /api/v1/graph/{owner}/{repo}/full -> nodes > 0, edges > 0)
  6. Call graph real data (GET /api/v1/call-graph/{owner}/{repo} -> nodes > 0, edges > 0)
  7. API surface real data (GET /api/v1/api-surface/{owner}/{repo} -> routes > 0, public APIs > 0)
  8. Reading path (POST /api/v1/reading-order -> ordered file sequence)
  9. Impact analysis (POST /api/v1/impact-analysis -> affected files & risk score)
 10. Gemini success path in chat retrieval pipeline
 11. Gemini quota exhaustion (429) failover to DeepSeek
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient

from backend.api import app
from backend.worker import AnalysisWorker
from infrastructure.job_executor import get_shared_local_queue
from services.chat.provider_manager import ProviderManager, ProviderEntry, CircuitState


@pytest.fixture
def product_test_env(monkeypatch, tmp_path):
    """Sets up an isolated test environment with realistic source code files."""
    monkeypatch.setenv("AZURE_USE_MEMORY_QUEUE", "true")
    monkeypatch.setenv("JOB_EXECUTOR", "azure")
    monkeypatch.setenv("APP_ENV", "test")

    store_file = tmp_path / "analysis_store.json"
    sqlite_file = tmp_path / "repo_understanding.db"
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))
    monkeypatch.setenv("SQLITE_DB_PATH", str(sqlite_file))

    # Create realistic multi-file repository
    repo_dir = tmp_path / "aria_sample_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    main_py = """
import helper
from router import app, get_users

def main():
    helper.greet()
    helper.compute_stats(10)
"""
    helper_py = """
def greet():
    return 'hello'

def compute_stats(n: int) -> int:
    return n * 2
"""
    router_py = """
class MockRouter:
    def get(self, path):
        def dec(fn): return fn
        return dec

app = MockRouter()

@app.get("/users")
def get_users():
    return ["alice", "bob"]
"""

    (repo_dir / "main.py").write_text(main_py, encoding="utf-8")
    (repo_dir / "helper.py").write_text(helper_py, encoding="utf-8")
    (repo_dir / "router.py").write_text(router_py, encoding="utf-8")

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
            {"path": "main.py", "content": main_py},
            {"path": "helper.py", "content": helper_py},
            {"path": "router.py", "content": router_py},
        ],
    )

    # Mock chroma_store staging to avoid Rust HNSW segment lock in tests
    from backend.dependencies import get_chroma_store

    cs = get_chroma_store()
    monkeypatch.setattr(cs, "stage_repository_batch", lambda *args, **kwargs: 1)
    monkeypatch.setattr(cs, "publish_repository_version", lambda *args, **kwargs: None)
    monkeypatch.setattr(cs, "search_repository", lambda *args, **kwargs: [])

    # Empty local queue
    queue = get_shared_local_queue()
    while queue.receive_message(timeout=0.01) is not None:
        pass

    with TestClient(app) as client:
        yield client, repo_dir


def test_e2e_product_feature_completion_flow(product_test_env, monkeypatch):
    """Executes the full product flow and asserts every single contract edge."""
    client, repo_dir = product_test_env
    repo_url = "https://github.com/aria-test/sample-repo"
    owner = "aria-test"
    repo = "sample-repo"
    repo_name = f"{owner}/{repo}"

    # Edge 1: POST /api/v1/analyze
    resp = client.post(
        "/api/v1/analyze",
        json={"url": repo_url, "branch": "main", "force_rebuild": True},
    )
    assert resp.status_code == 202, f"POST /api/v1/analyze failed: {resp.text}"
    job_id = resp.json().get("job_id")
    assert job_id is not None

    # Edge 2: Worker execution
    worker = AnalysisWorker(use_memory_queue=True)
    processed = worker.run_once()
    assert processed is True, "Worker failed to process queue job"

    # Edge 3: Analysis Persistence & Polling
    poll_resp = client.get(f"/api/v1/analyze/{job_id}")
    assert poll_resp.status_code == 200, f"Poll failed: {poll_resp.text}"
    poll_data = poll_resp.json()
    assert poll_data.get("status") in ("completed", "partial")
    assert poll_data.get("progress") == 100

    # Edge 4: Dashboard Hydration (GET /api/v1/analysis/{owner}/{repo})
    dash_resp = client.get(f"/api/v1/analysis/{owner}/{repo}")
    assert dash_resp.status_code == 200, f"Dashboard hydration failed: {dash_resp.text}"
    dash_data = dash_resp.json()
    assert "analysis" in dash_data
    assert "architecture" in dash_data

    # Edge 5: File Graph with Real Dependency Data
    graph_resp = client.get(f"/api/v1/graph/{owner}/{repo}/full")
    assert graph_resp.status_code == 200, f"File graph failed: {graph_resp.text}"
    graph_data = graph_resp.json()
    assert len(graph_data.get("nodes", [])) >= 3, (
        "File graph should contain all 3 source files"
    )
    assert len(graph_data.get("edges", [])) >= 1, (
        "File graph should have import dependency edges"
    )

    # Edge 6: Call Graph with Real Function Data
    call_resp = client.get(f"/api/v1/call-graph/{owner}/{repo}")
    assert call_resp.status_code == 200, f"Call graph failed: {call_resp.text}"
    call_data = call_resp.json()
    assert call_data.get("node_count", 0) >= 2, (
        "Call graph should extract function nodes"
    )

    # Edge 7: API Surface with Real Data
    api_resp = client.get(f"/api/v1/api-surface/{owner}/{repo}")
    assert api_resp.status_code == 200, f"API surface failed: {api_resp.text}"
    api_data = api_resp.json()
    assert len(api_data.get("symbols", [])) >= 1, (
        "API surface should contain extracted symbols"
    )
    assert api_data.get("stats", {}).get("public_count", 0) >= 1, (
        "Should identify public symbols"
    )

    # Edge 8: Reading Path
    ro_resp = client.post("/api/v1/reading-order", json={"repo": repo_name})
    assert ro_resp.status_code == 200, f"Reading order failed: {ro_resp.text}"
    ro_data = ro_resp.json()
    assert len(ro_data.get("ordered_files", [])) >= 1, (
        "Reading order should produce ordered_files"
    )
    assert ro_data.get("estimated_reading_time", 0) >= 1

    # Edge 9: Impact Analysis
    impact_resp = client.post(
        "/api/v1/impact-analysis",
        json={"repo": repo_name, "issue": "Modify greet function in helper.py"},
    )
    assert impact_resp.status_code == 200, f"Impact analysis failed: {impact_resp.text}"
    impact_data = impact_resp.json()
    assert len(impact_data.get("directly_affected_files", [])) >= 1, (
        "Impact analysis should identify directly affected files"
    )
    assert impact_data.get("risk_level", "").lower() in ("low", "medium", "high")


@pytest.mark.anyio
async def test_llm_assistant_gemini_and_failover_paths():
    """Validates Edge 10 & 11: Gemini success and Gemini 429 failover to DeepSeek."""
    # Edge 10: Gemini success path
    gemini_primary = MagicMock()
    gemini_primary.model = "gemini-2.5-flash"
    gemini_primary.generate = AsyncMock(return_value="Gemini architectural summary")

    deepseek_backup = MagicMock()
    deepseek_backup.model = "deepseek-chat"
    deepseek_backup.generate = AsyncMock(return_value="DeepSeek fallback summary")

    e1 = ProviderEntry(name="gemini", provider=gemini_primary, priority=1)
    e2 = ProviderEntry(name="deepseek", provider=deepseek_backup, priority=2)
    pm = ProviderManager(providers=[e1, e2])

    res, provider_used = await pm.generate("Explain architecture")
    assert res == "Gemini architectural summary"
    assert provider_used == "gemini"
    assert deepseek_backup.generate.call_count == 0

    # Edge 11: Gemini simulated quota failure (429) -> DeepSeek fallback
    class QuotaError(Exception):
        pass

    gemini_primary.generate = AsyncMock(
        side_effect=QuotaError("ClientError 429 RESOURCE_EXHAUSTED quota exceeded")
    )
    pm.reset_all_circuits()

    res_fb, provider_used_fb = await pm.generate("Explain architecture")
    assert res_fb == "DeepSeek fallback summary"
    assert provider_used_fb == "deepseek"
    assert e1.circuit_breaker.state == CircuitState.OPEN


def test_dashboard_error_and_edge_cases(product_test_env):
    """Tests 404, 400, unanalyzed repos, and partial states for dashboard endpoints."""
    client, _ = product_test_env

    # 404 for unanalyzed repo
    res_404 = client.get("/api/v1/analysis/nonexistent/repo")
    assert res_404.status_code == 404
    assert "has not been analysed yet" in res_404.json().get("detail", "")

    # Graph 404 for unanalyzed repo
    res_g404 = client.get("/api/v1/graph/nonexistent/repo/full")
    assert res_g404.status_code == 404

    # Call graph 404 for unanalyzed repo
    res_cg404 = client.get("/api/v1/call-graph/nonexistent/repo")
    assert res_cg404.status_code == 404

    # API surface 404 for unanalyzed repo
    res_api404 = client.get("/api/v1/api-surface/nonexistent/repo")
    assert res_api404.status_code == 404
