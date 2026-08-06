"""Query Cache Store Port Definition."""

from typing import Protocol, Any, Optional


class QueryCacheStore(Protocol):
    """Port interface for query caching."""

    def get(self, key: str) -> Optional[Any]: ...

    def put(self, key: str, value: Any) -> None: ...
