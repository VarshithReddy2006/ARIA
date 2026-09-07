"""Phase 2 — Repository Intelligence Layer: Pydantic models.

Defines output schemas for:
  - ReadingOrder    : optimal file-reading sequence for a developer
  - ImpactAnalysis  : files and components affected by a proposed change
  - ArchContext     : architecture context payload injected into LLM prompts

These models are intentionally separate from models/schemas.py and
models/architecture.py to keep phase boundaries clean.
"""

from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Reading Order
# ---------------------------------------------------------------------------


class ReadingOrderEntry(BaseModel):
    """A single file in the recommended reading sequence.

    Attributes:
        rank:      1-based position in the reading order.
        file_path: Relative path to the file.
        reason:    Short human-readable justification for this rank.
        tier:      Broad category: 'entry_point', 'core', 'service', 'utility', 'other'.
        score:     Internal ranking score (higher = read sooner).
    """

    rank: int = Field(..., description="1-based position in the reading order.")
    file_path: str = Field(..., description="Relative file path.")
    reason: str = Field("", description="Why this file appears at this rank.")
    tier: str = Field(
        "other",
        description="Tier category: entry_point, core, service, utility, other.",
    )
    score: float = Field(0.0, description="Internal ranking score.")


class ReadingOrder(BaseModel):
    """Optimal code-reading sequence for a repository.

    Attributes:
        repo:                  Repository identifier (owner/repo).
        ordered_files:         Ranked list of ReadingOrderEntry items.
        reasoning:             Top-level explanation of the ranking strategy.
        estimated_reading_time: Approximate minutes to read all listed files.
        total_files_ranked:    Total number of files that were scored.
    """

    repo: str = Field(..., description="Repository identifier.")
    ordered_files: List[ReadingOrderEntry] = Field(
        default_factory=list,
        description="Files sorted from most-to-least important to read first.",
    )
    reasoning: List[str] = Field(
        default_factory=list,
        description="Bullet-point reasoning for the overall strategy.",
    )
    estimated_reading_time: int = Field(
        0,
        description="Estimated reading time in minutes.",
    )
    total_files_ranked: int = Field(
        0,
        description="Total number of source files considered.",
    )


# ---------------------------------------------------------------------------
# Evidence & Impact Models
# ---------------------------------------------------------------------------


class EvidenceKind(str, Enum):
    """Classification of evidence backing an intelligence conclusion."""

    FACT = "FACT"
    INFERENCE = "INFERENCE"
    PREDICTION = "PREDICTION"
    RECOMMENDATION = "RECOMMENDATION"


class EvidenceStrength(str, Enum):
    """Deterministic hierarchy expressing relative strength of structural evidence."""

    LEVEL_1_EXACT_SYMBOL = (
        "LEVEL_1_EXACT_SYMBOL"  # Exact symbol definition (Weight: 1.00)
    )
    LEVEL_2_EXACT_CALL = "LEVEL_2_EXACT_CALL"  # Exact call edge in AST (Weight: 0.95)
    LEVEL_3_SYMBOL_DEPENDENCY = (
        "LEVEL_3_SYMBOL_DEPENDENCY"  # Explicit symbol import in AST (Weight: 0.85)
    )
    LEVEL_4_API_CONTRACT = (
        "LEVEL_4_API_CONTRACT"  # Public API route handler wrapping call (Weight: 0.80)
    )
    LEVEL_5_TEST_RELATIONSHIP = (
        "LEVEL_5_TEST_RELATIONSHIP"  # Test exercising symbol or route (Weight: 0.75)
    )
    LEVEL_6_MODULE_DEPENDENCY = "LEVEL_6_MODULE_DEPENDENCY"  # Coarse module import without symbol usage (Weight: 0.50)
    LEVEL_7_HEURISTIC = "LEVEL_7_HEURISTIC"  # Path/name similarity (Weight: 0.25)

    @property
    def weight(self) -> float:
        weights = {
            "LEVEL_1_EXACT_SYMBOL": 1.00,
            "LEVEL_2_EXACT_CALL": 0.95,
            "LEVEL_3_SYMBOL_DEPENDENCY": 0.85,
            "LEVEL_4_API_CONTRACT": 0.80,
            "LEVEL_5_TEST_RELATIONSHIP": 0.75,
            "LEVEL_6_MODULE_DEPENDENCY": 0.50,
            "LEVEL_7_HEURISTIC": 0.25,
        }
        return weights.get(self.value, 0.25)


class ConfidenceTier(str, Enum):
    """Confidence tier for affected files."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ImpactedFileDetail(BaseModel):
    """Detailed explainable record of why a file was included in the impact set."""

    file_path: str = Field(..., description="Relative file path.")
    confidence_tier: str = Field(
        ConfidenceTier.LOW.value, description="Confidence tier: HIGH, MEDIUM, or LOW."
    )
    confidence_score: float = Field(
        0.0, ge=0.0, le=1.0, description="Deterministic confidence score (0.0 to 1.0)."
    )
    evidence_strength: str = Field(
        EvidenceStrength.LEVEL_7_HEURISTIC.value,
        description="Evidence strength category from LEVEL_1 down to LEVEL_7.",
    )
    reason: str = Field("", description="Human-readable justification for inclusion.")
    propagation_path: List[str] = Field(
        default_factory=list,
        description="Step-by-step path from root changed symbol to this file.",
    )
    target_symbols: List[str] = Field(
        default_factory=list,
        description="Specific symbols defined, imported, or called in this file.",
    )
    verifications: dict = Field(
        default_factory=dict,
        description="Diagnostic flags (e.g. has_symbol, has_call, has_import, has_route, has_test).",
    )


class EvidenceItem(BaseModel):
    """A single piece of evidence backing an impact conclusion."""

    kind: EvidenceKind = Field(
        ..., description="Classification: FACT, INFERENCE, PREDICTION, RECOMMENDATION."
    )
    statement: str = Field(
        ..., description="Human-readable statement explaining the fact or reasoning."
    )
    source_reference: Optional[str] = Field(
        None,
        description="Actual repository location e.g. path/to/file.py:42 or symbol ID.",
    )
    confidence: int = Field(100, ge=0, le=100, description="Confidence score 0–100.")


class CallerInfo(BaseModel):
    """A direct or transitive caller of an affected symbol."""

    caller_id: str = Field(
        ..., description="Qualified caller node ID ({file}::{name})."
    )
    caller_name: str = Field(..., description="Function or method name.")
    file_path: str = Field(..., description="Source file containing the caller.")
    line_number: Optional[int] = Field(None, description="Line number of the caller.")
    is_direct: bool = Field(
        True, description="True for direct caller, False for transitive."
    )
    depth: int = Field(1, description="Call distance in hops from changed symbol.")
    propagation_path: List[str] = Field(
        default_factory=list,
        description="Call chain leading from target function to this caller.",
    )
    relationship: str = Field(
        "DIRECT_CALL", description="CallRelationshipType classification."
    )
    receiver_expr: Optional[str] = Field(None, description="Receiver expression text.")
    receiver_type: Optional[str] = Field(
        None, description="Resolved class or module of receiver."
    )
    confidence_tier: str = Field(
        "HIGH", description="Confidence tier (HIGH, MEDIUM, LOW)."
    )


class ApiExposureInfo(BaseModel):
    """Exposed routes and interfaces impacted by the proposed change."""

    public_routes: List[str] = Field(
        default_factory=list,
        description="Public HTTP routes reachable from affected symbols.",
    )
    internal_routes: List[str] = Field(
        default_factory=list, description="Internal routes affected."
    )
    exported_symbols: List[str] = Field(
        default_factory=list, description="Exported symbols impacted."
    )
    deprecated_interfaces: List[str] = Field(
        default_factory=list, description="Deprecated interfaces impacted."
    )


class TestImpactItem(BaseModel):
    """A test file affected by the change, grounded in repository evidence."""

    test_file: str = Field(..., description="Path to the affected test file.")
    impact_type: Literal[
        "DIRECT TEST IMPACT", "LIKELY TEST IMPACT", "HEURISTIC TEST CANDIDATE"
    ] = Field(..., description="Direct caller/importer vs candidate.")
    reason: str = Field(..., description="Why this test is impacted.")
    confidence_tier: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        "HIGH", description="Confidence tier: HIGH, MEDIUM, LOW."
    )
    evidence_strength: str = Field(
        EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value,
        description="Specific evidence tier e.g. LEVEL_1_EXACT_SYMBOL, LEVEL_2_EXACT_CALL, LEVEL_5_TEST_RELATIONSHIP.",
    )
    propagation_path: List[str] = Field(
        default_factory=list,
        description="Call or dependency path from target to this test.",
    )
    source_reference: Optional[str] = Field(
        None,
        description="Exact file:line reference where test calls or imports target.",
    )
    evidence_paths: List[dict] = Field(
        default_factory=list,
        description="All detected evidence paths for this test file (deduplicated).",
    )


class DependencyPath(BaseModel):
    """A chain of files linking the changed file to an affected file.

    Attributes:
        path: List of file paths forming the dependency chain, from changed
              file to transitively affected file.
    """

    path: List[str] = Field(
        default_factory=list,
        description="Dependency chain: [changed_file, ..., affected_file].",
    )


class ImpactAnalysis(BaseModel):
    """Evidence-backed impact analysis of a proposed change on the repository.

    Attributes:
        repo:                     Repository identifier.
        issue_text:               The original change request / issue.
        directly_affected_files:  Files that directly implement or import the
                                  changed functionality.
        indirectly_affected_files: Files transitively affected through the
                                  dependency graph.
        affected_components:      High-level component labels impacted.
        risk_level:               'low', 'medium', 'high', or 'extreme'.
        estimated_file_count:     Total count of directly + indirectly affected.
        dependency_paths:         Key dependency chains showing how impact spreads.
        confidence:               0–100 confidence score for this analysis.
        blast_radius_category:    'XS' (1-2), 'S' (3-5), 'M' (6-12), 'L' (13-25), 'XL' (>25).
        affected_symbols:         Classified symbols directly touched or resolved.
        direct_callers:           Functions directly calling affected symbols.
        transitive_callers:       Indirect callers reached via call graph BFS.
        api_exposure:             Public routes, internal routes, and exported symbols.
        affected_tests:           Test files exercising affected symbols/modules.
        architecture_boundaries:  Architecture layers crossed by the change ripple.
        evidence_items:           Detailed FACT, INFERENCE, PREDICTION, RECOMMENDATION items.
        implementation_order:     Dependency-ordered sequence of changes.
    """

    repo: str = Field(..., description="Repository identifier.")
    issue_text: str = Field("", description="Original change request.")
    directly_affected_files: List[str] = Field(
        default_factory=list,
        description="Files directly touched by the change.",
    )
    indirectly_affected_files: List[str] = Field(
        default_factory=list,
        description="Files transitively affected through imports.",
    )
    affected_components: List[str] = Field(
        default_factory=list,
        description="High-level components impacted.",
    )
    risk_level: str = Field(
        "low",
        description="Risk level: low, medium, high, or extreme.",
    )
    estimated_file_count: int = Field(
        0,
        description="Total directly + indirectly affected files.",
    )
    dependency_paths: List[DependencyPath] = Field(
        default_factory=list,
        description="Key dependency chains illustrating how impact propagates.",
    )
    confidence: int = Field(
        0,
        ge=0,
        le=100,
        description="Confidence score 0–100.",
    )
    blast_radius_category: str = Field(
        "XS",
        description="Blast radius size category: XS (1-2), S (3-5), M (6-12), L (13-25), XL (>25).",
    )
    affected_symbols: List[str] = Field(
        default_factory=list,
        description="Symbols directly touched or resolved from the change request.",
    )
    direct_callers: List[CallerInfo] = Field(
        default_factory=list,
        description="Direct callers of affected symbols with exact file and line numbers.",
    )
    transitive_callers: List[CallerInfo] = Field(
        default_factory=list,
        description="Transitive callers reached through the call graph.",
    )
    api_exposure: Optional[ApiExposureInfo] = Field(
        None,
        description="API routes and exported interfaces affected.",
    )
    affected_tests: List[TestImpactItem] = Field(
        default_factory=list,
        description="Test files impacted based on callers and imports.",
    )
    architecture_boundaries: List[str] = Field(
        default_factory=list,
        description="Architecture layer transitions crossed by impact propagation.",
    )
    evidence_items: List[EvidenceItem] = Field(
        default_factory=list,
        description="Structured FACT, INFERENCE, PREDICTION, RECOMMENDATION evidence with line citations.",
    )
    implementation_order: List[str] = Field(
        default_factory=list,
        description="Recommended dependency-ordered change sequence.",
    )
    high_confidence_files: List[str] = Field(
        default_factory=list,
        description="Files with Level 1–5 verified relationships (symbols, calls, direct imports, routes, tests).",
    )
    medium_confidence_files: List[str] = Field(
        default_factory=list,
        description="Files with Level 4–6 relationships (transitive callers, confirmed module dependencies).",
    )
    low_confidence_files: List[str] = Field(
        default_factory=list,
        description="Files with Level 6–7 relationships (unverified module imports, heuristic matches).",
    )
    tiered_files: dict = Field(
        default_factory=dict,
        description="Files grouped by confidence tier: {'high': [...], 'medium': [...], 'low': [...]}.",
    )
    impacted_file_details: List[ImpactedFileDetail] = Field(
        default_factory=list,
        description="Per-file explainable provenance, evidence strength, confidence score, and propagation path.",
    )
    verified_impact_count: int = Field(
        0,
        description="Count of verified, high-confidence impacts (code files and tests).",
    )
    likely_impact_count: int = Field(
        0,
        description="Count of likely, medium-confidence impacts (transitive callers, helper chains).",
    )
    candidate_count: int = Field(
        0,
        description="Count of exploratory, low-confidence candidates (peripheral imports, heuristics).",
    )
    operating_mode: str = Field(
        "BALANCED",
        description="Operating mode: SAFE (HIGH only), BALANCED (HIGH+MED), or EXPLORATORY (ALL).",
    )


# ---------------------------------------------------------------------------
# Architecture Context (used for LLM prompt injection)
# ---------------------------------------------------------------------------


class ArchContext(BaseModel):
    """Architecture context payload injected into LLM prompts.

    Attributes:
        entry_points:          Primary repository entry points.
        core_modules:          Most-central files by degree centrality.
        high_coupling_modules: Files with most combined in+out degree.
        total_files:           Total repository file count.
        total_dependencies:    Total import edges in the dependency graph.
        available:             False when no architecture has been built yet —
                               callers should degrade gracefully.
    """

    entry_points: List[str] = Field(default_factory=list)
    core_modules: List[str] = Field(default_factory=list)
    high_coupling_modules: List[str] = Field(default_factory=list)
    total_files: int = Field(0)
    total_dependencies: int = Field(0)
    available: bool = Field(
        False,
        description="True only when architecture data was successfully loaded.",
    )

    def to_prompt_block(self) -> str:
        """Render a compact, human-readable context block for LLM injection."""
        if not self.available:
            return ""
        lines = [
            "=== Repository Architecture Context ===",
            f"Total files: {self.total_files}  |  Dependency edges: {self.total_dependencies}",
            f"Entry points: {', '.join(self.entry_points[:5]) or 'none detected'}",
            f"Core modules (most connected): {', '.join(self.core_modules[:5]) or 'none'}",
            f"High-coupling files: {', '.join(self.high_coupling_modules[:5]) or 'none'}",
            "Note: High-level architectural centrality. For specific technical features (e.g. failover, circuit breakers, retrieval, embeddings, tree-sitter), ground answers in retrieved code chunks below.",
            "======================================",
        ]
        return "\n".join(lines)
