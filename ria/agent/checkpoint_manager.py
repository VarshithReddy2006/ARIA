"""Checkpoint Manager implementing CheckpointManagerPort."""

import time
from typing import Dict, Optional

from ria.domain.common.value_objects import UUIDv4
from ria.domain.agent.entities import Checkpoint, ExecutionContext
from ria.domain.agent.value_objects import CheckpointId
from ria.ports.agent.checkpoint import CheckpointManagerPort


class CheckpointManager(CheckpointManagerPort):
    """In-memory manager creating and restoring execution checkpoints."""

    def __init__(self) -> None:
        self._checkpoints: Dict[str, Checkpoint] = {}

    def create_checkpoint(
        self,
        context: ExecutionContext,
    ) -> Checkpoint:
        cid = CheckpointId(value=UUIDv4.generate().value)
        cp = Checkpoint(
            checkpoint_id=cid,
            goal_id=context.goal.goal_id,
            timestamp_str=str(time.time()),
            context_state={
                "context_id": context.context_id,
                "completed_tasks": [t.value for t in context.completed_tasks],
            },
        )
        self._checkpoints[cid.value] = cp
        return cp

    def restore_checkpoint(
        self,
        checkpoint_id: CheckpointId,
    ) -> Optional[Checkpoint]:
        return self._checkpoints.get(checkpoint_id.value)
