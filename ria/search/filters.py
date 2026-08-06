"""Search Filter Engine."""

from collections.abc import Sequence

from ria.domain.search.value_objects import SearchFilter, SearchIndexEntry


class SearchFilterEngine:
    """Filter engine matching SearchIndexEntry against SearchFilter criteria."""

    def filter_entries(
        self,
        entries: Sequence[SearchIndexEntry],
        sfilter: SearchFilter,
    ) -> Sequence[SearchIndexEntry]:
        results: list[SearchIndexEntry] = []
        for entry in entries:
            sym = entry.symbol
            if sfilter.symbol_kind and sym.kind != sfilter.symbol_kind:
                continue
            if sfilter.visibility and sym.visibility != sfilter.visibility:
                continue
            if sfilter.file_extension and not sym.path.relative_path.endswith(sfilter.file_extension):
                continue
            results.append(entry)
        return tuple(results)
