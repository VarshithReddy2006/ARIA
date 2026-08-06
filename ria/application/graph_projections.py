"""Graph Projection application service.

Constructs specialized graph projections (Call, Dependency, Import, Inheritance, Module, Namespace, Package, Symbol, Repository)
over the underlying base Graph.
"""

from __future__ import annotations

from typing import FrozenSet, Tuple

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.graph import Graph
from ria.domain.models.graph_edge import GraphEdge
from ria.domain.models.graph_node import GraphNode

__all__ = ["GraphProjectionService"]


class GraphProjectionService:
    """Service for computing deterministic sub-graph projections over a master Graph."""

    def project_call_graph(self, graph: Graph) -> Graph:
        """Project the Call Graph (Function/Method nodes connected by CALLS edges)."""
        permitted_kinds: FrozenSet[NodeKind] = frozenset(
            {NodeKind.FUNCTION, NodeKind.METHOD}
        )
        return self._project_subgraph(
            graph, node_kinds=permitted_kinds, edge_kinds=frozenset({EdgeKind.CALLS})
        )

    def project_import_graph(self, graph: Graph) -> Graph:
        """Project the Import Graph (File/Module nodes connected by IMPORTS edges)."""
        permitted_kinds: FrozenSet[NodeKind] = frozenset(
            {NodeKind.FILE, NodeKind.MODULE, NodeKind.PACKAGE}
        )
        return self._project_subgraph(
            graph, node_kinds=permitted_kinds, edge_kinds=frozenset({EdgeKind.IMPORTS})
        )

    def project_inheritance_graph(self, graph: Graph) -> Graph:
        """Project the Inheritance Graph (Class/Interface nodes connected by EXTENDS/IMPLEMENTS/OVERRIDES edges)."""
        permitted_kinds: FrozenSet[NodeKind] = frozenset(
            {NodeKind.CLASS, NodeKind.INTERFACE, NodeKind.STRUCT, NodeKind.ENUM}
        )
        return self._project_subgraph(
            graph,
            node_kinds=permitted_kinds,
            edge_kinds=frozenset(
                {EdgeKind.EXTENDS, EdgeKind.IMPLEMENTS, EdgeKind.OVERRIDES}
            ),
        )

    def project_dependency_graph(self, graph: Graph) -> Graph:
        """Project the overall Dependency Graph."""
        return self._project_subgraph(
            graph,
            node_kinds=None,
            edge_kinds=frozenset(
                {
                    EdgeKind.IMPORTS,
                    EdgeKind.CALLS,
                    EdgeKind.USES,
                    EdgeKind.EXTENDS,
                    EdgeKind.IMPLEMENTS,
                }
            ),
        )

    def project_module_graph(self, graph: Graph) -> Graph:
        """Project the Module Graph."""
        return self._project_subgraph(
            graph,
            node_kinds=frozenset({NodeKind.MODULE, NodeKind.FILE}),
            edge_kinds=None,
        )

    def project_namespace_graph(self, graph: Graph) -> Graph:
        """Project the Namespace Graph."""
        return self._project_subgraph(
            graph, node_kinds=frozenset({NodeKind.NAMESPACE}), edge_kinds=None
        )

    def project_package_graph(self, graph: Graph) -> Graph:
        """Project the Package Graph."""
        return self._project_subgraph(
            graph, node_kinds=frozenset({NodeKind.PACKAGE}), edge_kinds=None
        )

    def project_symbol_graph(self, graph: Graph) -> Graph:
        """Project the Symbol Graph (all code symbols and structural/reference edges)."""
        symbol_kinds: FrozenSet[NodeKind] = frozenset(
            {
                NodeKind.CLASS,
                NodeKind.INTERFACE,
                NodeKind.STRUCT,
                NodeKind.ENUM,
                NodeKind.FUNCTION,
                NodeKind.METHOD,
                NodeKind.FIELD,
                NodeKind.VARIABLE,
                NodeKind.PARAMETER,
                NodeKind.SYMBOL,
            }
        )
        return self._project_subgraph(graph, node_kinds=symbol_kinds, edge_kinds=None)

    def project_repository_graph(self, graph: Graph) -> Graph:
        """Project the top-level Repository structural containment graph."""
        repo_kinds: FrozenSet[NodeKind] = frozenset(
            {
                NodeKind.REPOSITORY,
                NodeKind.COMMIT,
                NodeKind.BRANCH,
                NodeKind.FILE,
                NodeKind.MODULE,
                NodeKind.PACKAGE,
            }
        )
        return self._project_subgraph(graph, node_kinds=repo_kinds, edge_kinds=None)

    def _project_subgraph(
        self,
        graph: Graph,
        node_kinds: FrozenSet[NodeKind] | None,
        edge_kinds: FrozenSet[EdgeKind] | None,
    ) -> Graph:
        """Helper to construct a projected Graph instance based on node and edge kinds."""
        filtered_nodes: Tuple[GraphNode, ...]
        if node_kinds is not None:
            filtered_nodes = tuple(n for n in graph.nodes if n.kind in node_kinds)
        else:
            filtered_nodes = graph.nodes

        valid_node_ids = {n.node_id for n in filtered_nodes}

        filtered_edges: Tuple[GraphEdge, ...] = tuple(
            e
            for e in graph.edges
            if (edge_kinds is None or e.kind in edge_kinds)
            and e.source_id in valid_node_ids
            and e.target_id in valid_node_ids
        )

        return Graph(nodes=filtered_nodes, edges=filtered_edges)
