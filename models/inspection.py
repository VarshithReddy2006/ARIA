"""Autonomous Repository Inspector (ARI) Data Models.

Defines Pydantic models for Findings, Inspection Reports, and Inspection Contexts.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class Finding(BaseModel):
    """An individual structured finding compiled by an inspection pack."""

    id: str = Field(..., description="Unique finding identifier.")
    category: str = Field(
        ...,
        description="architecture | security | performance | dependency | complexity | dead_code | documentation | testing",
    )
    severity: str = Field(..., description="critical | high | medium | low | info")
    confidence: float = Field(
        ..., description="Deterministic confidence score between 0.0 and 1.0."
    )
    title: str = Field(..., description="Short summary of the finding.")
    description: str = Field(..., description="Detailed description of the finding.")
    affected_entities: List[str] = Field(
        default_factory=list,
        description="List of affected files, symbols, or components.",
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="Source context evidence justifying the finding.",
    )
    graph_paths: List[Dict[str, Any]] = Field(
        default_factory=list, description="Visual paths/edges in the Knowledge Graph."
    )
    recommendations: List[str] = Field(
        default_factory=list, description="Actionable recommendations."
    )
    estimated_effort: str = Field(
        ..., description="Estimated effort to resolve (e.g. '2 hours', '1 day')."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata."
    )


class InspectionReport(BaseModel):
    """A full, read-only inspection report summarizing repository health."""

    repository: str = Field(..., description="Repository owner/name.")
    timestamp: float = Field(..., description="Unix timestamp of the inspection run.")
    overall_score: float = Field(
        ..., description="Aggregated quality score from 0.0 to 100.0."
    )
    findings: List[Finding] = Field(
        default_factory=list, description="Deduplicated list of findings."
    )
    statistics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Numerical counters of finding counts, severity distribution, etc.",
    )
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="High-level text summarizing overall repository health.",
    )
    inspection_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata containing context settings or executor run parameters.",
    )


class InspectionContext(BaseModel):
    """Shared immutable context data passed down to every inspection pack."""

    repository: str = Field(..., description="Repository owner/name.")
    twin: Dict[str, Any] = Field(
        ..., description="Repository Digital Twin representation."
    )
    knowledge_graph: Dict[str, Any] = Field(
        ..., description="Repository Knowledge Graph representation."
    )
    memory_context: Optional[Dict[str, Any]] = Field(
        None, description="Optional historic memory/timeline context."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional context parameters."
    )
