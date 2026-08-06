"""Incremental Parser service.

Implements the incremental parsing requirement of Milestone 3:
- Consumes ``ChangeSet.paths_requiring_reparse()`` to reparse only changed files.
- Reuses cached parse results for unchanged or renamed files using
  ``FileUnit.reuse_key`` and component versions.
- Never parses the same content twice under the same component versions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, FrozenSet, Mapping, Optional, Sequence, Tuple

from ria.domain.models.change_set import ChangeSet
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parse_cache_entry import ParseCacheEntry
from ria.domain.models.parse_result import ParseResult
from ria.domain.models.parser_identity import ParseCacheKey
from ria.ports.blob_store import ContentAddressableStore
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.parser import ParseCacheStore, ParserRegistryPort

__all__ = ["IncrementalParseSummary", "IncrementalParser"]

#: Content loader callback type: takes a FileUnit's content_hash and returns its bytes
ContentLoader = Callable[[str], bytes]


@dataclass(frozen=True)
class IncrementalParseSummary:
    """Summary statistics for an incremental parse execution.

    Attributes:
        total_units: Total file units presented.
        reparsed_units: Number of units newly parsed.
        cached_units: Number of units served from cache.
        skipped_units: Number of non-candidate units skipped.
        cache_hit_ratio: Ratio of cached units to parse candidates.
    """

    total_units: int
    reparsed_units: int
    cached_units: int
    skipped_units: int

    @property
    def candidate_units(self) -> int:
        """Total parse candidates."""
        return self.reparsed_units + self.cached_units

    @property
    def cache_hit_ratio(self) -> float:
        """Fraction of candidates served from cache."""
        if self.candidate_units == 0:
            return 1.0
        return self.cached_units / self.candidate_units


class IncrementalParser:
    """Service that executes incremental repository parsing over a ChangeSet.

    Attributes:
        registry: Parser registry holding language plugins.
        cache_store: Storage adapter for cached parse results.
        blob_store: Content-addressable store for reading file bytes.
        metrics: Optional metrics sink.
    """

    def __init__(
        self,
        registry: ParserRegistryPort,
        cache_store: ParseCacheStore,
        blob_store: ContentAddressableStore,
        metrics: Optional[MetricsSink] = None,
    ) -> None:
        self._registry = registry
        self._cache_store = cache_store
        self._blob_store = blob_store
        self._metrics = metrics or NullMetricsSink()

    def parse_commit_units(
        self,
        units: Sequence[FileUnit],
        change_set: Optional[ChangeSet] = None,
    ) -> Tuple[Mapping[str, ParseResult], IncrementalParseSummary]:
        """Perform incremental parsing over a set of FileUnits.

        Args:
            units: All FileUnits belonging to the commit.
            change_set: Optional ChangeSet between base commit and head commit. When
                absent (full rebuild), every candidate unit is a reparse candidate.

        Returns:
            Tuple of (path -> ParseResult mapping, IncrementalParseSummary).
        """
        paths_requiring_reparse: FrozenSet[str] = (
            change_set.paths_requiring_reparse()
            if change_set is not None
            else frozenset(u.path for u in units)
        )

        results: Dict[str, ParseResult] = {}
        reparsed_count = 0
        cached_count = 0
        skipped_count = 0

        for unit in units:
            if not unit.is_parse_candidate:
                skipped_count += 1
                continue

            plugin = self._registry.get_plugin(unit.language)
            if plugin is None:
                skipped_count += 1
                continue

            fingerprint = plugin.fingerprint()
            cache_key = ParseCacheKey(reuse_key=unit.reuse_key, fingerprint=fingerprint)

            # Check cache if path does not explicitly require reparse
            if unit.path not in paths_requiring_reparse:
                cached_entry = self._cache_store.get(cache_key)
                if cached_entry is not None:
                    results[unit.path] = cached_entry.as_result()
                    cached_count += 1
                    continue

            # Check cache lookup even for required reparse paths (content-hash reuse across renames)
            cached_entry = self._cache_store.get(cache_key)
            if cached_entry is not None:
                results[unit.path] = cached_entry.as_result()
                cached_count += 1
                continue

            # Must parse from source bytes
            source_bytes = self._blob_store.get(unit.content_hash)
            parse_res = plugin.parse(unit, source_bytes)

            # Put freshly parsed result in cache
            cache_entry = ParseCacheEntry(
                key=cache_key,
                result=parse_res,
                cached_at=datetime.now(timezone.utc),
            )
            self._cache_store.put(cache_entry)

            results[unit.path] = parse_res
            reparsed_count += 1

        summary = IncrementalParseSummary(
            total_units=len(units),
            reparsed_units=reparsed_count,
            cached_units=cached_count,
            skipped_units=skipped_count,
        )

        return results, summary
