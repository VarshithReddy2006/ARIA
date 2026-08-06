"""Unit tests for C7 Context Builder domain models, expanders, ranker, deduplicator, optimizer, serializer, and engine."""

from pathlib import Path

import pytest
from ria.context import (
    CallExpander,
    ContextBuilder,
    ContextEngine,
    ContextExpander,
    ContextSerializer,
    Deduplicator,
    DependencyExpander,
    RankingEngine,
    ReferenceExpander,
    TokenBudgetOptimizer,
)
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.context import (
    Citation,
    ContextOptions,
    ContextPackage,
    ContextRequest,
    ContextSnippet,
    ExpansionRule,
    InvalidContextRequestError,
    RankingScore,
    TokenBudget,
)
from ria.domain.index.value_objects import FilePath, Location
from ria.domain.resolution import QualifiedName, ResolvedFactSet, SemanticSymbol, SymbolKind, SymbolMoniker, Visibility
from ria.domain.search import SearchQueryType
from ria.domain.sync import CommitReference, RepositoryIdentity
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.query import QueryCache, QueryEngine, QueryExecutor, QueryOptimizer, QueryPlanner
from ria.search import AutocompleteEngine, HighlightEngine, RankingEngine as SearchRankingEngine, SearchCache, SearchEngine, SearchFilterEngine, SearchIndex, SearchPlanner


def test_context_domain_value_objects() -> None:
    tb = TokenBudget(max_tokens=2000)
    assert tb.max_tokens == 2000

    with pytest.raises(InvalidContextRequestError):
        TokenBudget(max_tokens=0)

    req = ContextRequest(question="How does auth work?")
    assert req.question == "How does auth work?"

    with pytest.raises(InvalidContextRequestError):
        ContextRequest(question="")


def test_deduplicator_and_budget_optimizer() -> None:
    fp = FilePath(relative_path="auth.py")
    moniker = SymbolMoniker(value="repo:auth.py:global:login")
    cit = Citation(repo_name="repo", commit_sha="a" * 40, file_path=fp, module_name="auth", symbol_moniker=moniker, start_line=1, end_line=5)
    score = RankingScore(priority=1, score_value=1.0, category="Definition")

    snip1 = ContextSnippet(snippet_id="s1", content="login function", citation=cit, score=score, estimated_tokens=100)
    snip2 = ContextSnippet(snippet_id="s2", content="login function", citation=cit, score=score, estimated_tokens=100)
    snip3 = ContextSnippet(snippet_id="s3", content="logout function", citation=cit, score=score, estimated_tokens=150)

    dedup = Deduplicator()
    deduped = dedup.deduplicate((snip1, snip2, snip3))
    assert len(deduped) == 2

    opt = TokenBudgetOptimizer()
    budget = TokenBudget(max_tokens=150)
    selected = opt.optimize_budget(deduped, budget)
    assert len(selected) == 1
    assert selected[0].snippet_id == "s1"


def test_context_serializer() -> None:
    serializer = ContextSerializer()
    fp = FilePath(relative_path="auth.py")
    moniker = SymbolMoniker(value="repo:auth.py:global:login")
    cit = Citation(repo_name="repo", commit_sha="a" * 40, file_path=fp, module_name="auth", symbol_moniker=moniker, start_line=1, end_line=5)
    score = RankingScore(priority=1, score_value=1.0, category="Definition")
    snip = ContextSnippet(snippet_id="s1", content="login function", citation=cit, score=score, estimated_tokens=10)

    pkg = ContextPackage(package_id="pkg1", question="auth?", sections=(), references=(), metadata=pytest.importorskip("ria.domain.context").ContextMetadata(1, 1, 10, 4000))

    json_out = serializer.serialize_json(pkg)
    assert "pkg1" in json_out

    md_out = serializer.serialize_markdown(pkg)
    assert "pkg1" in md_out

    txt_out = serializer.serialize_text(pkg)
    assert "pkg1" in txt_out


def test_context_builder_assembly() -> None:
    fact_store = SQLiteFactStoreAdapter(db_path=":memory:")
    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="b" * 40, committed_at=Timestamp.now())

    fp = FilePath(relative_path="services/auth.py")
    loc = Location(1, 0, 10, 0)
    moniker = SymbolMoniker(value="repo:services/auth.py:global:login")
    qname = QualifiedName(dotted_path="services.auth.login")
    sym = SemanticSymbol(moniker=moniker, name="login", qualified_name=qname, kind=SymbolKind.FUNCTION, visibility=Visibility.PUBLIC, path=fp, location=loc)

    fact_set = ResolvedFactSet(symbols=(sym,))
    fact_store.save_fact_set(repo_id, commit, fact_set)

    # Search Engine Setup
    search_planner = SearchPlanner()
    search_index = SearchIndex()
    search_ranking = SearchRankingEngine()
    search_filters = SearchFilterEngine()
    search_hl = HighlightEngine()
    search_auto = AutocompleteEngine()
    search_cache = SearchCache()
    search_engine = SearchEngine(search_planner, search_index, search_ranking, search_filters, search_hl, search_auto, search_cache)

    # Query Engine Setup
    q_planner = QueryPlanner()
    q_executor = QueryExecutor()
    q_optimizer = QueryOptimizer()
    q_cache = QueryCache()
    query_engine = QueryEngine(q_planner, q_executor, q_optimizer, q_cache)

    # Context Builder Setup
    ref_exp = ReferenceExpander()
    call_exp = CallExpander()
    dep_exp = DependencyExpander()
    expander = ContextExpander(ref_exp, call_exp, dep_exp)
    ranker = RankingEngine()
    deduplicator = Deduplicator()
    budget_optimizer = TokenBudgetOptimizer()

    builder = ContextBuilder(expander, ranker, deduplicator, budget_optimizer)
    serializer = ContextSerializer()
    engine = ContextEngine(builder, serializer)

    req = ContextRequest(question="login")
    pkg, formatted_json = engine.assemble_and_serialize(req, search_engine, query_engine, fact_store, repo_id, commit, fmt="json")

    assert pkg.package_id is not None
    assert pkg.metadata.total_snippets >= 1
    assert "login" in formatted_json
