"""Repository Retriever Port Definition."""

from typing import Protocol, Any


class RepositoryRetrieverPort(Protocol):
    """Port interface for repository retrieval."""

    def retrieve(self, query: Any) -> Any: ...
