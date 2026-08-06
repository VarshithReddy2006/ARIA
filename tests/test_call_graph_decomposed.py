"""Unit tests for decomposed CallGraph service components."""

import os
import tempfile
import pytest
import networkx as nx

from models.call_graph import CallNode, CallGraphSummary
from models.symbol import Symbol
from services.call_graph.extractor import CallGraphExtractor, _node_id, _qualified, _file_dir
from services.call_graph.store import CallGraphStore
from services.call_graph.query_engine import CallGraphQueryEngine
from services.call_graph.serializer import CallGraphSerializer
from services.call_graph.builder import CallGraphBuilder


def test_extractor_helpers():
    assert _node_id("foo.py", "bar") == "foo.py::bar"
    
    sym = Symbol(
        name="my_func",
        file_path="src/main.py",
        line_number=10,
        type="function",
        language="python",
        parent_class="MyClass"
    )
    assert _qualified(sym) == "MyClass.my_func"
    assert _file_dir("a/b/c.py") == "a/b"


def test_store_and_query_engine():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = CallGraphStore(call_graphs_dir=tmpdir)
        repo_name = "test_repo"

        # Create a test graph
        G = nx.DiGraph()
        n1 = "app.py::main"
        n2 = "app.py::helper"
        G.add_node(
            n1,
            name="main",
            qualified="main",
            file_path="app.py",
            line_number=1,
            language="python",
            symbol_type="function",
            is_entry=True,
            is_recursive=False,
        )
        G.add_node(
            n2,
            name="helper",
            qualified="helper",
            file_path="app.py",
            line_number=10,
            language="python",
            symbol_type="function",
            is_entry=False,
            is_recursive=False,
        )
        G.add_edge(n1, n2, call_line=5, ambiguous=False, relationship="calls")

        store.save_graph(repo_name, G)
        assert store.graph_exists(repo_name)

        loaded_G = store.load_graph(repo_name)
        assert loaded_G is not None
        assert loaded_G.number_of_nodes() == 2
        assert loaded_G.number_of_edges() == 1

        # Query Engine
        query_engine = CallGraphQueryEngine(store=store)
        node = query_engine.get_node(repo_name, n1)
        assert node is not None
        assert node.name == "main"

        callees = query_engine.get_callees(repo_name, n1)
        assert len(callees) == 1
        assert callees[0].name == "helper"

        callers = query_engine.get_callers(repo_name, n2)
        assert len(callers) == 1
        assert callers[0].name == "main"

        blast = query_engine.get_blast_radius(repo_name, n2)
        assert n1 in blast.affected_functions

        stats = query_engine.get_stats(repo_name)
        assert stats["node_count"] == 2
        assert stats["edge_count"] == 1

        # Serializer
        serializer = CallGraphSerializer(store=store, query_engine=query_engine)
        json_res = serializer.get_graph_json(repo_name)
        assert json_res["node_count"] == 2
        assert json_res["edge_count"] == 1


def test_extractor_parse():
    extractor = CallGraphExtractor()
    content = "def foo():\n    bar()\n\ndef bar():\n    pass\n"
    all_nodes = {
        "test.py::foo": CallNode(
            node_id="test.py::foo",
            name="foo",
            qualified="foo",
            file_path="test.py",
            line_number=1,
            language="python",
            symbol_type="function",
        ),
        "test.py::bar": CallNode(
            node_id="test.py::bar",
            name="bar",
            qualified="bar",
            file_path="test.py",
            line_number=4,
            language="python",
            symbol_type="function",
        ),
    }
    defn_by_name = {
        "foo": [Symbol(name="foo", file_path="test.py", line_number=1, type="function", language="python")],
        "bar": [Symbol(name="bar", file_path="test.py", line_number=4, type="function", language="python")],
    }
    edges = extractor.extract_call_edges("test.py", content, defn_by_name, all_nodes)
    assert len(edges) == 1
    assert edges[0][0] == "test.py::foo"
    assert edges[0][1] == "test.py::bar"
