"""Dependency Analyzer computing symbol and file impact."""

from collections.abc import Sequence

from ria.domain.index.value_objects import FilePath
from ria.domain.resolution.value_objects import SymbolMoniker
from ria.domain.snapshot.value_objects import ChangedFile, DependencyImpact
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.storage.fact_store import FactStorePort


class DependencyAnalyzer:
    """Analyzer identifying symbols and files impacted by a sequence of file changes."""

    def __init__(self, fact_store: FactStorePort) -> None:
        self._fact_store = fact_store

    def analyze_impact(
        self,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        changed_files: Sequence[ChangedFile],
    ) -> DependencyImpact:
        affected_symbols: list[SymbolMoniker] = []
        affected_files: list[FilePath] = []

        for cf in changed_files:
            affected_files.append(cf.path)
            symbols = self._fact_store.get_symbols(repo_id, commit, path=cf.path)
            for sym in symbols:
                affected_symbols.append(sym.moniker)

        return DependencyImpact(
            affected_symbols=tuple(set(affected_symbols)),
            affected_files=tuple(set(affected_files)),
        )
