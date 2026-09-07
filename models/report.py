"""Report schema models for ARIA.

Defines Pydantic structures for health score breakdowns, metadata, sections,
and the unified report data model.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ScoreBreakdown(BaseModel):
    """Detailed score breakdown and letter grade."""

    overall: float = Field(..., description="Overall health score (0-100).")
    architecture: float = Field(
        ..., description="Architecture stability score (0-100)."
    )
    api: float = Field(..., description="API quality and balance score (0-100).")
    hygiene: float = Field(
        ..., description="Maintainability & code hygiene score (0-100)."
    )
    churn: float = Field(..., description="Hotspot & churn risk score (0-100).")
    readability: float = Field(
        ..., description="Onboarding & readability score (0-100)."
    )
    grade: str = Field(..., description="Academic letter grade (A, B, C, D, F).")


class ReportMetadata(BaseModel):
    """Repository stats and report execution metadata."""

    repo_name: str = Field(..., description="Full repository name (owner/repo).")
    owner: str = Field(..., description="Repository owner.")
    name: str = Field(..., description="Repository name.")
    total_loc: int = Field(0, description="Total lines of code analyzed.")
    commits_count: int = Field(0, description="Total commit history count.")
    languages: Dict[str, float] = Field(
        default_factory=dict, description="Language percentage breakdown."
    )
    generated_at: str = Field(..., description="ISO 8601 generation timestamp.")
    execution_time_ms: float = Field(..., description="Time taken to compile report.")


class RuleViolationItem(BaseModel):
    """Structured architectural boundary rule violation."""

    rule_id: str = Field(..., description="Unique rule code (e.g. ARCH-001).")
    rule_name: str = Field(..., description="Human-readable rule name.")
    severity: str = Field(..., description="CRITICAL | MAJOR | MINOR.")
    source_node: str = Field(..., description="Origin module/file path.")
    target_node: str = Field(..., description="Target module/file path.")
    description: str = Field(
        ..., description="Explanation of why this violates layer boundaries."
    )


class WhyThisScoreItem(BaseModel):
    """Deterministic score driver with grounded evidence."""

    dimension: str = Field(..., description="Health dimension name.")
    score: float = Field(..., description="Dimension score out of 100.")
    status: str = Field(..., description="attention | review | healthy | unknown.")
    evidence: str = Field(..., description="Exact numerical or structural evidence.")
    impact: str = Field(
        ..., description="How this affects overall codebase maintainability."
    )
    recommendation: str = Field(
        ..., description="Action to remediate this score driver."
    )


class SignalAttentionItem(BaseModel):
    """High-priority signal requiring engineering attention."""

    id: str = Field(..., description="Signal identifier.")
    severity: str = Field(..., description="critical | high | medium | low.")
    title: str = Field(..., description="Concise issue title.")
    evidence: str = Field(..., description="Concrete numerical proof.")
    meaning: str = Field(..., description="Why this matters.")
    action_label: str = Field(..., description="Action button label.")
    action_target: str = Field(..., description="Target view or surface.")
    affected_file: Optional[str] = Field(
        None, description="Primary affected file path."
    )


class ArchReportSection(BaseModel):
    """Summary of structural stability and modular coupling."""

    cycles_count: int = Field(
        0, description="Number of circular dependencies detected."
    )
    cycles: List[List[str]] = Field(
        default_factory=list, description="circular paths details."
    )
    strongly_connected_components: int = Field(
        0, description="Count of strongly connected component clusters."
    )
    smells_count: int = Field(
        0, description="Number of dependency design smell violations."
    )
    smells: List[str] = Field(
        default_factory=list, description="Details of design smell violations."
    )
    rule_violations: List[RuleViolationItem] = Field(
        default_factory=list, description="Structured ArchUnit-style rule violations."
    )


class ApiReportSection(BaseModel):
    """Details on external interface exposure and package coupling stability."""

    total_exported_symbols: int = Field(
        0, description="Total count of public/exported symbols."
    )
    public_private_ratio: float = Field(
        0.0, description="Ratio of public to private symbols."
    )
    average_distance_main_sequence: float = Field(
        0.0, description="Average distance from main sequence."
    )
    unstable_modules_count: int = Field(
        0, description="Count of unstable/volatile modules."
    )


class HygieneReportSection(BaseModel):
    """Details on code cleanliness, dead code, and unreachable paths."""

    dead_functions_count: int = Field(
        0, description="Number of unused or unreachable functions."
    )
    dead_functions: List[str] = Field(
        default_factory=list, description="Names of dead/unused functions."
    )
    dead_code_ratio: float = Field(
        0.0, description="Percentage of codebase containing dead code."
    )


class OnboardingReportSection(BaseModel):
    """Onboarding guide, logical read paths, and core entry points."""

    reading_path_completeness: float = Field(
        0.0, description="Percentage of files included in reading path."
    )
    core_entry_points: List[str] = Field(
        default_factory=list, description="Detected main file entry points."
    )
    recommended_reading_path: List[str] = Field(
        default_factory=list, description="File names in recommended reading order."
    )


class ReportDataModel(BaseModel):
    """The unified report payload enclosing all sections and score metrics."""

    metadata: ReportMetadata = Field(
        ..., description="Repository and execution metadata."
    )
    scores: ScoreBreakdown = Field(..., description="Aggregated score details.")
    architecture: ArchReportSection = Field(
        ..., description="Structural and dependency coupling analysis."
    )
    api_surface: ApiReportSection = Field(
        ..., description="Public API and packaging stability analysis."
    )
    hygiene: HygieneReportSection = Field(
        ..., description="Code hygiene and dead code statistics."
    )
    onboarding: OnboardingReportSection = Field(
        ..., description="Code walkthrough and entry points."
    )
    refactoring_priorities: List[str] = Field(
        default_factory=list,
        description="Prioritized file refactoring recommendations.",
    )
    why_this_score: List[WhyThisScoreItem] = Field(
        default_factory=list,
        description="Grounding evidence for why this score was computed.",
    )
    signals_needing_attention: List[SignalAttentionItem] = Field(
        default_factory=list,
        description="Prioritized signals that require engineering attention.",
    )
    healthy_baseline: List[str] = Field(
        default_factory=list,
        description="Verified healthy signals supported by evidence.",
    )
    ai_summary: Optional[str] = Field(
        None, description="High-level LLM-generated code summary."
    )
