"""Synthetic Micro-Fixtures & Trust Tests for Test Impact Intelligence v3.

Validates the 8-level test evidence hierarchy, alias resolution, method-level
disambiguation (e.g. Session.send vs sock.send), helper chains, API route invocations,
deduplication, and blast radius decoupling.
"""

import tempfile
import os
import shutil
import pytest
import networkx as nx

from models.symbol import Symbol, SymbolIndex
from models.phase2 import (
    EvidenceStrength,
    CallerInfo,
    ApiExposureInfo,
)
from services.impact_analysis_service import ImpactAnalysisService
from services.impact_debugger import ImpactDebugger


class FakeSymbolService:
    def __init__(self, symbols):
        self.symbols = symbols

    def load_index(self, repo_name):
        return SymbolIndex(
            repo=repo_name,
            symbols=self.symbols,
            generated_at="2026-01-01T00:00:00Z",
            symbol_count=len(self.symbols),
        )

    def find_matching_symbols(self, repo_name, identifier, file_context=None):
        clean = identifier.split(".")[-1]
        return [s for s in self.symbols if s.name == clean or s.name == identifier]

    def get_definition(self, repo_name, symbol_name):
        for s in self.symbols:
            if s.name == symbol_name:
                return s
        return None


class FakeGraphService:
    def __init__(self, graph):
        self.graph = graph

    def load_graph(self, repo_name):
        return self.graph


class FakeArchitectureService:
    def get_summary(self, repo_name):
        return None


@pytest.fixture
def temp_repo_workspace():
    """Create a temporary repository filesystem fixture."""
    tmp = tempfile.mkdtemp(prefix="aria_test_impact_")
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


def test_direct_call_test_impact(temp_repo_workspace, monkeypatch):
    """LEVEL 1: Test file directly calls target function in AST -> HIGH tier."""
    test_file_rel = "tests/test_direct.py"
    test_file_abs = os.path.join(temp_repo_workspace, test_file_rel)
    os.makedirs(os.path.dirname(test_file_abs), exist_ok=True)
    with open(test_file_abs, "w", encoding="utf-8") as f:
        f.write(
            "from services.payment import process_payment\n\ndef test_pay():\n    process_payment(100)\n"
        )

    graph = nx.DiGraph()
    graph.add_edge(test_file_rel, "services/payment.py")

    sym = Symbol(
        name="process_payment",
        type="function",
        file_path="services/payment.py",
        line_number=10,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_repo_file_path",
        lambda repo, fp: os.path.join(temp_repo_workspace, fp),
    )

    result = svc.analyze_change(
        "owner/repo", "Refactor process_payment in services/payment.py"
    )
    test_map = {t.test_file: t for t in result.affected_tests}

    assert test_file_rel in test_map
    item = test_map[test_file_rel]
    assert item.confidence_tier == "HIGH"
    assert item.impact_type == "DIRECT TEST IMPACT"
    assert item.evidence_strength == EvidenceStrength.LEVEL_1_EXACT_SYMBOL.value
    assert "process_payment" in item.reason


def test_alias_aware_test_resolution(temp_repo_workspace, monkeypatch):
    """LEVEL 2/1: Test imports symbol with alias (from X import Y as Z) -> HIGH tier."""
    test_file_rel = "tests/test_alias.py"
    test_file_abs = os.path.join(temp_repo_workspace, test_file_rel)
    os.makedirs(os.path.dirname(test_file_abs), exist_ok=True)
    with open(test_file_abs, "w", encoding="utf-8") as f:
        f.write(
            "from services.auth import verify_token as check_jwt\n\ndef test_auth():\n    check_jwt('token123')\n"
        )

    graph = nx.DiGraph()
    graph.add_edge(test_file_rel, "services/auth.py")

    sym = Symbol(
        name="verify_token",
        type="function",
        file_path="services/auth.py",
        line_number=25,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_repo_file_path",
        lambda repo, fp: os.path.join(temp_repo_workspace, fp),
    )

    result = svc.analyze_change("owner/repo", "Update verify_token in services/auth.py")
    test_map = {t.test_file: t for t in result.affected_tests}

    assert test_file_rel in test_map
    item = test_map[test_file_rel]
    assert item.confidence_tier == "HIGH"
    assert item.impact_type == "DIRECT TEST IMPACT"
    assert any("verify_token" in ep.get("reason", "") for ep in item.evidence_paths)


def test_method_qualification_disambiguation(temp_repo_workspace, monkeypatch):
    """Method qualification: Session.send vs sock.send."""
    # Test A: imports Session and calls session.send()
    test_a_rel = "tests/test_session_send.py"
    test_a_abs = os.path.join(temp_repo_workspace, test_a_rel)
    os.makedirs(os.path.dirname(test_a_abs), exist_ok=True)
    with open(test_a_abs, "w", encoding="utf-8") as f:
        f.write(
            "from requests.sessions import Session\n\ndef test_http():\n    s = Session()\n    s.send('req')\n"
        )

    # Test B: raw socket send without importing Session
    test_b_rel = "tests/test_socket.py"
    test_b_abs = os.path.join(temp_repo_workspace, test_b_rel)
    with open(test_b_abs, "w", encoding="utf-8") as f:
        f.write(
            "import socket\n\ndef test_raw():\n    sock = socket.socket()\n    sock.send(b'bytes')\n"
        )

    graph = nx.DiGraph()
    graph.add_edge(test_a_rel, "requests/sessions.py")
    graph.add_node(test_b_rel)

    sym = Symbol(
        name="send",
        parent_class="Session",
        type="method",
        file_path="requests/sessions.py",
        line_number=500,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_repo_file_path",
        lambda repo, fp: os.path.join(temp_repo_workspace, fp),
    )

    result = svc.analyze_change(
        "owner/repo", "Fix retry handling in Session.send in requests/sessions.py"
    )
    test_map = {t.test_file: t for t in result.affected_tests}

    assert test_a_rel in test_map
    assert test_map[test_a_rel].confidence_tier == "HIGH"

    # Raw socket test must NOT be matched
    assert test_b_rel not in test_map


def test_helper_chain_transitive_test_impact(temp_repo_workspace, monkeypatch):
    """LEVEL 3: Test calls a test helper fixture that calls the target symbol -> MEDIUM tier."""
    test_file_rel = "tests/test_orders.py"
    helper_file_rel = "tests/conftest.py"

    graph = nx.DiGraph()
    graph.add_edge(test_file_rel, helper_file_rel)
    graph.add_edge(helper_file_rel, "services/inventory.py")

    sym = Symbol(
        name="reserve_stock",
        type="function",
        file_path="services/inventory.py",
        line_number=40,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(svc, "_resolve_repo_file_path", lambda repo, fp: None)

    # Simulate transitive caller from helper
    def mock_resolve_callers(repo_name, seed_files, resolved_symbols, evidence_items):
        tc = CallerInfo(
            caller_id="tests/test_orders.py::test_create",
            caller_name="test_create",
            file_path="tests/test_orders.py",
            line_number=18,
            is_direct=False,
            depth=2,
            propagation_path=[
                "services/inventory.py::reserve_stock",
                "tests/conftest.py::seed_inventory",
                "tests/test_orders.py::test_create",
            ],
        )
        return [], [tc]

    monkeypatch.setattr(svc, "_resolve_callers", mock_resolve_callers)

    result = svc.analyze_change(
        "owner/repo", "Modify reserve_stock in services/inventory.py"
    )
    test_map = {t.test_file: t for t in result.affected_tests}

    assert test_file_rel in test_map
    item = test_map[test_file_rel]
    assert item.confidence_tier == "MEDIUM"
    assert item.impact_type == "LIKELY TEST IMPACT"
    assert item.evidence_strength == EvidenceStrength.LEVEL_3_SYMBOL_DEPENDENCY.value
    assert len(item.propagation_path) >= 2


def test_api_route_test_impact(temp_repo_workspace, monkeypatch):
    """LEVEL 4: Test file invokes public API route exposed by target symbol -> HIGH tier."""
    test_file_rel = "tests/test_api_endpoints.py"
    test_file_abs = os.path.join(temp_repo_workspace, test_file_rel)
    os.makedirs(os.path.dirname(test_file_abs), exist_ok=True)
    with open(test_file_abs, "w", encoding="utf-8") as f:
        f.write(
            "from fastapi.testclient import TestClient\n\ndef test_token_route(client):\n    res = client.post('/token', data={'u':'a'})\n    assert res.status_code == 200\n"
        )

    graph = nx.DiGraph()
    graph.add_edge(test_file_rel, "backend/routes.py")

    sym = Symbol(
        name="login_for_access_token",
        type="function",
        file_path="backend/routes.py",
        line_number=50,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_repo_file_path",
        lambda repo, fp: os.path.join(temp_repo_workspace, fp),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_api_exposure",
        lambda **kwargs: ApiExposureInfo(
            public_routes=["/token POST", "/users/me GET"],
            internal_routes=[],
            exported_symbols=[],
            deprecated_interfaces=[],
        ),
    )

    result = svc.analyze_change(
        "owner/repo", "Refactor login_for_access_token in backend/routes.py"
    )
    test_map = {t.test_file: t for t in result.affected_tests}

    assert test_file_rel in test_map
    item = test_map[test_file_rel]
    assert item.confidence_tier == "HIGH"
    assert item.impact_type == "DIRECT TEST IMPACT"
    assert item.evidence_strength == EvidenceStrength.LEVEL_4_API_CONTRACT.value
    assert "/token" in item.reason


def test_test_deduplication_and_aggregation(temp_repo_workspace, monkeypatch):
    """Deduplication: A test with multiple evidence links appears ONCE with highest tier."""
    test_file_rel = "tests/test_combo.py"
    test_file_abs = os.path.join(temp_repo_workspace, test_file_rel)
    os.makedirs(os.path.dirname(test_file_abs), exist_ok=True)
    with open(test_file_abs, "w", encoding="utf-8") as f:
        f.write(
            "from backend.auth import authenticate\n"
            "def test_both(client):\n"
            "    authenticate('u', 'p')\n"
            "    client.post('/login')\n"
        )

    graph = nx.DiGraph()
    graph.add_edge(test_file_rel, "backend/auth.py")

    sym = Symbol(
        name="authenticate",
        type="function",
        file_path="backend/auth.py",
        line_number=15,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_repo_file_path",
        lambda repo, fp: os.path.join(temp_repo_workspace, fp),
    )
    monkeypatch.setattr(
        svc,
        "_resolve_api_exposure",
        lambda **kwargs: ApiExposureInfo(
            public_routes=["/login POST"],
            internal_routes=[],
            exported_symbols=[],
            deprecated_interfaces=[],
        ),
    )

    result = svc.analyze_change("owner/repo", "Update authenticate in backend/auth.py")

    # Verify test_file_rel appears exactly ONCE
    matching = [t for t in result.affected_tests if t.test_file == test_file_rel]
    assert len(matching) == 1

    item = matching[0]
    assert item.confidence_tier == "HIGH"
    assert len(item.evidence_paths) >= 2

    # Debugger format check
    explanation = ImpactDebugger.format_test_explanation(item)
    assert "HIGH" in explanation
    assert "Evidence Paths" in explanation


def test_test_impact_risk_decoupling(temp_repo_workspace, monkeypatch):
    """Phase 14: Many affected tests do NOT artificially inflate production blast radius/risk."""
    graph = nx.DiGraph()
    seed = "services/calc.py"
    graph.add_node(seed)

    for i in range(100):
        t_name = f"tests/test_calc_{i}.py"
        graph.add_edge(t_name, seed)

    sym = Symbol(
        name="compute",
        type="function",
        file_path=seed,
        line_number=10,
        language="python",
    )

    svc = ImpactAnalysisService(
        symbol_service=FakeSymbolService([sym]),
        graph_service=FakeGraphService(graph),
        architecture_service=FakeArchitectureService(),
    )
    monkeypatch.setattr(svc, "_resolve_repo_file_path", lambda repo, fp: None)

    result = svc.analyze_change("owner/repo", "Tweak compute in services/calc.py")

    # Tests detected
    assert len(result.affected_tests) >= 50
    # Blast radius category must remain XS or S because only 1 production file is affected!
    assert result.blast_radius_category in ("XS", "S")
    assert result.risk_level in ("low", "medium")
