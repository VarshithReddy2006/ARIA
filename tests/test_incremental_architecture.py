"""Unit tests for incremental ArchitectureService build (PH2-021)."""

import pytest
import tempfile
import shutil

from services.architecture_service import ArchitectureService
from storage import JsonSnapshotStore
from core import AnalysisCache


@pytest.fixture
def temp_store_and_service():
    tmpdir = tempfile.mkdtemp()
    store = JsonSnapshotStore(base_dir=tmpdir)
    cache = AnalysisCache()
    service = ArchitectureService(
        snapshot_store=store, analysis_cache=cache, graphs_dir=tmpdir
    )
    yield service, store, tmpdir
    shutil.rmtree(tmpdir)


def test_architecture_service_incremental_updates(temp_store_and_service):
    """Verify that ArchitectureService.build_partial correctly manages cached parsed files and rebuilds graph."""
    service, store, tmpdir = temp_store_and_service
    repo_name = "test/incremental_repo"

    # 1. Full Build
    files = [
        {"path": "main.py", "content": "import utils\ndef foo(): pass"},
        {"path": "utils.py", "content": "import helper"},
        {"path": "helper.py", "content": "def run(): pass"},
    ]

    full_result = service.build_full(repo_name, files=files)
    assert full_result["status"] == "success"
    assert full_result["files_parsed"] == 3

    # Check that parsed_files snapshot is saved
    parsed_snapshot = store.load(repo_name, "parsed_files")
    assert parsed_snapshot is not None
    assert len(parsed_snapshot["parsed"]) == 3

    # Check dependency graph edges
    graph = service.graph_service.load_graph(repo_name)
    assert graph is not None
    assert graph.has_edge("main.py", "utils.py")
    assert graph.has_edge("utils.py", "helper.py")
    assert not graph.has_edge("main.py", "helper.py")

    # 2. Partial Build (modify main.py to import helper, keep utils/helper as is)
    changed_files = {"main.py"}
    new_files = [
        {"path": "main.py", "content": "import helper\ndef foo(): pass"},
        {"path": "utils.py", "content": "import helper"},
        {"path": "helper.py", "content": "def run(): pass"},
    ]

    partial_result = service.build_partial(
        repo_name, changed_files=changed_files, files=new_files
    )
    assert partial_result["status"] == "success"
    assert partial_result["files_parsed"] == 3  # all 3 files remain in registry

    # Verify that parsed_files snapshot is updated
    parsed_snapshot_updated = store.load(repo_name, "parsed_files")
    assert len(parsed_snapshot_updated["parsed"]) == 3

    # Rebuild graph should show main -> helper and utils -> helper, but main -> utils is removed
    graph_updated = service.graph_service.load_graph(repo_name)
    assert graph_updated is not None
    assert graph_updated.has_edge("main.py", "helper.py")
    assert graph_updated.has_edge("utils.py", "helper.py")
    assert not graph_updated.has_edge("main.py", "utils.py")


def test_architecture_partial_build_replaces_renamed_path(temp_store_and_service):
    service, store, _ = temp_store_and_service
    repo_name = "test/renamed_repo"
    service.build_full(
        repo_name, files=[{"path": "old_name.py", "content": "def run(): pass"}]
    )

    result = service.build_partial(
        repo_name,
        changed_files={"old_name.py", "new_name.py"},
        files=[{"path": "new_name.py", "content": "def run(): pass"}],
    )

    assert result["status"] == "success"
    parsed_paths = {
        item["file_path"] for item in store.load(repo_name, "parsed_files")["parsed"]
    }
    assert parsed_paths == {"new_name.py"}
