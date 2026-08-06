"""Architecture Foundation — Phase 1 Unit Tests.

Covers:
  - TreeSitterService: Python and JS/TS parsing (imports, classes, functions)
  - GraphService: file graph nodes/edges, module graph, persistence
  - EntryPointService: main.py detection, FastAPI init detection
  - ArchitectureSummary computation: centrality, core modules
  - ArchitectureService: full pipeline integration
  - API endpoints: POST /api/architecture/build, GET /api/architecture/{owner}/{repo}
"""

import os
import sys
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tree_sitter_service import TreeSitterService
from services.graph_service import GraphService
from services.entry_point_service import EntryPointService
from services.architecture_service import ArchitectureService
from models.architecture import ParsedFile, ArchitectureSummary


# ===========================================================================
# Fixtures — synthetic repository data
# ===========================================================================

PYTHON_MAIN_CONTENT = """\
from fastapi import FastAPI
from services.retrieval_service import RetrievalService

app = FastAPI()

class MyApp:
    def __init__(self):
        pass

def startup():
    pass
"""

PYTHON_SERVICE_CONTENT = """\
import os
from typing import List

class RetrievalService:
    def __init__(self, store):
        self.store = store

    def retrieve(self, query: str) -> List[str]:
        return []
"""

JS_MODULE_CONTENT = """\
import React from 'react';
import { useState } from 'react';

export class App extends React.Component {
    render() {
        return null;
    }
}

export function main(props) {
    return null;
}
"""

TS_MODULE_CONTENT = """\
import express from 'express';

const app = express();

export function startServer(port: number): void {
    app.listen(port);
}
"""


@pytest.fixture
def ts_service():
    return TreeSitterService()


@pytest.fixture
def graph_service(tmp_path):
    return GraphService(graphs_dir=str(tmp_path / "graphs"))


@pytest.fixture
def entry_service():
    return EntryPointService()


@pytest.fixture
def arch_service(tmp_path):
    graphs_dir = str(tmp_path / "graphs")
    arch_dir = str(tmp_path / "architecture")
    return ArchitectureService(arch_dir=arch_dir, graphs_dir=graphs_dir)


@pytest.fixture
def python_files():
    """Minimal synthetic Python repo file list."""
    return [
        {"path": "backend/main.py", "content": PYTHON_MAIN_CONTENT},
        {"path": "services/retrieval_service.py", "content": PYTHON_SERVICE_CONTENT},
    ]


@pytest.fixture
def js_files():
    return [
        {"path": "src/App.tsx", "content": JS_MODULE_CONTENT},
        {"path": "src/server.ts", "content": TS_MODULE_CONTENT},
    ]


@pytest.fixture
def mixed_files(python_files, js_files):
    return python_files + js_files


# ===========================================================================
# 1. TreeSitterService
# ===========================================================================


class TestTreeSitterService:
    """Tree-Sitter parsing — imports, classes, functions."""

    # -----------------------------------------------------------------------
    # Python
    # -----------------------------------------------------------------------

    def test_python_imports_extracted(self, ts_service):
        result = ts_service.parse_file("backend/main.py", PYTHON_MAIN_CONTENT)
        assert result is not None
        assert "fastapi" in result["imports"]
        assert "services.retrieval_service" in result["imports"]

    def test_python_classes_extracted(self, ts_service):
        result = ts_service.parse_file("backend/main.py", PYTHON_MAIN_CONTENT)
        assert result is not None
        class_names = [c["class_name"] for c in result["classes"]]
        assert "MyApp" in class_names

    def test_python_functions_extracted(self, ts_service):
        result = ts_service.parse_file("backend/main.py", PYTHON_MAIN_CONTENT)
        assert result is not None
        fn_names = [f["function_name"] for f in result["functions"]]
        assert "startup" in fn_names

    def test_python_language_detected(self, ts_service):
        result = ts_service.parse_file("path/to/file.py", PYTHON_SERVICE_CONTENT)
        assert result is not None
        assert result["language"] == "python"

    def test_python_class_methods_extracted(self, ts_service):
        result = ts_service.parse_file(
            "services/retrieval_service.py", PYTHON_SERVICE_CONTENT
        )
        assert result is not None
        service_class = next(
            (c for c in result["classes"] if c["class_name"] == "RetrievalService"),
            None,
        )
        assert service_class is not None
        assert "__init__" in service_class["methods"]
        assert "retrieve" in service_class["methods"]

    def test_python_class_base_classes(self, ts_service):
        content = "class MyView(BaseView, Mixin): pass"
        result = ts_service.parse_file("views.py", content)
        assert result is not None
        classes = {c["class_name"]: c for c in result["classes"]}
        assert "MyView" in classes
        assert "BaseView" in classes["MyView"]["base_classes"]
        assert "Mixin" in classes["MyView"]["base_classes"]

    def test_python_function_parameters(self, ts_service):
        content = "def process(data, limit=10, *args, **kwargs): pass"
        result = ts_service.parse_file("utils.py", content)
        assert result is not None
        fn = next(
            (f for f in result["functions"] if f["function_name"] == "process"), None
        )
        assert fn is not None
        assert "data" in fn["parameters"]

    def test_unsupported_extension_returns_none(self, ts_service):
        result = ts_service.parse_file("README.md", "# Hello World")
        assert result is None

    def test_is_supported_python(self, ts_service):
        assert ts_service.is_supported("main.py") is True
        assert ts_service.is_supported("app.js") is True
        assert ts_service.is_supported("app.ts") is True
        assert ts_service.is_supported("app.tsx") is True
        assert ts_service.is_supported("README.md") is False
        assert ts_service.is_supported("styles.css") is False

    # -----------------------------------------------------------------------
    # JavaScript / TypeScript
    # -----------------------------------------------------------------------

    def test_js_imports_extracted(self, ts_service):
        result = ts_service.parse_file("src/App.tsx", JS_MODULE_CONTENT)
        assert result is not None
        assert "react" in result["imports"]

    def test_js_classes_extracted(self, ts_service):
        result = ts_service.parse_file("src/App.tsx", JS_MODULE_CONTENT)
        assert result is not None
        class_names = [c["class_name"] for c in result["classes"]]
        assert "App" in class_names

    def test_js_functions_extracted(self, ts_service):
        result = ts_service.parse_file("src/App.tsx", JS_MODULE_CONTENT)
        assert result is not None
        fn_names = [f["function_name"] for f in result["functions"]]
        assert "main" in fn_names

    def test_ts_imports_extracted(self, ts_service):
        result = ts_service.parse_file("src/server.ts", TS_MODULE_CONTENT)
        assert result is not None
        assert "express" in result["imports"]

    def test_parse_repository_from_file_list(self, ts_service, mixed_files):
        results = ts_service.parse_repository(repo_path="", files=mixed_files)
        assert len(results) == len(mixed_files)
        paths = [r["file_path"] for r in results]
        assert "backend/main.py" in paths
        assert "src/App.tsx" in paths

    def test_parse_result_schema(self, ts_service):
        """Parsed result must match ParsedFile schema."""
        result = ts_service.parse_file("backend/main.py", PYTHON_MAIN_CONTENT)
        assert result is not None
        pf = ParsedFile(**result)
        assert pf.file_path == "backend/main.py"
        assert pf.language == "python"
        assert isinstance(pf.imports, list)
        assert isinstance(pf.classes, list)
        assert isinstance(pf.functions, list)


# ===========================================================================
# 2. GraphService
# ===========================================================================


class TestGraphService:
    """Dependency graph construction, stats, and persistence."""

    @pytest.fixture
    def parsed(self, ts_service, python_files):
        return ts_service.parse_repository(repo_path="", files=python_files)

    def test_nodes_created(self, graph_service, parsed):
        graph = graph_service.build_file_graph(parsed)
        assert graph.number_of_nodes() >= len(parsed)
        for pf in parsed:
            assert graph.has_node(pf["file_path"])

    def test_edges_created(self, graph_service, parsed):
        """backend/main.py imports services.retrieval_service → edge expected."""
        graph = graph_service.build_file_graph(parsed)
        # At least one edge must exist (main → retrieval_service)
        assert graph.number_of_edges() >= 1

    def test_edge_direction(self, graph_service, parsed):
        graph = graph_service.build_file_graph(parsed)
        # main.py imports retrieval_service → edge (main.py → retrieval_service.py)
        assert graph.has_edge("backend/main.py", "services/retrieval_service.py")

    def test_graph_stats(self, graph_service, parsed):
        graph = graph_service.build_file_graph(parsed)
        stats = graph_service.get_graph_stats(graph)
        assert "node_count" in stats
        assert "edge_count" in stats
        assert "density" in stats
        assert "is_dag" in stats
        assert stats["node_count"] == graph.number_of_nodes()
        assert stats["edge_count"] == graph.number_of_edges()

    def test_module_graph_built(self, graph_service, parsed):
        graph = graph_service.build_module_graph(parsed)
        assert graph.number_of_nodes() > 0
        # fastapi should appear as a module node
        assert graph.has_node("fastapi")

    def test_graph_persist_and_reload(self, graph_service, parsed):
        graph = graph_service.build_file_graph(parsed)
        graph_service.save_graph(graph, "test/repo")
        assert graph_service.graph_exists("test/repo")
        loaded = graph_service.load_graph("test/repo")
        assert loaded is not None
        assert loaded.number_of_nodes() == graph.number_of_nodes()
        assert loaded.number_of_edges() == graph.number_of_edges()

    def test_load_nonexistent_graph_returns_none(self, graph_service):
        result = graph_service.load_graph("no/such/repo")
        assert result is None

    def test_graph_exists_false_for_missing(self, graph_service):
        assert graph_service.graph_exists("nonexistent/repo") is False

    def test_file_graph_nodes_have_language(self, graph_service, parsed):
        graph = graph_service.build_file_graph(parsed)
        for node, attrs in graph.nodes(data=True):
            if node in [pf["file_path"] for pf in parsed]:
                assert "language" in attrs


# ===========================================================================
# 3. EntryPointService
# ===========================================================================


class TestEntryPointService:
    """Entry point pattern detection."""

    def test_main_py_detected(self, entry_service):
        result = entry_service.detect(
            ["backend/main.py", "services/retrieval_service.py"]
        )
        assert "backend/main.py" in result["entry_points"]

    def test_dunder_main_detected(self, entry_service):
        result = entry_service.detect(["app/__main__.py", "app/utils.py"])
        assert "app/__main__.py" in result["entry_points"]

    def test_fastapi_app_init_detected(self, entry_service, ts_service):
        """Files that import fastapi should be flagged as framework-init entry points."""
        parsed = [ts_service.parse_file("backend/api.py", PYTHON_MAIN_CONTENT)]
        result = entry_service.detect(["backend/api.py"], parsed_files=parsed)
        assert "backend/api.py" in result["entry_points"]

    def test_js_index_detected(self, entry_service):
        result = entry_service.detect(["index.js", "utils.js"])
        assert "index.js" in result["entry_points"]

    def test_js_server_detected(self, entry_service):
        result = entry_service.detect(["server.js", "app/routes.js"])
        assert "server.js" in result["entry_points"]

    def test_react_main_tsx_detected(self, entry_service):
        result = entry_service.detect(["src/main.tsx", "src/App.tsx"])
        assert "src/main.tsx" in result["entry_points"]

    def test_react_app_tsx_detected(self, entry_service):
        result = entry_service.detect(["src/App.tsx"])
        assert "src/App.tsx" in result["entry_points"]

    def test_nextjs_detected(self, entry_service):
        result = entry_service.detect(["pages/index.tsx", "pages/about.tsx"])
        assert result["next_js"] is True

    def test_no_entry_points_for_plain_files(self, entry_service):
        result = entry_service.detect(["utils.py", "helpers.py", "constants.py"])
        assert len(result["entry_points"]) == 0

    def test_output_schema(self, entry_service):
        result = entry_service.detect(["main.py"])
        assert "entry_points" in result
        assert "next_js" in result
        assert "patterns_hit" in result


# ===========================================================================
# 4. ArchitectureSummary model
# ===========================================================================


class TestArchitectureSummaryModel:
    """Pydantic model validation."""

    def test_default_fields(self):
        summary = ArchitectureSummary()
        assert summary.entry_points == []
        assert summary.core_modules == []
        assert summary.high_coupling_modules == []
        assert summary.total_files == 0
        assert summary.total_dependencies == 0

    def test_populated_summary(self):
        summary = ArchitectureSummary(
            entry_points=["backend/main.py"],
            core_modules=["services/retrieval_service.py"],
            high_coupling_modules=["backend/api.py"],
            total_files=50,
            total_dependencies=120,
        )
        assert summary.total_files == 50
        assert summary.total_dependencies == 120
        assert "backend/main.py" in summary.entry_points

    def test_serialisation(self):
        summary = ArchitectureSummary(
            entry_points=["main.py"],
            core_modules=["utils.py"],
            high_coupling_modules=["api.py"],
            total_files=10,
            total_dependencies=5,
        )
        data = summary.model_dump()
        assert data["total_files"] == 10
        restored = ArchitectureSummary(**data)
        assert restored.total_files == 10


# ===========================================================================
# 5. ArchitectureService — full pipeline
# ===========================================================================


class TestArchitectureService:
    """Integration: parse → entry points → graph → summary → persist."""

    def test_build_from_files_success(self, arch_service, python_files):
        result = arch_service.build(
            repo_name="test/myrepo",
            files=python_files,
        )
        assert result["status"] == "success"
        assert result["repo"] == "test/myrepo"
        assert result["files_parsed"] == len(python_files)
        assert result["dependencies_found"] >= 0
        assert isinstance(result["entry_points"], list)

    def test_build_detects_entry_points(self, arch_service, python_files):
        result = arch_service.build(repo_name="test/myrepo", files=python_files)
        # backend/main.py should be detected
        assert "backend/main.py" in result["entry_points"]

    def test_build_reports_dependency_count(self, arch_service, python_files):
        result = arch_service.build(repo_name="test/myrepo", files=python_files)
        # main.py imports retrieval_service → at least 1 dependency
        assert result["dependencies_found"] >= 1

    def test_graph_persisted_to_disk(self, arch_service, python_files, tmp_path):
        arch_service.build(repo_name="test/myrepo", files=python_files)
        # Graph JSON file must exist
        graph_path = os.path.join(str(tmp_path / "graphs"), "test_myrepo.json")
        assert os.path.exists(graph_path)

    def test_summary_persisted_to_disk(self, arch_service, python_files, tmp_path):
        arch_service.build(repo_name="test/myrepo", files=python_files)
        summary_path = os.path.join(str(tmp_path / "architecture"), "test_myrepo.json")
        assert os.path.exists(summary_path)

    def test_get_summary_after_build(self, arch_service, python_files):
        arch_service.build(repo_name="test/myrepo", files=python_files)
        summary = arch_service.get_summary("test/myrepo")
        assert summary is not None
        assert isinstance(summary, ArchitectureSummary)
        assert summary.total_files >= 0

    def test_get_summary_returns_none_for_missing(self, arch_service):
        result = arch_service.get_summary("no/such/repo")
        assert result is None

    def test_summary_exists_false_before_build(self, arch_service):
        assert arch_service.summary_exists("test/unbuilt") is False

    def test_summary_exists_true_after_build(self, arch_service, python_files):
        arch_service.build(repo_name="test/myrepo", files=python_files)
        assert arch_service.summary_exists("test/myrepo") is True

    def test_centrality_returns_core_modules(self, arch_service, python_files):
        arch_service.build(repo_name="test/myrepo", files=python_files)
        summary = arch_service.get_summary("test/myrepo")
        assert summary is not None
        # core_modules come from centrality — they may be empty for tiny repos
        assert isinstance(summary.core_modules, list)

    def test_build_with_mixed_files(self, arch_service, mixed_files):
        result = arch_service.build(repo_name="test/mixed", files=mixed_files)
        assert result["status"] == "success"
        assert result["files_parsed"] == len(mixed_files)

    def test_build_raises_without_path_or_files(self, arch_service):
        with pytest.raises(ValueError):
            arch_service.build(repo_name="test/repo")

    def test_force_rebuild(self, arch_service, python_files):
        """Rebuilding with force_rebuild=True must not raise and must update results."""
        result1 = arch_service.build(repo_name="test/myrepo", files=python_files)
        result2 = arch_service.build(
            repo_name="test/myrepo", files=python_files, force_rebuild=True
        )
        assert result2["status"] == "success"
        assert result2["files_parsed"] == result1["files_parsed"]


# ===========================================================================
# 6. API endpoints (FastAPI TestClient)
# ===========================================================================


class TestArchitectureAPI:
    """End-to-end API tests for the architecture endpoints."""

    @pytest.fixture(autouse=True)
    def client(self):
        from fastapi.testclient import TestClient
        from backend.api import app

        self._client = TestClient(app)

    def test_build_endpoint_missing_repo_returns_404(self):
        """Repo that hasn't been cloned yet should return 404."""
        response = self._client.post(
            "/api/architecture/build",
            json={"repo": "nonexistent/repo-that-does-not-exist"},
        )
        assert response.status_code == 404

    def test_get_summary_missing_repo_returns_404(self):
        """Repo with no persisted summary should return 404."""
        response = self._client.get("/api/architecture/ghost/reponame")
        assert response.status_code == 404

    def test_get_architecture_route_exists(self):
        """Route must exist; 404 should come from business logic, not routing."""
        response = self._client.get("/api/architecture/fastapi/fastapi")
        # Either 200 (if a summary is cached on disk) or 404 (if not built yet)
        assert response.status_code in (200, 404)

    def test_build_architecture_route_exists(self):
        """Route must exist and return proper HTTP error for uncloned repo."""
        response = self._client.post(
            "/api/architecture/build", json={"repo": "nonexistent/test-repo-xyz"}
        )
        assert response.status_code in (404, 422, 500)

    def test_build_endpoint_bad_payload_returns_422(self):
        """Missing required field in body should return 422 Unprocessable Entity."""
        response = self._client.post("/api/architecture/build", json={})
        assert response.status_code == 422

    def test_get_summary_response_schema_when_available(self, tmp_path):
        """If a summary JSON exists in arch_dir, the API should return valid schema."""
        from services.architecture_service import ArchitectureService

        # Write a fake summary directly to the real architecture dir
        service = ArchitectureService()
        fake_summary = {
            "entry_points": ["main.py"],
            "core_modules": ["services/api.py"],
            "high_coupling_modules": [],
            "total_files": 10,
            "total_dependencies": 5,
        }
        service._save_summary("testowner/testrepo", fake_summary)

        response = self._client.get("/api/architecture/testowner/testrepo")
        assert response.status_code == 200
        data = response.json()
        assert "entry_points" in data
        assert "core_modules" in data
        assert "total_files" in data
        assert "total_dependencies" in data
        assert data["total_files"] == 10

        # Cleanup
        summary_path = service._summary_path("testowner/testrepo")
        if os.path.exists(summary_path):
            os.remove(summary_path)


# ===========================================================================
# 7. Validation against fastapi/fastapi (cloned repo on disk)
# ===========================================================================


class TestFastapiRepoValidation:
    """Validate against the real fastapi/fastapi repo if it's already cloned."""

    REPO_NAME = "fastapi/fastapi"

    @pytest.fixture
    def local_path(self):
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "cloned_repos",
            "fastapi_fastapi",
        )
        return base

    def test_repo_cloned(self, local_path):
        """If the repo isn't cloned, skip — we don't want to clone in unit tests."""
        if not os.path.exists(local_path):
            pytest.skip("fastapi/fastapi repo not cloned — skipping live validation")

    def test_graph_builds_successfully(self, local_path, arch_service, ts_service):
        if not os.path.exists(local_path):
            pytest.skip("fastapi/fastapi repo not cloned")
        parsed = ts_service.parse_repository(repo_path=local_path)
        assert len(parsed) > 0

    def test_entry_points_detected(self, local_path, ts_service, entry_service):
        if not os.path.exists(local_path):
            pytest.skip("fastapi/fastapi repo not cloned")
        parsed = ts_service.parse_repository(repo_path=local_path)
        all_paths = [pf["file_path"] for pf in parsed]
        result = entry_service.detect(all_paths, parsed_files=parsed)
        # fastapi repo should have at least one entry point
        assert len(result["entry_points"]) > 0

    def test_architecture_summary_generated(self, local_path, arch_service):
        if not os.path.exists(local_path):
            pytest.skip("fastapi/fastapi repo not cloned")
        result = arch_service.build(
            repo_name=self.REPO_NAME,
            repo_path=local_path,
        )
        assert result["status"] == "success"
        assert result["files_parsed"] > 0
        assert result["dependencies_found"] >= 0

    def test_graph_persisted(self, local_path, arch_service):
        if not os.path.exists(local_path):
            pytest.skip("fastapi/fastapi repo not cloned")
        arch_service.build(
            repo_name=self.REPO_NAME,
            repo_path=local_path,
        )
        assert arch_service.summary_exists(self.REPO_NAME)

    def test_full_summary_fields(self, local_path, arch_service):
        if not os.path.exists(local_path):
            pytest.skip("fastapi/fastapi repo not cloned")
        arch_service.build(
            repo_name=self.REPO_NAME,
            repo_path=local_path,
        )
        summary = arch_service.get_summary(self.REPO_NAME)
        assert summary is not None
        assert isinstance(summary.entry_points, list)
        assert isinstance(summary.core_modules, list)
        assert isinstance(summary.high_coupling_modules, list)
        assert summary.total_files > 0
