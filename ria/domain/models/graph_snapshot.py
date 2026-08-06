"""GraphSnapshot domain entity.

Represents a committed, versioned snapshot of a Repository Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass

from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.graph import Graph
from ria.domain.models.graph_identity import GraphFingerprint
from ria.domain.models.graph_result import GraphMetadata, GraphStatistics

__all__ = ["GraphSnapshot"]


@dataclass(frozen=True)
class GraphSnapshot:
    """Immutable, versioned snapshot of a Repository Knowledge Graph.

    Attributes:
        repository_id: Identity of the repository.
        commit_sha: Identity of the commit snapshot.
        graph: Immutable Graph instance.
        fingerprint: GraphFingerprint used to build the graph.
        metadata: Provenance GraphMetadata.
        statistics: Derived GraphStatistics.
    """

    repository_id: RepositoryId
    commit_sha: CommitSha
    graph: Graph
    fingerprint: GraphFingerprint
    metadata: GraphMetadata
    statistics: GraphStatistics
