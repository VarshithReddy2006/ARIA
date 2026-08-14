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
    ai_summary: Optional[str] = Field(
        None, description="High-level LLM-generated code summary."
    )
