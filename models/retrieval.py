"""Repository Structural Retrieval Engine data models.

Defines Pydantic structures for retrieval references, steps, plans, explanations,
and the final retrieval context view.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class ContextReference(BaseModel):
    """A stable, typed reference to an entity inside the repository context."""

    id: str = Field(..., description="Unique stable entity identifier.")
    type: str = Field(..., description="Entity type: file | symbol | component | health | compliance | document.")
    source: str = Field(..., description="Executor source: subgraph | symbol_expansion | dependency_expansion | embedding.")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Metadata properties of the entity.")
    snippet: Optional[str] = Field(None, description="Optional raw text snippet (e.g. source snippet or documentation content).")


class RetrievalPlanStep(BaseModel):
    """A single step in a multi-stage retrieval plan."""

    executor: str = Field(..., description="Executor identifier: subgraph | symbol | dependency | embedding.")
    targets: List[str] = Field(default_factory=list, description="Target entity IDs for this step.")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Configuration parameters for the executor.")


class RetrievalPlan(BaseModel):
    """The generated plan specifying the execution sequence of retrieval steps."""

    policy: str = Field(..., description="Retrieval policy name.")
    steps: List[RetrievalPlanStep] = Field(default_factory=list, description="Ordered execution steps.")


class RetrievalExplanation(BaseModel):
    """Observability details explaining why and how context was gathered."""

    resolved_entities: List[str] = Field(..., description="Matched code entity names from user question.")
    policy: str = Field(..., description="Selected retrieval policy.")
    confidence: float = Field(..., description="Calculated retrieval confidence score (0.0-1.0).")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Summary counts of retrieved elements.")


class RepositoryRetrievalContext(BaseModel):
    """Composed structural context assembled for downstream LLM consumers."""

    repository_name: str = Field(..., description="owner/repo identifier.")
    question: str = Field(..., description="Original user question query.")
    references: List[ContextReference] = Field(default_factory=list, description="Ranked stable context references.")
    subgraph: Optional[Dict[str, Any]] = Field(None, description="Composed semantic subgraph slice.")
    explanation: RetrievalExplanation = Field(..., description="Explainability details.")
