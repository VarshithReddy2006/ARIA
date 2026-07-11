"""Graph-RAG data models.

Defines Pydantic structures for Chat requests, prompt rendering configurations,
and the final Graph-RAG completion result.
"""

from typing import Dict, List, Any
from pydantic import BaseModel, Field
from models.reasoning import ConfidenceBreakdown, Recommendation


class GraphRAGResult(BaseModel):
    """The fully composed, grounded Graph-RAG chat response."""

    answer: str = Field(
        ..., description="The grounded natural language answer from the LLM."
    )
    summary: str = Field(..., description="Short summary of the response.")
    reasoning_summary: str = Field(
        ..., description="Engineering reasoning summary from ERE."
    )
    citations: List[str] = Field(
        default_factory=list,
        description="Validated code references cited in the answer.",
    )
    confidence: ConfidenceBreakdown = Field(
        ..., description="Scores for evidence quality, reasoning, and recommendation."
    )
    graph_paths: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Semantic edge paths traversed in the subgraph.",
    )
    referenced_files: List[str] = Field(
        default_factory=list, description="Paths of referenced source code files."
    )
    referenced_symbols: List[str] = Field(
        default_factory=list, description="Names of referenced symbols."
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list, description="Actionable recommendations."
    )
    token_usage: Dict[str, int] = Field(
        default_factory=dict, description="Estimated prompt and response token usage."
    )
    processing_metrics: Dict[str, float] = Field(
        default_factory=dict, description="Execution traces and latencies (ms)."
    )
    model_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata about the model (e.g. model name, provider).",
    )
