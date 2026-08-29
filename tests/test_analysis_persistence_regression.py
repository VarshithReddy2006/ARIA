"""Regression tests for dynamic analysis store persistence, cross-container hydration, concurrency, and multi-process safety."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from unittest.mock import patch
import pytest
from starlette.testclient import TestClient

from backend.api import app
from backend.dependencies import (
    AnalysisStoreDict,
    persist_analysis_store_sync,
)
from models.schemas import ArchitectureSummary, RepositoryAnalysis


def _make_mock_analysis_entry(owner: str, name: str) -> dict:
    repo_name = f"{owner}/{name}"
    analysis = RepositoryAnalysis(
        structure={".": ["README.md", "main.py"]},
        dependencies=["pydantic", "fastapi"],
        tech_stack=["Python"],
        metadata={
            "owner": owner,
            "name": name,
            "local_path": f"/tmp/{name}",
        },
    )
    arch = ArchitectureSummary(
        summary=f"Architecture summary for {repo_name}",
        reading_order=["main.py"],
        relationships=[],
    )
    return {
        "analysis": analysis,
        "architecture": arch,
    }


def _worker_process_persist_task(store_path_str: str, owner: str, name: str) -> bool:
    """Worker process helper executing in an isolated operating system process."""
    from backend.dependencies import persist_analysis_store_sync

    repo_name = f"{owner}/{name}"
    store = {
        repo_name: {
            "analysis": {
                "structure": {".": ["README.md", "main.py"]},
                "dependencies": ["pydantic", "fastapi"],
                "tech_stack": ["Python"],
                "metadata": {
                    "owner": owner,
                    "name": name,
                    "local_path": f"/tmp/{name}",
                },
            },
            "architecture": {
                "summary": f"Architecture summary for {repo_name}",
                "reading_order": ["main.py"],
                "relationships": [],
            },
        }
    }
    persist_analysis_store_sync(store=store, store_path=store_path_str)
    return True


# ---------------------------------------------------------------------------
# Test A: Single repository persistence
# ---------------------------------------------------------------------------
def test_single_repository_persistence(tmp_path):
    """Test A: Verifies single repository persistence writes correct structure to disk."""
    store_file = tmp_path / "analysis_store.json"
    worker_store = {
        "VarshithReddy2006/ARIA": _make_mock_analysis_entry("VarshithReddy2006", "ARIA")
    }

    persist_analysis_store_sync(store=worker_store, store_path=str(store_file))

    assert store_file.exists()
    disk_data = json.loads(store_file.read_text(encoding="utf-8"))
    assert "VarshithReddy2006/ARIA" in disk_data
    assert (
        disk_data["VarshithReddy2006/ARIA"]["analysis"]["metadata"]["owner"]
        == "VarshithReddy2006"
    )
    assert disk_data["VarshithReddy2006/ARIA"]["analysis"]["metadata"]["name"] == "ARIA"


# ---------------------------------------------------------------------------
# Test B: Read-merge-write preserves existing repository
# ---------------------------------------------------------------------------
def test_read_merge_write_preserves_existing_repositories(tmp_path):
    """Test B: Proves a fresh worker does not overwrite existing repositories in the shared store."""
    store_file = tmp_path / "analysis_store.json"

    # Seed an existing repo on disk (simulating prior analysis)
    existing_repo = "ExampleOrg/ExampleRepo"
    initial_disk_data = {
        existing_repo: {
            "analysis": {
                "structure": {".": ["setup.py"]},
                "dependencies": ["requests"],
                "tech_stack": ["Python"],
                "metadata": {
                    "owner": "ExampleOrg",
                    "name": "ExampleRepo",
                    "local_path": "/tmp/repo",
                },
            },
            "architecture": {
                "summary": "Existing repo summary",
                "reading_order": ["setup.py"],
                "relationships": [],
            },
        }
    }
    store_file.write_text(json.dumps(initial_disk_data), encoding="utf-8")

    # Fresh worker has only the new repo
    fresh_worker_store = {
        "VarshithReddy2006/ARIA": _make_mock_analysis_entry("VarshithReddy2006", "ARIA")
    }
    persist_analysis_store_sync(store=fresh_worker_store, store_path=str(store_file))

    # Read disk store: BOTH repos must be present
    disk_data = json.loads(store_file.read_text(encoding="utf-8"))
    assert existing_repo in disk_data, f"Existing repo {existing_repo} was clobbered!"
    assert "VarshithReddy2006/ARIA" in disk_data, "New repo was not persisted!"
    assert len(disk_data) == 2


# ---------------------------------------------------------------------------
# Test C: Same-process concurrent persistence
# ---------------------------------------------------------------------------
def test_same_process_concurrent_persistence_safety(tmp_path):
    """Test C: Multiple concurrent threads passing independent snapshots do not corrupt the store."""
    store_file = tmp_path / "analysis_store.json"

    repos = [
        ("OrgA", "RepoA"),
        ("OrgB", "RepoB"),
        ("OrgC", "RepoC"),
        ("OrgD", "RepoD"),
        ("VarshithReddy2006", "ARIA"),
    ]

    def _persist_single(owner: str, name: str):
        repo_name = f"{owner}/{name}"
        thread_store = {repo_name: _make_mock_analysis_entry(owner, name)}
        persist_analysis_store_sync(store=thread_store, store_path=str(store_file))

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(_persist_single, owner, name) for owner, name in repos
        ]
        for f in futures:
            f.result()

    disk_data = json.loads(store_file.read_text(encoding="utf-8"))
    for owner, name in repos:
        repo_key = f"{owner}/{name}"
        assert repo_key in disk_data, (
            f"Missing {repo_key} in concurrent thread persistence output"
        )
    assert len(disk_data) == len(repos)


# ---------------------------------------------------------------------------
# Test D: Multi-process concurrent persistence
# ---------------------------------------------------------------------------
def test_multi_process_concurrent_persistence_safety(tmp_path):
    """Test D: Real multi-process workers concurrently persisting different repos do not lose state."""
    store_file = tmp_path / "analysis_store.json"
    store_path_str = str(store_file)

    repos = [
        ("OrgA", "RepoA"),
        ("OrgB", "RepoB"),
        ("OrgC", "RepoC"),
        ("OrgD", "RepoD"),
        ("VarshithReddy2006", "ARIA"),
    ]

    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_worker_process_persist_task, store_path_str, owner, name)
            for owner, name in repos
        ]
        for f in futures:
            res = f.result()
            assert res is True

    disk_data = json.loads(store_file.read_text(encoding="utf-8"))
    for owner, name in repos:
        repo_key = f"{owner}/{name}"
        assert repo_key in disk_data, (
            f"Missing {repo_key} in multi-process persistence output"
        )
    assert len(disk_data) == len(repos)


# ---------------------------------------------------------------------------
# Test E: Fresh API process can read Worker-persisted repository
# ---------------------------------------------------------------------------
def test_cross_process_isolated_store_hydration(tmp_path, monkeypatch):
    """Test E: Fresh API container with empty memory hydrates worker's on-disk analysis."""
    store_file = tmp_path / "analysis_store.json"
    monkeypatch.setenv("ANALYSIS_STORE_PATH", str(store_file))

    # Worker writes to disk
    worker_store = {
        "VarshithReddy2006/ARIA": _make_mock_analysis_entry("VarshithReddy2006", "ARIA")
    }
    persist_analysis_store_sync(store=worker_store, store_path=str(store_file))

    # API container starts up with completely empty in-memory store
    api_store = AnalysisStoreDict()
    assert "VarshithReddy2006/ARIA" not in dict(api_store)

    with patch("backend.dependencies.ANALYSIS_STORE", api_store):
        with patch("backend.routers.repositories.ANALYSIS_STORE", api_store):
            with TestClient(app) as client:
                res = client.get("/api/v1/analysis/VarshithReddy2006/ARIA")
                assert res.status_code == 200
                data = res.json()
                assert data["analysis"]["metadata"]["owner"] == "VarshithReddy2006"
                assert data["analysis"]["metadata"]["name"] == "ARIA"


# ---------------------------------------------------------------------------
# Test F: Persistence failure propagates and does not falsely complete
# ---------------------------------------------------------------------------
def test_persistence_failure_propagates(tmp_path):
    """Test F: Disk write failure raises an exception and is observable."""
    store_file = tmp_path / "analysis_store.json"
    worker_store = {"Fail/Repo": _make_mock_analysis_entry("Fail", "Repo")}

    with patch(
        "core.concurrency.write_json_atomic",
        side_effect=IOError("Simulated Storage Disk Full"),
    ):
        with pytest.raises(IOError, match="Simulated Storage Disk Full"):
            persist_analysis_store_sync(store=worker_store, store_path=str(store_file))
