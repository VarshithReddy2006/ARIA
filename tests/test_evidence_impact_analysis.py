"""Trust-critical test suite for evidence-backed ImpactAnalysisService."""

import pytest
import networkx as nx
from models.phase2 import (
    EvidenceKind,
    TestImpactItem,
)
from models.symbol import Symbol, SymbolIndex
from models.api_surface import (
    APISurface,
    ClassifiedSymbol,
    ApiKind,
    ApiStatus,
    APISurfaceStats,
)
from models.architecture import ArchitectureSummary
from services.impact_analysis_service import ImpactAnalysisService


class MockSymbolService:
    def __init__(self, symbols=None):
        self.symbols = symbols or []

    def get_definition(self, repo_name: str, symbol_name: str):
        for s in self.symbols:
            if s.name.lower() == symbol_name.lower():
                return s
        return None

    def load(self, repo_name: str):
        return SymbolIndex(repo=repo_name, symbols=self.symbols)


class MockCallGraphService:
    def __init__(self, graph=None):
        self.graph = graph or nx.DiGraph()

    def load_graph(self, repo_name: str):
        return self.graph


class MockAPISurfaceService:
    def __init__(self, symbols=None):
        self.symbols = symbols or []

    def load(self, repo_name: str):
        return APISurface(
            repo=repo_name,
            generated_at="2026-09-02T00:00:00Z",
            symbols=self.symbols,
            stats=APISurfaceStats(
                total_symbols=len(self.symbols),
                public_count=sum(1 for s in self.symbols if s.visibility == "public"),
                internal_count=sum(
                    1 for s in self.symbols if s.visibility == "internal"
                ),
                private_count=0,
                deprecated_count=sum(
                    1 for s in self.symbols if s.status == ApiStatus.DEPRECATED
                ),
                experimental_count=0,
                route_count=sum(1 for s in self.symbols if s.api_kind == ApiKind.ROUTE),
                orphan_public_count=0,
                by_language={"python": len(self.symbols)},
            ),
        )


class MockArchitectureService:
    def __init__(self, entry_points=None, core_modules=None):
        self.entry_points = entry_points or ["backend/main.py"]
        self.core_modules = core_modules or ["services/auth.py"]

    def get_summary(self, repo_name: str):
        return ArchitectureSummary(
            entry_points=self.entry_points,
            core_modules=self.core_modules,
            components={},
            patterns=["Layered Architecture"],
        )


class MockGraphService:
    def __init__(self, graph=None, return_none=False):
        self.return_none = return_none
        if graph is not None:
            self.graph = graph
        else:
            self.graph = nx.DiGraph()
            for n in [
                "services/auth.py",
                "services/token.py",
                "services/order.py",
                "core/database.py",
                "api/v1/users.py",
                "utils/helper.py",
                "billing/tax.py",
            ]:
                self.graph.add_node(n)

    def load_graph(self, repo_name: str):
        if self.return_none or repo_name == "unindexed/repo":
            return None
        return self.graph


TestImpactItem.__test__ = False


def test_symbol_resolution_and_line_numbers():
    """Verify exact symbol extraction, line number, file path, and FACT evidence."""
    sym = Symbol(
        name="authenticate_user",
        type="function",
        file_path="services/auth.py",
        line_number=42,
        language="python",
    )
    symbol_svc = MockSymbolService([sym])
    impact_svc = ImpactAnalysisService(
        symbol_service=symbol_svc,
        graph_service=MockGraphService(),
    )

    result = impact_svc.analyze_change(
        "test/repo", "Refactor authenticate_user to support OAuth"
    )
    assert "authenticate_user" in result.affected_symbols
    assert "services/auth.py" in result.directly_affected_files

    # Verify FACT evidence with exact source reference
    fact_items = [e for e in result.evidence_items if e.kind == EvidenceKind.FACT]
    assert len(fact_items) > 0
    sym_fact = next((e for e in fact_items if "authenticate_user" in e.statement), None)
    assert sym_fact is not None
    assert sym_fact.source_reference == "services/auth.py:42"


def test_caller_hierarchy_direct_and_transitive():
    """Verify direct callers (depth 1) and transitive callers (depth > 1) with line numbers."""
    sym = Symbol(
        name="verify_token",
        type="function",
        file_path="services/token.py",
        line_number=10,
        language="python",
    )
    symbol_svc = MockSymbolService([sym])

    # Call graph: route_handler -> auth_middleware -> verify_token
    # Note: edges in call graph are caller -> callee
    cg = nx.DiGraph()
    cg.add_node("services/token.py::verify_token", line_number=10, name="verify_token")
    cg.add_node(
        "services/auth.py::auth_middleware", line_number=55, name="auth_middleware"
    )
    cg.add_node("routers/api.py::route_handler", line_number=100, name="route_handler")

    cg.add_edge("services/auth.py::auth_middleware", "services/token.py::verify_token")
    cg.add_edge("routers/api.py::route_handler", "services/auth.py::auth_middleware")

    call_graph_svc = MockCallGraphService(cg)
    impact_svc = ImpactAnalysisService(
        symbol_service=symbol_svc,
        call_graph_service=call_graph_svc,
        graph_service=MockGraphService(),
    )

    result = impact_svc.analyze_change("test/repo", "Change verify_token signature")
    assert len(result.direct_callers) == 1
    assert result.direct_callers[0].caller_name == "auth_middleware"
    assert result.direct_callers[0].line_number == 55
    assert result.direct_callers[0].file_path == "services/auth.py"
    assert result.direct_callers[0].is_direct is True

    assert len(result.transitive_callers) == 1
    assert result.transitive_callers[0].caller_name == "route_handler"
    assert result.transitive_callers[0].line_number == 100
    assert result.transitive_callers[0].depth == 2


def test_api_route_exposure_detection():
    """Verify public API routes calling the affected symbol are identified."""
    sym = Symbol(
        name="get_db_session",
        type="function",
        file_path="core/database.py",
        line_number=15,
        language="python",
    )
    symbol_svc = MockSymbolService([sym])

    cg = nx.DiGraph()
    cg.add_node(
        "core/database.py::get_db_session", line_number=15, name="get_db_session"
    )
    cg.add_node("api/v1/users.py::list_users", line_number=88, name="list_users")
    cg.add_edge("api/v1/users.py::list_users", "core/database.py::get_db_session")
    call_graph_svc = MockCallGraphService(cg)

    api_sym = ClassifiedSymbol(
        name="list_users",
        qualified="api.v1.users.list_users",
        symbol_type="function",
        file_path="api/v1/users.py",
        line_number=88,
        language="python",
        visibility="public",
        api_kind=ApiKind.ROUTE,
        status=ApiStatus.STABLE,
        decorators=["@router.get('/users')"],
    )
    api_svc = MockAPISurfaceService([api_sym])

    impact_svc = ImpactAnalysisService(
        symbol_service=symbol_svc,
        call_graph_service=call_graph_svc,
        api_surface_service=api_svc,
        graph_service=MockGraphService(),
    )

    result = impact_svc.analyze_change("test/repo", "Modify get_db_session")
    assert result.api_exposure is not None
    assert len(result.api_exposure.public_routes) == 1
    assert "@router.get('/users')" in result.api_exposure.public_routes[0]
    assert "api/v1/users.py:88" in result.api_exposure.public_routes[0]


def test_affected_tests_mapping():
    """Verify test files importing or calling target code are marked as affected tests."""
    sym = Symbol(
        name="calculate_tax",
        type="function",
        file_path="billing/tax.py",
        line_number=20,
        language="python",
    )
    symbol_svc = MockSymbolService([sym])

    dep_graph = nx.DiGraph()
    dep_graph.add_node("billing/tax.py")
    dep_graph.add_node("tests/test_tax.py")
    dep_graph.add_node("tests/test_checkout.py")
    # test_tax imports tax.py
    dep_graph.add_edge("tests/test_tax.py", "billing/tax.py")
    dep_graph.add_edge("tests/test_checkout.py", "billing/tax.py")

    graph_svc = MockGraphService(dep_graph)
    impact_svc = ImpactAnalysisService(
        symbol_service=symbol_svc,
        graph_service=graph_svc,
    )

    result = impact_svc.analyze_change("test/repo", "Change calculate_tax formula")
    test_files = [t.test_file for t in result.affected_tests]
    assert "tests/test_tax.py" in test_files
    assert "tests/test_checkout.py" in test_files
    assert all(
        t.impact_type in ("DIRECT TEST IMPACT", "LIKELY TEST IMPACT")
        for t in result.affected_tests
    )


def test_evidence_kind_segregation():
    """Verify evidence items are cleanly segregated into FACT, INFERENCE, PREDICTION, RECOMMENDATION."""
    sym = Symbol(
        name="process_order",
        type="function",
        file_path="services/order.py",
        line_number=30,
        language="python",
    )
    symbol_svc = MockSymbolService([sym])
    impact_svc = ImpactAnalysisService(
        symbol_service=symbol_svc,
        graph_service=MockGraphService(),
        architecture_service=MockArchitectureService(
            core_modules=["services/order.py"]
        ),
    )

    result = impact_svc.analyze_change("test/repo", "Refactor process_order")
    kinds = {e.kind for e in result.evidence_items}

    # Must have FACT, PREDICTION, and RECOMMENDATION
    assert EvidenceKind.FACT in kinds
    assert EvidenceKind.PREDICTION in kinds
    assert EvidenceKind.RECOMMENDATION in kinds

    # All FACT items must specify a source_reference
    for e in result.evidence_items:
        if e.kind == EvidenceKind.FACT:
            assert e.source_reference is not None and len(e.source_reference) > 0


def test_blast_radius_and_risk_buckets():
    """Verify deterministic blast radius category (XS, S, M, L, XL)."""
    # 1. Single isolated file with no callers -> XS or S
    sym1 = Symbol(
        name="helper",
        type="function",
        file_path="utils/helper.py",
        line_number=5,
        language="python",
    )
    svc1 = ImpactAnalysisService(
        symbol_service=MockSymbolService([sym1]), graph_service=MockGraphService()
    )
    res1 = svc1.analyze_change("test/repo", "Tweak helper function")
    assert res1.blast_radius_category in ("XS", "S")

    # 2. Many dependent files -> XL
    dep_graph = nx.DiGraph()
    target = "core/engine.py"
    dep_graph.add_node(target)
    for i in range(25):
        client_node = f"services/client_{i}.py"
        dep_graph.add_node(client_node)
        dep_graph.add_edge(client_node, target)

    sym2 = Symbol(
        name="run_engine",
        type="function",
        file_path=target,
        line_number=10,
        language="python",
    )
    svc2 = ImpactAnalysisService(
        symbol_service=MockSymbolService([sym2]),
        graph_service=MockGraphService(dep_graph),
        architecture_service=MockArchitectureService(core_modules=[target]),
    )
    res2 = svc2.analyze_change("test/repo", "Rewrite run_engine in core/engine.py")
    assert res2.blast_radius_category == "XL"
    assert res2.risk_level in ("high", "extreme")


def test_fallback_graceful_handling():
    """Verify unindexed repository raises informative ValueError rather than uncaught error."""
    impact_svc = ImpactAnalysisService(graph_service=MockGraphService(graph=None))
    with pytest.raises(ValueError) as exc_info:
        impact_svc.analyze_change("unindexed/repo", "Refactor non_existent_thing")
    assert "No dependency graph found" in str(exc_info.value)
    assert "unindexed/repo" in str(exc_info.value)
