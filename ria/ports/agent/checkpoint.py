"""Checkpoint Manager Port Protocol."""

from typing import Optional, Protocol, runtime_checkable

from ria.domain.agent.entities import Checkpoint, ExecutionContext
from ria.domain.agent.value_objects import CheckpointId


@runtime_checkable
class CheckpointManagerPort(Protocol):
    """Protocol for creating and restoring execution checkpoints."""

    def create_checkpoint(
        self,
        context: ExecutionContext,
    ) -> Checkpoint:
        """Create execution snapshot checkpoint."""
        ...

    def restore_checkpoint(
        self,
        checkpoint_id: CheckpointId,
    ) -> Optional[Checkpoint]:
        """Restore checkpoint state."""
        ...
