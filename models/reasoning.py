"""Engineering Reasoning Engine data models.

Defines Pydantic structures for typed Evidence, Hypotheses, Contradictions,
Decision Options, Recommendations, Confidence Breakdowns, and the final Reasoning Result.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class Evidence(BaseModel):
    """A strongly-typed finding extracted and scored from repository context references."""

    id: str = Field(..., description="Unique evidence ID.")
    type: str = Field(
        ..., description="symbol | dependency | file | metric | health | compliance"
    )
    source: str = Field(
        "unknown",
        description="Retrieval source: subgraph | symbol_expansion | dependency_expansion | embedding",
    )
    reference_id: str = Field(
        ..., description="Stable ID of the underlying ContextReference."
    )
    description: str = Field(..., description="Description of the evidence findings.")
    quality_score: float = Field(
        1.0, description="Quality score of the evidence (0.0-1.0)."
    )


class Hypothesis(BaseModel):
    """An engineering assertion evaluated by ERE's rule packs."""

    id: str = Field(..., description="Unique hypothesis identifier.")
    description: str = Field(..., description="The formulated engineering hypothesis.")
    status: str = Field(..., description="validated | rejected | unverified")
    supporting_evidence: List[str] = Field(
        default_factory=list,
        description="IDs of typed Evidence objects supporting this.",
    )


class Contradiction(BaseModel):
    """A conflict between different evidence signals detected in repository context."""

    id: str = Field(..., description="Unique contradiction identifier.")
    description: str = Field(..., description="Explanation of the contradiction.")
    conflicting_evidence: List[str] = Field(
        ..., description="IDs of typed Evidence objects causing the conflict."
    )
    severity: str = Field(..., description="low | medium | high")


class DecisionOption(BaseModel):
    """An alternative solution path considered by ERE for a given problem."""

    name: str = Field(..., description="Name of the solution option.")
    description: str = Field(..., description="Description of the approach.")
    pros: List[str] = Field(
        default_factory=list, description="Advantages of this option."
    )
    cons: List[str] = Field(
        default_factory=list, description="Disadvantages or risks of this option."
    )
    recommendation_confidence: float = Field(
        ..., description="Confidence score for this specific option (0.0-100.0)."
    )


class DecisionAnalysis(BaseModel):
    """Trade-off analysis of alternative options before producing recommendations."""

    problem_statement: str = Field(
        ..., description="The identified code or architecture problem statement."
    )
    options: List[DecisionOption] = Field(
        default_factory=list, description="Alternative solution options."
    )


class Recommendation(BaseModel):
    """An actionable, structured recommendation to solve the resolved problem."""

    id: str = Field(..., description="Unique recommendation ID.")
    type: str = Field(
        ..., description="refactor | compliance_fix | testing | documentation"
    )
    target: str = Field(..., description="Target file or symbol ID.")
    priority: str = Field(..., description="low | medium | high")
    estimated_effort: str = Field(
        ..., description="Estimated timeline to implement, e.g. '2h', '1d'."
    )
    reasoning_chain: List[str] = Field(
        default_factory=list,
        description="Sequence of step or hypothesis IDs leading to this.",
    )


class ConfidenceBreakdown(BaseModel):
    """Granular confidence details separating evidence, reasoning, and recommendation trust."""

    evidence_quality: float = Field(
        ..., description="Overall quality score of retrieved evidence (0.0-100.0)."
    )
    reasoning_confidence: float = Field(
        ..., description="Consistency score of the reasoning chain (0.0-100.0)."
    )
    recommendation_confidence: float = Field(
        ...,
        description="Actionability confidence of proposed recommendations (0.0-100.0).",
    )


class ReasoningChainNode(BaseModel):
    """An internal node representing a step in the reasoning chain graph."""

    id: str = Field(..., description="Evidence, Hypothesis, or Recommendation ID.")
    type: str = Field(..., description="evidence | hypothesis | recommendation")
    label: str = Field(..., description="Human-readable node description.")
    relationships: List[Dict[str, str]] = Field(
        default_factory=list, description="Directed relations mapping reasoning flow."
    )


class ReasoningResult(BaseModel):
    """The fully composed read-only reasoning output from the ERE Orchestrator."""

    repository_name: str = Field(..., description="owner/repo identifier.")
    question: str = Field(..., description="Original user question query.")
    policy: str = Field(..., description="Selected reasoning policy.")
    evidence: List[Evidence] = Field(
        default_factory=list, description="Analyzed evidence nodes."
    )
    hypotheses: List[Hypothesis] = Field(
        default_factory=list, description="Evaluated engineering hypotheses."
    )
    contradictions: List[Contradiction] = Field(
        default_factory=list, description="Detected conflicts."
    )
    decision_analysis: Optional[DecisionAnalysis] = Field(
        None, description="Trade-off options evaluations."
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list, description="Actionable recommendations."
    )
    confidence: ConfidenceBreakdown = Field(
        ..., description="Confidence scores breakdown."
    )
    confidence_explanation: str = Field(
        ..., description="Text breakdown explanation of the scores."
    )
    reasoning_graph_nodes: List[ReasoningChainNode] = Field(
        default_factory=list, description="Findings nodes mapped internally for graphs."
    )
