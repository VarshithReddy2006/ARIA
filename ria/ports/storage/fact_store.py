"""Fact Store Port Protocol."""

from collections.abc import Sequence
from typing import Optional, Protocol, runtime_checkable

from ria.domain.index.value_objects import FilePath
from ria.domain.resolution.entities import ResolvedFactSet, SemanticSymbol
from ria.domain.resolution.value_objects import SemanticRelation, SymbolMoniker
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity


@runtime_checkable
class FactStorePort(Protocol):
    """Protocol for relational Fact Store persisting and querying ResolvedFactSet data.

    Preconditions: repo_id and commit must be valid domain objects.
    Postconditions: Persists facts atomically partitioned by (repo_id, commit_sha).
    """

    def save_fact_set(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        fact_set: ResolvedFactSet,
    ) -> None:
        """Atomically persist ResolvedFactSet into storage partitioned by (repo_id, commit_sha)."""
        ...

    def get_symbols(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        path: Optional[FilePath] = None,
    ) -> Sequence[SemanticSymbol]:
        """Retrieve stored SemanticSymbols for a repository commit, optionally filtered by file path."""
        ...

    def get_relations(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        source_moniker: Optional[SymbolMoniker] = None,
    ) -> Sequence[SemanticRelation]:
        """Retrieve stored SemanticRelations for a repository commit, optionally filtered by source moniker."""
        ...

    def delete_facts(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> bool:
        """Delete all persisted facts and relations for a specific repository commit."""
        ...
