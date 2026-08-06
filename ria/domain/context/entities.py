"""Entities and Result Containers for C7 Context Builder."""

from dataclasses import dataclass, field
from typing import Tuple

from ria.domain.common.base import ValueObject
from ria.domain.context.value_objects import Citation, ContextStatistics, RankingScore
from ria.domain.resolution.value_objects import SymbolMoniker


@dataclass(frozen=True, slots=True)
class ContextSnippet(ValueObject):
    """Immutable context snippet with full citation and score."""

    snippet_id: str
    content: str
    citation: Citation
    score: RankingScore
    estimated_tokens: int


@dataclass(frozen=True, slots=True)
class ContextReference(ValueObject):
    """Immutable context relationship reference."""

    source_moniker: SymbolMoniker
    target_moniker: SymbolMoniker
    relation_kind: str


@dataclass(frozen=True, slots=True)
class ContextSection(ValueObject):
    """Immutable section grouping related context snippets."""

    title: str
    snippets: Tuple[ContextSnippet, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ContextMetadata(ValueObject):
    """Immutable metadata describing assembled context package."""

    total_sections: int
    total_snippets: int
    total_tokens: int
    token_budget: int


@dataclass(frozen=True, slots=True)
class ContextPackage(ValueObject):
    """Immutable aggregate entity holding complete assembled context package."""

    package_id: str
    question: str
    sections: Tuple[ContextSection, ...] = field(default_factory=tuple)
    references: Tuple[ContextReference, ...] = field(default_factory=tuple)
    metadata: ContextMetadata = field(default_factory=lambda: ContextMetadata(0, 0, 0, 4000))
    statistics: ContextStatistics = field(default_factory=lambda: ContextStatistics(0.0, 0.0, 0.0, 0.0, 0, 0))
