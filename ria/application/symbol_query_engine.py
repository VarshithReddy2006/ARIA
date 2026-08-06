"""Symbol Query Engine application service.

Implements deterministic symbol lookups, definitions, references, scope, namespace, overrides,
and implementation queries on a RepositoryTwin.
Implements :class:`~ria.ports.query.SymbolQueryPort`.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ria.domain.enums import EdgeKind, NodeKind
from ria.domain.models.query_result import QueryMatch
from ria.domain.models.repository_twin import RepositoryTwin
from ria.ports.query import SymbolQueryPort

__all__ = ["SymbolQueryEngine"]


class SymbolQueryEngine(SymbolQueryPort):
    """Engine for deterministic symbol queries on a RepositoryTwin."""

    def find_symbol(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find symbols matching symbol_name."""
        matches: List[QueryMatch] = []
        for n in twin.graph_snapshot.graph.nodes:
            if (
                symbol_name.lower() in n.name.lower()
                or symbol_name.lower() in n.qualified_name.lower()
            ):
                matches.append(
                    QueryMatch(
                        id=n.node_id.value,
                        kind=n.kind.value,
                        name=n.name,
                        qualified_name=n.qualified_name,
                        location_path=n.location_path,
                    )
                )
        return tuple(matches)

    def find_definition(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]:
        """Find definition site of a symbol."""
        symbols = self.find_symbol(twin, symbol_name)
        return symbols[0] if symbols else None

    def find_declaration(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Optional[QueryMatch]:
        """Find declaration site of a symbol."""
        return self.find_definition(twin, symbol_name)

    def find_scope(self, twin: RepositoryTwin, scope_name: str) -> Optional[QueryMatch]:
        """Find scope matching scope_name."""
        for n in twin.graph_snapshot.graph.nodes:
            if n.kind is NodeKind.SCOPE and scope_name in n.name:
                return QueryMatch(
                    id=n.node_id.value,
                    kind=n.kind.value,
                    name=n.name,
                    qualified_name=n.qualified_name,
                    location_path=n.location_path,
                )
        return None

    def find_namespace(
        self, twin: RepositoryTwin, namespace_name: str
    ) -> Optional[QueryMatch]:
        """Find namespace matching namespace_name."""
        for n in twin.graph_snapshot.graph.nodes:
            if (
                n.kind in (NodeKind.NAMESPACE, NodeKind.PACKAGE, NodeKind.MODULE)
                and namespace_name in n.name
            ):
                return QueryMatch(
                    id=n.node_id.value,
                    kind=n.kind.value,
                    name=n.name,
                    qualified_name=n.qualified_name,
                    location_path=n.location_path,
                )
        return None

    def find_references(
        self, twin: RepositoryTwin, symbol_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find references targeting symbol_name."""
        matches: List[QueryMatch] = []
        target_nodes = {
            n.node_id: n
            for n in twin.graph_snapshot.graph.nodes
            if symbol_name.lower() in n.name.lower()
        }

        for e in twin.graph_snapshot.graph.edges:
            if (
                e.kind in (EdgeKind.REFERENCES, EdgeKind.CALLS)
                and e.target_id in target_nodes
            ):
                source_node = twin.graph_snapshot.graph.get_node(e.source_id)
                if source_node is not None:
                    matches.append(
                        QueryMatch(
                            id=source_node.node_id.value,
                            kind=source_node.kind.value,
                            name=source_node.name,
                            qualified_name=source_node.qualified_name,
                            location_path=source_node.location_path,
                        )
                    )
        return tuple(matches)

    def find_overrides(
        self, twin: RepositoryTwin, method_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find method overrides."""
        matches: List[QueryMatch] = []
        for e in twin.graph_snapshot.graph.edges:
            if e.kind is EdgeKind.OVERRIDES:
                source_node = twin.graph_snapshot.graph.get_node(e.source_id)
                if (
                    source_node is not None
                    and method_name.lower() in source_node.name.lower()
                ):
                    matches.append(
                        QueryMatch(
                            id=source_node.node_id.value,
                            kind=source_node.kind.value,
                            name=source_node.name,
                            qualified_name=source_node.qualified_name,
                            location_path=source_node.location_path,
                        )
                    )
        return tuple(matches)

    def find_implementations(
        self, twin: RepositoryTwin, interface_name: str
    ) -> Tuple[QueryMatch, ...]:
        """Find class implementations of an interface."""
        matches: List[QueryMatch] = []
        for e in twin.graph_snapshot.graph.edges:
            if e.kind in (EdgeKind.IMPLEMENTS, EdgeKind.EXTENDS):
                source_node = twin.graph_snapshot.graph.get_node(e.source_id)
                if source_node is not None:
                    matches.append(
                        QueryMatch(
                            id=source_node.node_id.value,
                            kind=source_node.kind.value,
                            name=source_node.name,
                            qualified_name=source_node.qualified_name,
                            location_path=source_node.location_path,
                        )
                    )
        return tuple(matches)
