"""Progress event.

Ingestion of a large repository takes minutes. Without progress reporting that time
is indistinguishable from a hang, so an operator's only recourse is to kill the job —
which for a resumable pipeline is exactly the wrong response.

A progress event is a value object, not a log line. Modelling it means the same
observation can reach a log, a metrics sink and an HTTP stream without three call
sites formatting it three ways and drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ria.domain.enums import IngestionStage
from ria.domain.identity import RepositoryId

__all__ = ["ProgressEvent"]


@dataclass(frozen=True)
class ProgressEvent:
    """One observation of pipeline progress.

    Attributes:
        repository_id: Repository being processed.
        stage: Pipeline stage the observation concerns.
        at: When the observation was made.
        job_id: Job driving the work, as a string. ``None`` when the pipeline is
            invoked directly rather than through the queue, which the ingestion
            service supports so that a caller can run it synchronously.
        commit_sha: Commit being processed, when the stage concerns one.
        completed: Units of work finished within the stage.
        total: Units of work in the stage. ``None`` when not yet known — for
            example while enumerating, before the tree size is read. Reporting a
            fabricated total would produce a progress bar that jumps backwards.
        message: Human-readable detail. Never carries a secret, because events are
            logged and may be surfaced to an operator.
    """

    repository_id: RepositoryId
    stage: IngestionStage
    at: datetime
    job_id: Optional[str] = None
    commit_sha: Optional[str] = None
    completed: int = 0
    total: Optional[int] = None
    message: Optional[str] = None

    def __post_init__(self) -> None:
        if self.completed < 0:
            raise ValueError("completed must be non-negative")
        if self.total is not None:
            if self.total < 0:
                raise ValueError("total must be non-negative")
            if self.completed > self.total:
                raise ValueError(
                    f"completed ({self.completed}) cannot exceed total ({self.total})"
                )

    @property
    def fraction(self) -> Optional[float]:
        """Completion of the stage in ``[0, 1]``, or ``None`` if the total is unknown.

        ``None`` rather than zero, because an unknown total and a stage that has not
        started are different statements and a caller renders them differently.
        """
        if self.total is None:
            return None
        if self.total == 0:
            return 1.0
        return self.completed / self.total

    @property
    def is_stage_complete(self) -> bool:
        """Whether the stage has finished all its known work."""
        return self.total is not None and self.completed >= self.total

    def __str__(self) -> str:
        scope = self.commit_sha[:12] if self.commit_sha else "repository"
        if self.total is None:
            counter = str(self.completed)
        else:
            counter = f"{self.completed}/{self.total}"
        suffix = f" {self.message}" if self.message else ""
        return f"[{self.stage}] {scope} {counter}{suffix}"
