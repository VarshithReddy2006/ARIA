"""Sync Scheduler Port abstraction."""

from typing import Optional, Protocol, runtime_checkable

from ria.domain.common.value_objects import Timestamp
from ria.domain.sync.value_objects import RepositoryIdentity


@runtime_checkable
class SyncSchedulerPort(Protocol):
    """Protocol for managing background/recurring repository synchronization schedules.

    Preconditions: Interval seconds must be > 0.
    Postconditions: Registers or cancels background sync timers.
    """

    def schedule_sync(
        self, repo_id: RepositoryIdentity, interval_seconds: float
    ) -> None:
        """Schedule periodic background sync for repository."""
        ...

    def cancel_sync(self, repo_id: RepositoryIdentity) -> bool:
        """Cancel scheduled background sync for repository. Returns True if schedule existed."""
        ...

    def get_next_execution(self, repo_id: RepositoryIdentity) -> Optional[Timestamp]:
        """Query next scheduled execution timestamp for repository."""
        ...
