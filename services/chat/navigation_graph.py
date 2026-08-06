"""Navigation Graph — Lightweight conversation entity navigation history.

Tracks movement through repository entities (files, symbols, modules) across conversation turns.
Assists relative reference resolution ("that file", "there", "previous module", "earlier service", "its dependency").
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple


@dataclass(frozen=True, slots=True)
class NavigationStep:
    """Immutable single step in conversation navigation history."""

    from_entity: Optional[str]
    to_entity: str
    transition_type: str  # e.g., "INITIAL", "FILE_TO_FILE", "FILE_TO_SYMBOL", "TOPIC_SWITCH"
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class NavigationGraph:
    """Immutable graph container tracking entity navigation history."""

    steps: Tuple[NavigationStep, ...] = ()

    def add_step(
        self,
        to_entity: str,
        transition_type: str = "NAVIGATION",
        timestamp: Optional[float] = None,
    ) -> NavigationGraph:
        """Return a new NavigationGraph with the new step added."""
        if not to_entity:
            return self

        from_ent = self.steps[-1].to_entity if self.steps else None
        ts = timestamp if timestamp is not None else time.time()
        new_step = NavigationStep(
            from_entity=from_ent,
            to_entity=to_entity,
            transition_type=transition_type,
            timestamp=ts,
        )
        return NavigationGraph(steps=self.steps + (new_step,))

    @property
    def current_entity(self) -> Optional[str]:
        return self.steps[-1].to_entity if self.steps else None

    @property
    def previous_entity(self) -> Optional[str]:
        if len(self.steps) >= 2:
            return self.steps[-2].to_entity
        return None

    def find_previous_file(self) -> Optional[str]:
        """Return the most recent file entity before the current one."""
        if not self.steps:
            return None
        current = self.steps[-1].to_entity
        for step in reversed(self.steps[:-1]):
            if step.to_entity != current and ("/" in step.to_entity or "." in step.to_entity):
                return step.to_entity
        return self.previous_entity

    def find_previous_symbol(self) -> Optional[str]:
        """Return the most recent symbol entity before the current one."""
        if not self.steps:
            return None
        current = self.steps[-1].to_entity
        for step in reversed(self.steps[:-1]):
            if step.to_entity != current and "/" not in step.to_entity and not step.to_entity.endswith(".py"):
                return step.to_entity
        return self.previous_entity
