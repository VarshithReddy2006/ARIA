"""Symbol Query Port Definition."""

from typing import Protocol, Any


class SymbolQueryPort(Protocol):
    """Port interface for symbol queries."""

    def query_symbols(self, query: Any) -> Any: ...
