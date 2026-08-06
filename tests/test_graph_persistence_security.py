"""Security regression tests for safe graph persistence (Task 2 / R-0014).

Verifies that:
1. `save_graph` creates safe schema-versioned JSON files, not pickle files.
2. `load_graph` correctly restores NetworkX DiGraph objects with node and edge attributes.
3. Legacy `.pkl` files are safely purged upon load attempt without executing un-pickling code.
4. `graph_exists` checks for `.json` files.
"""

import json
import os
import tempfile
import networkx as nx
import pytest

from services.graph_service import GraphService


@pytest.fixture
def tmp_graph_service():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield GraphService(graphs_dir=tmpdir)


def test_save_graph_creates_json_file(tmp_graph_service):
    g = nx.DiGraph()
    g.add_node("backend/api.py", language="python", type="file")
    g.add_node("services/graph_service.py", language="python", type="file")
    g.add_edge("backend/api.py", "services/graph_service.py", relationship="imports")

    saved_path = tmp_graph_service.save_graph(g, "owner/test-repo")

    assert saved_path.endswith(".json")
    assert os.path.exists(saved_path)
    assert not os.path.exists(saved_path.replace(".json", ".pkl"))

    with open(saved_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    assert payload.get("schema_version") == 1
    assert payload.get("repo_name") == "owner/test-repo"
    assert "graph_data" in payload


def test_load_graph_restores_digraph_attributes(tmp_graph_service):
    g = nx.DiGraph()
    g.add_node("src/index.ts", language="typescript", type="file")
    g.add_node("src/utils.ts", language="typescript", type="file")
    g.add_edge("src/index.ts", "src/utils.ts", relationship="imports")

    tmp_graph_service.save_graph(g, "owner/test-repo")
    loaded = tmp_graph_service.load_graph("owner/test-repo")

    assert loaded is not None
    assert isinstance(loaded, nx.DiGraph)
    assert loaded.number_of_nodes() == 2
    assert loaded.number_of_edges() == 1
    assert loaded.nodes["src/index.ts"]["language"] == "typescript"
    assert loaded.edges[("src/index.ts", "src/utils.ts")]["relationship"] == "imports"


def test_legacy_pkl_file_is_purged_and_not_loaded(tmp_graph_service):
    repo_name = "owner/legacy-repo"
    safe_name = repo_name.replace("/", "_")
    legacy_pkl_path = os.path.join(tmp_graph_service.graphs_dir, f"{safe_name}.pkl")

    # Create dummy legacy pickle file
    with open(legacy_pkl_path, "wb") as f:
        f.write(b"CORRUPTED_OR_MALICIOUS_PICKLE_DATA")

    assert os.path.exists(legacy_pkl_path)

    # load_graph must purge legacy file and return None if no .json exists
    loaded = tmp_graph_service.load_graph(repo_name)

    assert loaded is None
    assert not os.path.exists(legacy_pkl_path)


def test_graph_exists_checks_json(tmp_graph_service):
    repo_name = "owner/exists-repo"
    assert not tmp_graph_service.graph_exists(repo_name)

    g = nx.DiGraph()
    g.add_node("main.py")
    tmp_graph_service.save_graph(g, repo_name)

    assert tmp_graph_service.graph_exists(repo_name)
