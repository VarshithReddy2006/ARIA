"""Repository Digital Twin data models.

Defines Pydantic structures for the Repository Twin, including snapshot status,
summaries, and lightweight view representations.
"""

from typing import Dict, List, Any
from pydantic import BaseModel, Field


class RepositorySnapshot(BaseModel):
    """Pin metadata representing a specific repository commit and state."""

    commit_sha: str = Field(..., description="Git commit hash of the analyzed state.")
    branch: str = Field(..., description="Target branch (e.g. main/master).")
    indexed_timestamp: float = Field(
        ..., description="Epoch timestamp of analysis build."
    )
    analysis_version: str = Field(..., description="Schema or tool version identifier.")


class RepositoryTwin(BaseModel):
    """Unified composed view of the repository state (read-only architectural façade)."""

    repository_name: str = Field(..., description="owner/repo identifier.")
    snapshot: RepositorySnapshot = Field(
        ..., description="Specific repository state pinning."
    )
    metadata: Dict[str, Any] = Field(..., description="Tech stack, LOC, general info.")
    files: List[str] = Field(..., description="List of file paths.")
    symbols_summary: Dict[str, Any] = Field(
        ..., description="Total symbols count, public/private ratio."
    )
    dependencies_summary: Dict[str, Any] = Field(
        ..., description="External packages and import relationships count."
    )
    architecture_summary: Dict[str, Any] = Field(
        ..., description="Cycles, strongly connected components count, entry points."
    )
    health_summary: Dict[str, Any] = Field(
        ..., description="Overall health score and grade breakdown."
    )
    compliance_summary: Dict[str, Any] = Field(
        ..., description="Compliance status based on codebase rules."
    )


class RepositoryTwinSummary(BaseModel):
    """Lightweight summary version of the Repository Twin for dashboards and IDE integrations."""

    repository_name: str = Field(..., description="owner/repo identifier.")
    snapshot: RepositorySnapshot = Field(..., description="Repository state pin info.")
    tech_stack: List[str] = Field(
        ..., description="Primary languages/technologies detected."
    )
    overall_health_score: float = Field(..., description="Health score (0-100).")
    health_grade: str = Field(..., description="Academic health grade (A/B/C/D/F).")
    compliance_status: str = Field(
        ..., description="Compliance status (compliant/warning/non-compliant)."
    )
    total_files: int = Field(..., description="Total code files count.")
    total_symbols: int = Field(..., description="Total code symbols count.")
