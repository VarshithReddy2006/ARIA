"""Regression and correctness tests for repository intelligence pipeline.

Verifies:
1. Primary Stack Detection (Python over CSS/HTML/docs/examples)
2. Entry-Point Detection (production package outranking docs_src examples)
3. Chunk Classification (production, test, docs, example, config, generated)
4. RAG Grounding & Intent Routing (distinguishing production entry points from examples)
5. Architecture Health & SCC cluster calculations
"""

import networkx as nx
from unittest.mock import MagicMock

from core.file_classifier import (
    classify_file,
    CATEGORY_PRODUCTION,
    CATEGORY_TEST,
    CATEGORY_DOCS,
    CATEGORY_EXAMPLE,
    CATEGORY_CONFIG,
    CATEGORY_GENERATED,
)
from services.ingestion_service import detect_tech_stack_and_deps
from services.entry_point_service import EntryPointService
from services.chunking_service import CodeChunker
from services.chat.intent_router import IntentRouter
from services.chat.intent_detector import Intent, IntentResult
from services.graph_service import GraphService
from services.report.composer import ReportComposer


# ---------------------------------------------------------------------------
# 1. Primary Stack Detection Tests
# ---------------------------------------------------------------------------


def test_language_detection_prioritizes_python_over_css_and_docs():
    """Given a Python repository containing .py, .css, .js, docs, and examples,
    Python must be selected as the primary language (tech_stack[0])."""
    files = [
        # Manifest
        {
            "path": "pyproject.toml",
            "content": '[project]\nname = "my-fastapi-app"\ndependencies = ["pydantic", "starlette"]',
        },
        # Production Python source code
        {
            "path": "fastapi/__init__.py",
            "content": "from .applications import FastAPI\n__version__ = '0.100.0'",
        },
        {
            "path": "fastapi/applications.py",
            "content": "class FastAPI:\n    def __init__(self):\n        pass\n" * 50,
        },
        {"path": "fastapi/routing.py", "content": "class APIRoute:\n    pass\n" * 40},
        {"path": "fastapi/params.py", "content": "class Param:\n    pass\n" * 30},
        # Documentation HTML & CSS assets
        {
            "path": "docs/en/docs/css/extra.css",
            "content": "body { color: red; }\n" * 500,
        },
        {
            "path": "docs/en/docs/css/material.css",
            "content": ".md-header { height: 48px; }\n" * 600,
        },
        {
            "path": "docs/en/docs/index.html",
            "content": "<html><body><h1>FastAPI</h1></body></html>\n" * 200,
        },
        # Examples under docs_src
        {
            "path": "docs_src/tutorial001/main.py",
            "content": "from fastapi import FastAPI\napp = FastAPI()",
        },
        {
            "path": "docs_src/header_params/main.py",
            "content": "from fastapi import FastAPI\napp = FastAPI()",
        },
        # Tests
        {"path": "tests/test_main.py", "content": "def test_app(): assert True"},
    ]

    tech_stack, deps = detect_tech_stack_and_deps(files)

    assert len(tech_stack) > 0
    assert tech_stack[0] == "Python", (
        f"Expected Python to be primary, got {tech_stack[0]}"
    )
    assert "pydantic" in deps
    assert "starlette" in deps


# ---------------------------------------------------------------------------
# 2. Entry-Point Detection Tests
# ---------------------------------------------------------------------------


def test_entry_point_detection_ranks_production_over_docs_and_tests():
    """Given production sources, docs_src examples, and tests,
    production source files must outrank docs_src and tests."""
    file_paths = [
        "fastapi/__init__.py",
        "fastapi/applications.py",
        "fastapi/routing.py",
        "docs_src/tutorial001/main.py",
        "docs_src/header_params/tutorial002/main.py",
        "docs_src/path_params/main.py",
        "tests/test_app.py",
        "tests/conftest.py",
    ]

    files_content = [
        {
            "path": "pyproject.toml",
            "content": '[project.scripts]\nfastapi = "fastapi.cli:main"',
        },
        {"path": "fastapi/__init__.py", "content": "from .applications import FastAPI"},
    ]

    entry_service = EntryPointService()
    result = entry_service.detect(file_paths, files_content=files_content)

    entry_points = result["entry_points"]
    assert len(entry_points) > 0
    # The top entry point must be from the production package, not docs_src or tests
    top_entry = entry_points[0]
    assert not top_entry.startswith("docs_src/"), (
        f"Top entry point should not be in docs_src: {top_entry}"
    )
    assert not top_entry.startswith("tests/"), (
        f"Top entry point should not be in tests: {top_entry}"
    )
    assert top_entry == "fastapi/__init__.py"

    # Verify example entry points are distinctly segregated
    assert "example_entry_points" in result
    for ex in result["example_entry_points"]:
        assert ex.startswith("docs_src/")


# ---------------------------------------------------------------------------
# 3. Chunk Classification Tests
# ---------------------------------------------------------------------------


def test_chunk_classification():
    """Verify files are classified correctly into architectural categories."""
    assert classify_file("fastapi/applications.py")["category"] == CATEGORY_PRODUCTION
    assert classify_file("src/app/server.ts")["category"] == CATEGORY_PRODUCTION
    assert classify_file("tests/test_router.py")["category"] == CATEGORY_TEST
    assert classify_file("docs/index.md")["category"] == CATEGORY_DOCS
    assert classify_file("docs_src/tutorial/main.py")["category"] == CATEGORY_EXAMPLE
    assert classify_file("examples/simple_server.py")["category"] == CATEGORY_EXAMPLE
    assert classify_file("pyproject.toml")["category"] == CATEGORY_CONFIG
    assert classify_file("package-lock.json")["category"] == CATEGORY_GENERATED
    assert classify_file("dist/bundle.min.js")["category"] == CATEGORY_GENERATED


def test_chunker_includes_classification_metadata():
    """Verify chunker attaches category and source_priority to each chunk."""
    chunker = CodeChunker()

    prod_chunks = chunker.chunk_file(
        "fastapi/applications.py", "class FastAPI: pass\n" * 100
    )
    assert len(prod_chunks) > 0
    assert prod_chunks[0]["category"] == CATEGORY_PRODUCTION
    assert prod_chunks[0]["source_priority"] == 1.0

    example_chunks = chunker.chunk_file(
        "docs_src/tutorial/main.py", "app = FastAPI()\n"
    )
    assert len(example_chunks) > 0
    assert example_chunks[0]["category"] == CATEGORY_EXAMPLE
    assert example_chunks[0]["source_priority"] == 0.4


# ---------------------------------------------------------------------------
# 4. RAG Grounding & Intent Routing Tests
# ---------------------------------------------------------------------------


def test_intent_router_distinguishes_production_from_examples():
    """Verify RAG IntentRouter generates context distinguishing core entry points from docs_src."""
    mock_arch = MagicMock()
    mock_summary = MagicMock()
    mock_summary.total_files = 120
    mock_summary.total_dependencies = 45
    mock_summary.entry_points = [
        "fastapi/__init__.py",
        "docs_src/tutorial001/main.py",
        "docs_src/tutorial002/main.py",
    ]
    mock_summary.core_modules = ["fastapi/applications.py", "fastapi/routing.py"]
    mock_summary.high_coupling_modules = ["fastapi/routing.py"]
    mock_summary.tech_stack = ["Python"]
    mock_arch.get_summary.return_value = mock_summary

    router = IntentRouter(architecture_service=mock_arch)
    intent_res = IntentResult(intent=Intent.ARCHITECTURE, confidence=0.95)

    intel = router.route(
        "fastapi/fastapi",
        "What does this codebase do, and what are its main entry points?",
        intent_res,
    )

    assert intel.has_data
    context = intel.structured_context

    # Must contain production entry points clearly labeled
    assert "Primary Production Entry Points" in context
    assert "fastapi/__init__.py" in context

    # Must explicitly label documentation / example applications as such
    assert "Example / Documentation Applications" in context
    assert "docs_src/tutorial001/main.py" in context
    assert (
        "(Note: these are sample/demo applications, not the core framework entry points)"
        in context
    )


# ---------------------------------------------------------------------------
# 5. Architecture Health & SCC Calculation Tests
# ---------------------------------------------------------------------------


def test_dag_with_zero_cycles_has_zero_scc_clusters_and_high_score():
    """Verify a healthy DAG with 0 cycles does not get penalised with SCC count = node count."""
    G = nx.DiGraph()
    # Create a linear DAG: a -> b -> c -> d -> e
    G.add_edge("a.py", "b.py")
    G.add_edge("b.py", "c.py")
    G.add_edge("c.py", "d.py")
    G.add_edge("d.py", "e.py")

    graph_service = GraphService()
    graph_service.load_graph = MagicMock(return_value=G)

    scc_count = graph_service.get_strongly_connected_components_count("test/repo")
    assert scc_count == 0, (
        f"Expected 0 non-trivial SCC clusters for a DAG, got {scc_count}"
    )

    # Verify report composer computes high architecture score
    mock_store = {
        "test/repo": {
            "analysis": MagicMock(metadata={"loc": 1000}, tech_stack=["Python"]),
            "architecture": MagicMock(
                reading_order=["a.py", "b.py", "c.py", "d.py", "e.py"],
                entry_points=["a.py"],
            ),
        }
    }
    composer = ReportComposer(
        store=mock_store,
        symbol_service=MagicMock(load=lambda _: MagicMock(symbol_count=10, symbols=[])),
        call_graph_service=MagicMock(),
        dead_code_service=MagicMock(analyze=lambda _: MagicMock(unused_files=[])),
        git_history_service=MagicMock(
            load=lambda _: MagicMock(hotspots=[], file_records=["a.py"])
        ),
        graph_service=graph_service,
    )

    report = composer.compose_report("test/repo")
    assert report.scores.architecture >= 90.0, (
        f"Expected architecture score >= 90, got {report.scores.architecture}"
    )
    assert report.scores.overall >= 80.0
    assert report.scores.grade in ("A", "B")
