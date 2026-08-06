"""Node Builder application service.

Maps repository units and semantic resolution entities into GraphNode entities.
Implements :class:`~ria.ports.graph.NodeBuilderPort`.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from ria.domain.enums import DeclarationKind, NodeKind
from ria.domain.identity import CommitSha, RepositoryId
from ria.domain.models.file_unit import FileUnit
from ria.domain.models.graph_node import GraphNode
from ria.domain.models.graph_node_id import GraphNodeId
from ria.domain.models.scope import Scope
from ria.domain.models.symbol import Symbol
from ria.ports.graph import NodeBuilderPort

__all__ = ["NodeBuilderService"]


class NodeBuilderService(NodeBuilderPort):
    """Service for mapping repository entities and semantic resolution entities to GraphNode objects."""

    def build_repository_node(self, repository_id: RepositoryId) -> GraphNode:
        """Build GraphNode for a Repository."""
        repo_str = (
            str(repository_id.value)
            if hasattr(repository_id, "value")
            else str(repository_id)
        )
        nid = GraphNodeId.for_node(NodeKind.REPOSITORY, repo_str, repo_str)
        return GraphNode(
            node_id=nid,
            kind=NodeKind.REPOSITORY,
            name=repo_str,
            qualified_name=repo_str,
        )

    def build_commit_node(
        self, repository_id: RepositoryId, commit_sha: CommitSha
    ) -> GraphNode:
        """Build GraphNode for a Commit."""
        repo_str = (
            str(repository_id.value)
            if hasattr(repository_id, "value")
            else str(repository_id)
        )
        sha_str = (
            str(commit_sha.value) if hasattr(commit_sha, "value") else str(commit_sha)
        )
        nid = GraphNodeId.for_node(NodeKind.COMMIT, repo_str, sha_str)
        return GraphNode(
            node_id=nid,
            kind=NodeKind.COMMIT,
            name=sha_str[:7],
            qualified_name=f"{repo_str}@{sha_str}",
        )

    def build_file_node(self, repository_id: RepositoryId, unit: FileUnit) -> GraphNode:
        """Build GraphNode for a File / Module / Package."""
        kind = NodeKind.FILE
        if (
            unit.path.endswith("__init__.py")
            or unit.path.endswith("index.js")
            or unit.path.endswith("index.ts")
        ):
            kind = NodeKind.PACKAGE
        elif unit.language != "unknown":
            kind = NodeKind.MODULE

        nid = GraphNodeId.for_node(kind, repository_id.value, unit.path)
        return GraphNode(
            node_id=nid,
            kind=kind,
            name=unit.path.rsplit("/", 1)[-1],
            qualified_name=unit.path,
            location_path=unit.path,
            properties={"language": unit.language, "blob_sha": unit.blob_sha},
        )

    def build_scope_node(self, repository_id: RepositoryId, scope: Scope) -> GraphNode:
        """Build GraphNode for a Scope."""
        kind = NodeKind.SCOPE
        nid = GraphNodeId.for_node(kind, repository_id.value, scope.scope_id.value)
        return GraphNode(
            node_id=nid,
            kind=kind,
            name=scope.name or scope.scope_id.value,
            qualified_name=scope.scope_id.value,
            location_path=scope.name,
            span=scope.span,
            scope_id=scope.scope_id,
            properties={"scope_kind": scope.kind.value},
        )

    def build_symbol_nodes(
        self,
        repository_id: RepositoryId,
        symbols: Sequence[Symbol],
    ) -> Tuple[GraphNode, ...]:
        """Build GraphNode instances for Symbol entities."""
        nodes: List[GraphNode] = []
        for sym in symbols:
            kind = _DECLARATION_KIND_TO_NODE_KIND.get(sym.kind, NodeKind.SYMBOL)
            nid = GraphNodeId.for_node(kind, repository_id.value, sym.symbol_id.value)
            node = GraphNode(
                node_id=nid,
                kind=kind,
                name=sym.name,
                qualified_name=sym.qualified_name,
                location_path=sym.location_file_path
                if hasattr(sym, "location_file_path")
                else None,
                span=sym.location,
                symbol_id=sym.symbol_id,
                scope_id=sym.scope_id,
                properties={
                    "visibility": sym.visibility.value,
                    "signature": sym.signature_text,
                },
            )
            nodes.append(node)
        return tuple(nodes)


_DECLARATION_KIND_TO_NODE_KIND = {
    DeclarationKind.CLASS: NodeKind.CLASS,
    DeclarationKind.INTERFACE: NodeKind.INTERFACE,
    DeclarationKind.STRUCT: NodeKind.STRUCT,
    DeclarationKind.ENUM: NodeKind.ENUM,
    DeclarationKind.FUNCTION: NodeKind.FUNCTION,
    DeclarationKind.METHOD: NodeKind.METHOD,
    DeclarationKind.FIELD: NodeKind.FIELD,
    DeclarationKind.VARIABLE: NodeKind.VARIABLE,
    DeclarationKind.PARAMETER: NodeKind.PARAMETER,
    DeclarationKind.NAMESPACE: NodeKind.NAMESPACE,
}
