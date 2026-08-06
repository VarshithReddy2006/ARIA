"""Unit tests for C6 Search Engine domain models, index, ranking, filters, highlight, cache, and engine."""

import pytest
from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import FilePath, Location
from ria.domain.resolution import (
    QualifiedName,
    ResolvedFactSet,
    SemanticSymbol,
    SymbolKind,
    SymbolMoniker,
    Visibility,
)
from ria.domain.search import (
    AutocompleteResult,
    FileResult,
    InvalidSearchQueryError,
    ModuleResult,
    SearchQuery,
    SearchQueryType,
    SymbolResult,
)
from ria.domain.sync import CommitReference, RepositoryIdentity
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.search import (
    AutocompleteEngine,
    HighlightEngine,
    RankingEngine,
    SearchCache,
    SearchEngine,
    SearchFilterEngine,
    SearchIndex,
    SearchPlanner,
)


def test_search_domain_value_objects() -> None:
    query = SearchQuery(query_text="Auth", query_type=SearchQueryType.PREFIX)
    assert query.query_text == "Auth"

    with pytest.raises(InvalidSearchQueryError):
        SearchQuery(query_text="", query_type=SearchQueryType.EXACT)


def test_highlight_engine() -> None:
    hl = HighlightEngine()
    result = hl.highlight("AuthService", "Auth")
    assert result == "[Auth]Service"


def test_search_engine_all_types() -> None:
    fact_store = SQLiteFactStoreAdapter(db_path=":memory:")
    repo_id = RepositoryIdentity(
        repo_id=UUIDv4.generate(),
        remote_url="https://github.com/org/repo.git",
        name="repo",
    )
    commit = CommitReference(sha="a" * 40, committed_at=Timestamp.now())

    fp = FilePath(relative_path="services/auth_service.py")
    loc = Location(1, 0, 10, 0)
    moniker = SymbolMoniker(value="repo:services/auth_service.py:global:AuthService")
    qname = QualifiedName(dotted_path="services.auth_service.AuthService")

    sym1 = SemanticSymbol(
        moniker=moniker,
        name="AuthService",
        qualified_name=qname,
        kind=SymbolKind.CLASS,
        visibility=Visibility.PUBLIC,
        path=fp,
        location=loc,
    )
    sym2 = SemanticSymbol(
        moniker=SymbolMoniker(value="repo:services/auth_service.py:global:login"),
        name="login",
        qualified_name=QualifiedName(dotted_path="services.auth_service.login"),
        kind=SymbolKind.FUNCTION,
        visibility=Visibility.PUBLIC,
        path=fp,
        location=loc,
    )
    sym_mod = SemanticSymbol(
        moniker=SymbolMoniker(
            value="repo:services/auth_service.py:global:auth_service"
        ),
        name="auth_service",
        qualified_name=QualifiedName(dotted_path="services.auth_service"),
        kind=SymbolKind.MODULE,
        visibility=Visibility.PUBLIC,
        path=fp,
        location=loc,
    )

    fact_set = ResolvedFactSet(symbols=(sym1, sym2, sym_mod))
    fact_store.save_fact_set(repo_id, commit, fact_set)

    planner = SearchPlanner()
    index = SearchIndex()
    ranking = RankingEngine()
    filters = SearchFilterEngine()
    highlight = HighlightEngine()
    autocomplete = AutocompleteEngine()
    cache = SearchCache()

    engine = SearchEngine(
        planner, index, ranking, filters, highlight, autocomplete, cache
    )

    # 1. Exact Symbol Search
    q1 = SearchQuery(query_text="AuthService", query_type=SearchQueryType.EXACT)
    r1 = engine.search(q1, fact_store, repo_id, commit)
    assert r1.is_success
    assert isinstance(r1.results.payload, tuple)
    assert isinstance(r1.results.payload[0], SymbolResult)
    assert r1.results.payload[0].symbol.name == "AuthService"

    # 2. Prefix Search
    q2 = SearchQuery(query_text="log", query_type=SearchQueryType.PREFIX)
    r2 = engine.search(q2, fact_store, repo_id, commit)
    assert r2.is_success

    # 3. File Search
    q3 = SearchQuery(query_text="auth_service", query_type=SearchQueryType.FILE)
    r3 = engine.search(q3, fact_store, repo_id, commit)
    assert r3.is_success
    assert isinstance(r3.results.payload[0], FileResult)

    # 4. Module Search
    q4 = SearchQuery(query_text="auth_service", query_type=SearchQueryType.MODULE)
    r4 = engine.search(q4, fact_store, repo_id, commit)
    assert r4.is_success
    assert isinstance(r4.results.payload[0], ModuleResult)

    # 5. Autocomplete
    q5 = SearchQuery(query_text="Aut", query_type=SearchQueryType.AUTOCOMPLETE)
    r5 = engine.search(q5, fact_store, repo_id, commit)
    assert r5.is_success
    assert isinstance(r5.results.payload, AutocompleteResult)
    assert len(r5.results.payload.suggestions) >= 1
