"""Search Index implementing SearchIndexPort."""

from collections.abc import Sequence

from ria.domain.search.value_objects import SearchIndexEntry, SearchQuery
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.search.index import SearchIndexPort
from ria.ports.storage.fact_store import FactStorePort


class SearchIndex(SearchIndexPort):
    """In-memory SearchIndex built from persisted FactStore symbols."""

    def __init__(self) -> None:
        self._entries: list[SearchIndexEntry] = []

    def build_index(
        self,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
    ) -> int:
        self._entries.clear()
        symbols = fact_store.get_symbols(repo_id, commit)
        for sym in symbols:
            tokens = (
                sym.name,
                sym.qualified_name.dotted_path,
                sym.path.relative_path,
            )
            self._entries.append(SearchIndexEntry(symbol=sym, tokens=tokens))
        return len(self._entries)

    def search_candidates(
        self,
        query: SearchQuery,
    ) -> Sequence[SearchIndexEntry]:
        return tuple(self._entries)
