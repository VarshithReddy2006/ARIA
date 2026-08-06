"""GraphNodeId value object.

Identifies a single node within the Repository Knowledge Graph.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

from ria.domain.enums import NodeKind

__all__ = ["GraphNodeId"]


@dataclass(frozen=True)
class GraphNodeId:
    """Opaque, immutable identifier for a GraphNode.

    Attributes:
        value: Non-empty string key.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("GraphNodeId value must be a non-empty string")

    @classmethod
    def for_node(
        cls,
        kind: NodeKind,
        repository_id: str,
        identity_path: str,
    ) -> GraphNodeId:
        """Construct a deterministic GraphNodeId for a entity kind and location/path.

        Args:
            kind: NodeKind classification.
            repository_id: Identity of the parent repository.
            identity_path: Unique qualified path or moniker for the node.

        Returns:
            Deterministic GraphNodeId.
        """
        repo_str = str(repository_id).strip()
        path_str = str(identity_path).strip()
        raw_key = f"node:{kind.value}:{repo_str}:{path_str}"
        digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
        return cls(f"gn_{kind.value[:4]}_{digest}")

    def __str__(self) -> str:
        return self.value
