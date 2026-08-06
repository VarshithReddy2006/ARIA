"""High-level Parser Service orchestrator.

Coordinates parser registry, incremental parser, and parse result caching for repository ingestion.
"""

from __future__ import annotations

from typing import Mapping, Optional, Sequence, Tuple

from ria.application.capability_registry import CapabilityRegistry
from ria.application.incremental_parser import (
    IncrementalParseSummary,
    IncrementalParser,
)
from ria.application.parser_registry import ParserRegistry
from ria.domain.models.change_set import ChangeSet
from ria.domain.models.commit import CommitCoverage, LanguageCoverage
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.parse_result import ParseResult
from ria.ports.blob_store import ContentAddressableStore
from ria.observability.metrics import NullMetricsSink
from ria.ports.metrics import MetricsSink
from ria.ports.parser import ParseCacheStore, ParserRegistryPort

__all__ = ["ParserService"]


class ParserService:
    """High-level application service orchestrating Milestone 3 Parser Layer.

    Attributes:
        registry: Parser registry holding registered language plugins.
        capabilities: Capability registry for querying plugin capabilities.
        incremental_parser: Incremental parser engine.
    """

    def __init__(
        self,
        cache_store: ParseCacheStore,
        blob_store: ContentAddressableStore,
        registry: Optional[ParserRegistryPort] = None,
        metrics: Optional[MetricsSink] = None,
    ) -> None:
        self._metrics = metrics or NullMetricsSink()
        self._registry = registry or ParserRegistry()
        self._capabilities = CapabilityRegistry(self._registry)
        self._cache_store = cache_store
        self._blob_store = blob_store
        self._incremental_parser = IncrementalParser(
            registry=self._registry,
            cache_store=self._cache_store,
            blob_store=self._blob_store,
            metrics=self._metrics,
        )

    @property
    def registry(self) -> ParserRegistryPort:
        """Parser registry instance."""
        return self._registry

    @property
    def capabilities(self) -> CapabilityRegistry:
        """Capability registry instance."""
        return self._capabilities

    def parse_commit(
        self,
        units: Sequence[FileUnit],
        change_set: Optional[ChangeSet] = None,
    ) -> Tuple[
        Sequence[FileUnit],
        CommitCoverage,
        Mapping[str, ParseResult],
        IncrementalParseSummary,
    ]:
        """Parse all candidate file units for a commit, updating unit parse outcomes and coverage.

        Args:
            units: Sequence of FileUnits belonging to the commit.
            change_set: Optional ChangeSet between base commit and head commit.

        Returns:
            Tuple of:
            - Updated sequence of FileUnits with parse outcomes recorded
            - Calculated CommitCoverage for the commit
            - Path -> ParseResult mapping
            - IncrementalParseSummary
        """
        results, summary = self._incremental_parser.parse_commit_units(
            units, change_set
        )

        updated_units = []
        files_parsed = 0
        symbols_total = 0
        lang_coverage_map = {}

        for unit in units:
            if unit.path in results:
                res = results[unit.path]
                updated_unit = unit.with_parse_outcome(
                    status=res.status,
                    reason=res.status_reason,
                )
                updated_units.append(updated_unit)

                if res.status.contributes_to_coverage:
                    files_parsed += 1
                    symbols_in_file = len(res.extracted.declarations)
                    symbols_total += symbols_in_file

                    # Aggregate per-language coverage
                    curr_lang_cov = lang_coverage_map.get(
                        unit.language,
                        LanguageCoverage(
                            language=unit.language,
                            files_total=0,
                            files_parsed=0,
                            symbols_total=0,
                        ),
                    )
                    lang_coverage_map[unit.language] = LanguageCoverage(
                        language=unit.language,
                        files_total=curr_lang_cov.files_total + 1,
                        files_parsed=curr_lang_cov.files_parsed + 1,
                        symbols_total=curr_lang_cov.symbols_total + symbols_in_file,
                    )
            else:
                updated_units.append(unit)
                if unit.is_parse_candidate:
                    curr_lang_cov = lang_coverage_map.get(
                        unit.language,
                        LanguageCoverage(
                            language=unit.language,
                            files_total=0,
                            files_parsed=0,
                            symbols_total=0,
                        ),
                    )
                    lang_coverage_map[unit.language] = LanguageCoverage(
                        language=unit.language,
                        files_total=curr_lang_cov.files_total + 1,
                        files_parsed=curr_lang_cov.files_parsed,
                        symbols_total=curr_lang_cov.symbols_total,
                    )

        files_eligible = sum(1 for u in units if u.is_parse_candidate)

        coverage = CommitCoverage(
            files_total=len(units),
            files_eligible=files_eligible,
            files_parsed=files_parsed,
            symbols_total=symbols_total,
            by_language=tuple(
                sorted(
                    lang_coverage_map.values(), key=lambda lang_cov: lang_cov.language
                )
            ),
        )

        return tuple(updated_units), coverage, results, summary
