"""Repository analysis domain models.

Defines DependencyAnalysis, ImpactAnalysis, ArchitectureAnalysis, PatternMatch, CrossReference, and AnalysisResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Optional, Tuple

from ria.domain.identity import CommitSha, RepositoryId

__all__ = [
    "DependencyAnalysis",
    "ImpactAnalysis",
    "ArchitectureAnalysis",
    "PatternMatch",
    "CrossReference",
    "AnalysisResult",
]


@dataclass(frozen=True)
class DependencyAnalysis:
    """Quantitative and structural dependency analysis output.

    Attributes:
        module_dependencies: Mapping of module path to dependent modules.
        package_dependencies: Mapping of package path to dependent packages.
        circular_dependencies: Tuple of detected dependency cycles.
        dependency_depth_max: Maximum depth of import chains.
        import_chains: Detailed import chain paths.
    """

    module_dependencies: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    package_dependencies: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    circular_dependencies: Tuple[Tuple[str, ...], ...] = ()
    dependency_depth_max: int = 0
    import_chains: Tuple[Tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class ImpactAnalysis:
    """Deterministic change impact analysis output.

    Attributes:
        target_files: Directly modified target files.
        affected_files: Files indirectly affected by changes.
        affected_symbols: Symbols affected across codebase.
        affected_classes: Classes affected across codebase.
        affected_functions: Callables affected across codebase.
        dependency_ripple_count: Import dependency ripple count.
        inheritance_ripple_count: Subtyping inheritance ripple count.
        reference_ripple_count: Symbol reference ripple count.
    """

    target_files: Tuple[str, ...] = ()
    affected_files: Tuple[str, ...] = ()
    affected_symbols: Tuple[str, ...] = ()
    affected_classes: Tuple[str, ...] = ()
    affected_functions: Tuple[str, ...] = ()
    dependency_ripple_count: int = 0
    inheritance_ripple_count: int = 0
    reference_ripple_count: int = 0


@dataclass(frozen=True)
class ArchitectureAnalysis:
    """Architectural health and rule violation analysis output.

    Attributes:
        layer_violations: Detected clean architecture layer boundary violations.
        dependency_violations: Illegal dependency directions or imports.
        cycles: Detected structural cycle clusters.
        orphan_components: Unreferenced/isolated components.
        unused_symbols: Declared symbols with zero references.
        dead_code_candidates: Dead code candidate paths or symbols.
        structural_hotspots: High-coupling or high-complexity hotspot locations.
    """

    layer_violations: Tuple[str, ...] = ()
    dependency_violations: Tuple[str, ...] = ()
    cycles: Tuple[Tuple[str, ...], ...] = ()
    orphan_components: Tuple[str, ...] = ()
    unused_symbols: Tuple[str, ...] = ()
    dead_code_candidates: Tuple[str, ...] = ()
    structural_hotspots: Tuple[str, ...] = ()


@dataclass(frozen=True)
class PatternMatch:
    """Structural pattern match entry.

    Attributes:
        pattern_type: Pattern category (e.g. 'class', 'interface', 'method', 'import', 'decorator').
        matched_element: Matched element name or moniker.
        location_path: File path location.
        span_details: Source position or span string description.
    """

    pattern_type: str
    matched_element: str
    location_path: str
    span_details: Optional[str] = None


@dataclass(frozen=True)
class CrossReference:
    """Cross-reference link entry.

    Attributes:
        source_symbol: Source symbol moniker or name.
        target_symbol: Target symbol moniker or name.
        relation_kind: Relation category (e.g. 'calls', 'references', 'extends', 'imports').
        source_file: Source file path location.
        target_file: Target file path location.
    """

    source_symbol: str
    target_symbol: str
    relation_kind: str
    source_file: str
    target_file: str


@dataclass(frozen=True)
class AnalysisResult:
    """Comprehensive analysis result container.

    Attributes:
        analysis_type: Kind of analysis performed.
        repository_id: Repository identity.
        commit_sha: Bound commit SHA.
        created_at_iso: UTC timestamp of analysis run.
        dependency_analysis: Optional DependencyAnalysis details.
        impact_analysis: Optional ImpactAnalysis details.
        architecture_analysis: Optional ArchitectureAnalysis details.
        pattern_matches: Tuple of PatternMatch entries.
        cross_references: Tuple of CrossReference entries.
    """

    analysis_type: str
    repository_id: RepositoryId
    commit_sha: CommitSha
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    dependency_analysis: Optional[DependencyAnalysis] = None
    impact_analysis: Optional[ImpactAnalysis] = None
    architecture_analysis: Optional[ArchitectureAnalysis] = None
    pattern_matches: Tuple[PatternMatch, ...] = ()
    cross_references: Tuple[CrossReference, ...] = ()
