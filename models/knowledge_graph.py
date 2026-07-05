"""Repository Knowledge Graph data models.

Defines Pydantic structures for the Knowledge Graph nodes, edges, and summaries.
"""

from typing import Dict, List, Any
from pydantic import BaseModel, Field


class KnowledgeGraphNode(BaseModel):
    """A single semantic entity/node in the Repository Knowledge Graph."""

    id: str = Field(..., description="Unique stable node identifier.")
    type: str = Field(..., description="Entity type: repository | directory | file | symbol | component | health | compliance.")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Metadata properties of the entity.")


class KnowledgeGraphEdge(BaseModel):
    """A directed semantic relationship between two nodes in the graph."""

    source: str = Field(..., description="Source stable node ID.")
    target: str = Field(..., description="Target stable node ID.")
    type: str = Field(..., description="Relationship type: CONTAINS | DECLARES | IMPORTS | CALLS | HAS_HEALTH | HAS_COMPLIANCE.")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Metadata properties of the relationship.")


class KnowledgeGraph(BaseModel):
    """The fully composed read-only view of the Repository Knowledge Graph."""

    repository_name: str = Field(..., description="owner/repo identifier.")
    nodes: List[KnowledgeGraphNode] = Field(default_factory=list, description="All semantic nodes.")
    edges: List[KnowledgeGraphEdge] = Field(default_factory=list, description="All semantic edges.")


class KnowledgeGraphSummary(BaseModel):
    """Lightweight summary version of the Repository Knowledge Graph for stats and dashboards."""

    repository_name: str = Field(..., description="owner/repo identifier.")
    nodes_count: int = Field(..., description="Total count of nodes in the graph.")
    edges_count: int = Field(..., description="Total count of edges in the graph.")
    node_types_breakdown: Dict[str, int] = Field(..., description="Breakdown of nodes count by entity type.")
    edge_types_breakdown: Dict[str, int] = Field(..., description="Breakdown of edges count by relationship type.")
