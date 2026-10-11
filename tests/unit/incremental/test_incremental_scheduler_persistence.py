"""Persistence behavior for incremental scheduler and engine."""

from pathlib import Path
import time

import pytest

from ria.domain.common.value_objects import Timestamp, UUIDv4
from ria.domain.index.value_objects import FilePath, Location
from ria.domain.resolution import (
    QualifiedName,
    RelationKind,
    ResolvedFactSet,
    SemanticRelation,
    SemanticSymbol,
    SymbolKind,
    SymbolModifiers,
    SymbolMoniker,
    Visibility,
)
from ria.domain.snapshot.value_objects import IncrementalPlan
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.incremental.cache_invalidator import CacheInvalidator
from ria.incremental.engine import IncrementalEngine
from ria.incremental.scheduler import IncrementalScheduler, _merge_incremental_fact_set
from ria.incremental.snapshot_manager import SnapshotManager
from ria.infrastructure.storage.sqlite_fact_store import SQLiteFactStoreAdapter
from ria.infrastructure.system import SystemClockAdapter
from ria.query.cache import QueryCache


def _repo() -> RepositoryIdentity:
    return RepositoryIdentity(
        UUIDv4.generate(), "https://example.test/repo.git", "repo"
    )


def _commit(char: str) -> CommitReference:
    return CommitReference(char * 40, Timestamp.now())


def _symbol(path: str, name: str) -> SemanticSymbol:
    moniker = SymbolMoniker(f"python:.:{path}#{name}")
    return SemanticSymbol(
        moniker=moniker,
        name=name,
        qualified_name=QualifiedName(name),
        kind=SymbolKind.FUNCTION,
        visibility=Visibility.PUBLIC,
        path=FilePath(path),
        location=Location(1, 0, 1, 1),
        modifiers=SymbolModifiers(),
    )


def _edge(source: SemanticSymbol, target: SemanticSymbol) -> SemanticRelation:
    return SemanticRelation(
        source=source.moniker,
        target=target.moniker,
        kind=RelationKind.CALLS,
        location=Location(1, 0, 1, 1),
    )


class _Workspace:
    def get_workspace_path(self, _repo_id):
        return Path(".")


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass


class _Metrics:
    def increment_counter(self, *_args, **_kwargs):
        pass

    def record_duration(self, *_args, **_kwargs):
        pass


class _Clock:
    def monotonic_seconds(self):
        return time.monotonic()

    def now_utc(self):
        return Timestamp.now()


class _FailedScheduler:
    def execute_plan(self, _plan):
        return False


class _Diff:
    def compute_diff(self, *_args):
        return ()


class _Planner:
    def build_plan(self, snapshot, to_commit, _changed):
        return IncrementalPlan(snapshot.identity, snapshot.commit, to_commit)


def _make_scheduler(fact_store):
    return IncrementalScheduler(
        scanner=None,
        parser_registry=None,
        unit_builder=None,
        batch_assembler=None,
        resolution_engine=None,
        fact_store=fact_store,
        workspace_manager=_Workspace(),
        filesystem=None,
        cache_invalidator=CacheInvalidator(),
        query_cache=QueryCache(),
        clock=_Clock(),
        logger=_Logger(),
        metrics=_Metrics(),
    )


def test_incremental_plan_persists_complete_partition_and_applies_deletions():
    repo, from_commit, to_commit = _repo(), _commit("a"), _commit("b")
    keep = _symbol("keep.py", "keep")
    changed = _symbol("changed.py", "same")
    deleted = _symbol("deleted.py", "gone")
    fact_store = SQLiteFactStoreAdapter()
    fact_store.save_fact_set(
        repo,
        from_commit,
        ResolvedFactSet(
            symbols=(keep, changed, deleted),
            relations=(
                _edge(keep, changed),
                _edge(changed, keep),
                _edge(keep, deleted),
                _edge(deleted, keep),
            ),
        ),
    )

    plan = IncrementalPlan(
        repo_id=repo,
        from_commit=from_commit,
        to_commit=to_commit,
        files_to_delete=(FilePath("deleted.py"),),
    )
    assert _make_scheduler(fact_store).execute_plan(plan)

    target_symbols = fact_store.get_symbols(repo, to_commit)
    assert {symbol.name for symbol in target_symbols} == {"keep", "same"}
    target_edges = {
        (relation.source.value, relation.target.value)
        for relation in fact_store.get_relations(repo, to_commit)
    }
    assert target_edges == {
        (keep.moniker.value, changed.moniker.value),
        (changed.moniker.value, keep.moniker.value),
    }
    # The prior commit remains an immutable full snapshot.
    assert {symbol.name for symbol in fact_store.get_symbols(repo, from_commit)} == {
        "keep",
        "same",
        "gone",
    }


def test_empty_plan_copies_facts_to_new_commit_partition():
    repo, from_commit, to_commit = _repo(), _commit("e"), _commit("f")
    keep = _symbol("keep.py", "keep")
    fact_store = SQLiteFactStoreAdapter()
    fact_store.save_fact_set(repo, from_commit, ResolvedFactSet(symbols=(keep,)))

    plan = IncrementalPlan(repo_id=repo, from_commit=from_commit, to_commit=to_commit)
    assert _make_scheduler(fact_store).execute_plan(plan)
    assert fact_store.get_symbols(repo, to_commit) == (keep,)


def test_merge_replaces_outgoing_edges_and_keeps_incoming_to_reintroduced_symbol():
    keep = _symbol("keep.py", "keep")
    changed = _symbol("changed.py", "same")
    new_target = _symbol("changed.py", "new_target")
    old_relations = (_edge(keep, changed), _edge(changed, keep))
    updated = _merge_incremental_fact_set(
        (keep, changed),
        old_relations,
        ResolvedFactSet(
            symbols=(changed, new_target),
            relations=(_edge(changed, new_target),),
        ),
        (FilePath("changed.py"),),
    )
    assert {symbol.name for symbol in updated.symbols} == {
        "keep",
        "same",
        "new_target",
    }
    assert {
        (relation.source.value, relation.target.value) for relation in updated.relations
    } == {
        (keep.moniker.value, changed.moniker.value),
        (changed.moniker.value, new_target.moniker.value),
    }


def test_failed_scheduler_does_not_advance_snapshot():
    repo, old, new = _repo(), _commit("c"), _commit("d")
    snapshots = SnapshotManager(SystemClockAdapter())
    engine = IncrementalEngine(snapshots, _Diff(), _Planner(), _FailedScheduler())

    with pytest.raises(RuntimeError, match="snapshot was not advanced"):
        engine.process_incremental_update(repo, old, new)

    latest = snapshots.get_latest_snapshot(repo)
    assert latest is not None
    assert latest.commit == old
