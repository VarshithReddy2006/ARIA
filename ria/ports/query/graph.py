"""Graph Query Port Definition."""

from typing import Protocol, Any


class GraphQueryPort(Protocol):
    """Port interface for graph queries."""

    def query_graph(self, query: Any) -> Any: ...
