"""Repository Registry Port abstraction."""

from collections.abc import Sequence
from typing import Optional, Protocol, runtime_checkable

from ria.domain.sync.entities import RepositoryState
from ria.domain.sync.value_objects import RepositoryIdentity


@runtime_checkable
class RepositoryRegistryPort(Protocol):
    """Protocol for persisting and retrieving RepositoryState aggregate roots.

    Preconditions: RepositoryIdentity must be non-null and valid.
    Postconditions: Persists repository lifecycle states atomically.
    """

    def save_state(self, state: RepositoryState) -> None:
        """Persist or update RepositoryState aggregate root."""
        ...

    def get_state(self, repo_id: RepositoryIdentity) -> Optional[RepositoryState]:
        """Load RepositoryState for a given identity, or None if not registered."""
        ...

    def list_all(self) -> Sequence[RepositoryState]:
        """Retrieve list of all registered repository states."""
        ...

    def delete_state(self, repo_id: RepositoryIdentity) -> bool:
        """Remove repository state record. Returns True if deleted, False if not found."""
        ...
