"""Unit tests for SQLiteFactStoreAdapter."""

from pathlib import Path

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import FilePath, Location
from ria.domain.resolution import (
    CallRelation,
    QualifiedName,
    RelationKind,
    ResolvedFactSet,
    SemanticDefinition,
    SemanticRelation,
    SemanticSymbol,
    SymbolKind,
    SymbolMoniker,
    Visibility,
)
from ria.domain.sync import CommitReference, RepositoryIdentity
from ria.infrastructure.storage import SQLiteFactStoreAdapter


def test_sqlite_fact_store_crud() -> None:
    store = SQLiteFactStoreAdapter(db_path=":memory:")

    repo_id = RepositoryIdentity(repo_id=UUIDv4.generate(), remote_url="https://github.com/org/repo.git", name="repo")
    commit = CommitReference(sha="a" * 40, committed_at=Timestamp.now())

    fp = FilePath(relative_path="src/main.py")
    loc = Location(1, 0, 5, 20)
    moniker = SymbolMoniker(value="repo:src/main.py:global:main")
    qname = QualifiedName(dotted_path="src.main.main")

    sym = SemanticSymbol(
        moniker=moniker,
        name="main",
        qualified_name=qname,
        kind=SymbolKind.FUNCTION,
        visibility=Visibility.PUBLIC,
        path=fp,
        location=loc,
    )
    defn = SemanticDefinition(moniker=moniker, qualified_name=qname, path=fp, location=loc)

    callee_m = SymbolMoniker(value="repo:src/util.py:global:helper")
    call_rel = CallRelation(caller_moniker=moniker, callee_moniker=callee_m, location=loc)

    fact_set = ResolvedFactSet(
        symbols=(sym,),
        definitions=(defn,),
        calls=(call_rel,),
    )

    # 1. Save
    store.save_fact_set(repo_id, commit, fact_set)

    # 2. Get symbols
    symbols = store.get_symbols(repo_id, commit)
    assert len(symbols) == 1
    assert symbols[0].moniker == moniker
    assert symbols[0].name == "main"
    assert symbols[0].path == fp

    # Path filter
    symbols_filtered = store.get_symbols(repo_id, commit, path=fp)
    assert len(symbols_filtered) == 1

    symbols_empty = store.get_symbols(repo_id, commit, path=FilePath(relative_path="other.py"))
    assert len(symbols_empty) == 0

    # 3. Get relations
    relations = store.get_relations(repo_id, commit)
    assert len(relations) == 1
    assert relations[0].source == moniker
    assert relations[0].target == callee_m
    assert relations[0].kind == RelationKind.CALLS

    # 4. Delete facts
    deleted = store.delete_facts(repo_id, commit)
    assert deleted is True

    assert len(store.get_symbols(repo_id, commit)) == 0
    assert len(store.get_relations(repo_id, commit)) == 0
