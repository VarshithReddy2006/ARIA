"""Repository Retriever application service.

Retrieves repository evidence candidates (files, symbols, graph neighbours, dependencies,
inheritance, references, metrics) from a RepositoryTwin according to a ContextPlan.
Implements :class:`~ria.ports.context.RepositoryRetrieverPort`.
"""

from __future__ import annotations

import time
from typing import List

from ria.domain.models.context_evidence import ContextCandidate
from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_result import RetrievalResult
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.context import RepositoryRetrieverPort

__all__ = ["RepositoryRetrieverService"]


class RepositoryRetrieverService(RepositoryRetrieverPort):
    """Service for deterministic evidence retrieval from RepositoryTwin."""

    def retrieve(
        self,
        twin: RepositoryTwin,
        plan: ContextPlan,
    ) -> RetrievalResult:
        """Retrieve evidence candidates according to plan."""
        t0 = time.perf_counter()
        candidates: List[ContextCandidate] = []

        graph = twin.graph_snapshot.graph
        nodes = graph.nodes
        edges = graph.edges

        # 1. Target symbol matching
        for sym in plan.target_symbols:
            sym_lower = sym.lower()
            for n in nodes:
                if sym_lower in n.name.lower():
                    candidates.append(
                        ContextCandidate(
                            id=n.node_id.value,
                            kind=n.kind.value,
                            content=f"{n.kind.value} {n.qualified_name or n.name}",
                            location_path=n.location_path or "",
                            raw_score=1.0,
                        )
                    )

        # 2. Target file matching
        for target_f in plan.target_files:
            tf_lower = target_f.lower()
            for n in nodes:
                if n.location_path and tf_lower in n.location_path.lower():
                    candidates.append(
                        ContextCandidate(
                            id=n.node_id.value,
                            kind=n.kind.value,
                            content=f"file_node {n.name} in {n.location_path}",
                            location_path=n.location_path,
                            raw_score=0.9,
                        )
                    )

        # 3. Dependencies & References if requested
        if plan.include_dependencies or plan.include_references:
            for e in edges:
                src_node = graph.get_node(e.source_id)
                tgt_node = graph.get_node(e.target_id)
                if src_node is not None and tgt_node is not None:
                    candidates.append(
                        ContextCandidate(
                            id=e.edge_id.value,
                            kind=e.kind.value,
                            content=f"{e.kind.value}: {src_node.name} -> {tgt_node.name}",
                            location_path=src_node.location_path or "",
                            raw_score=0.7,
                        )
                    )

        # Deduplicate candidates by id
        seen_ids = set()
        dedup_candidates: List[ContextCandidate] = []
        for c in candidates:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                dedup_candidates.append(c)

        elapsed = time.perf_counter() - t0
        return RetrievalResult(
            candidates=tuple(dedup_candidates),
            retrieval_time_seconds=elapsed,
        )
