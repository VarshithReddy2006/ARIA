"""Reasoning pipeline value objects.

Defines ReasoningStep and ReasoningPlan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

__all__ = ["ReasoningStep", "ReasoningPlan"]


@dataclass(frozen=True)
class ReasoningStep:
    """A single step in a grounded reasoning chain.

    Attributes:
        step_index: 0-indexed step sequence.
        thought: Intermediary thought text.
        action: Optional action or observation description.
    """

    step_index: int
    thought: str
    action: Optional[str] = None

    def __post_init__(self) -> None:
        if self.step_index < 0:
            raise ValueError(f"step_index must be non-negative, got {self.step_index}")


@dataclass(frozen=True)
class ReasoningPlan:
    """Strategy plan for AI reasoning.

    Attributes:
        strategy: Planned reasoning strategy (e.g. 'direct', 'chain_of_thought').
        max_steps: Max allowed reasoning steps.
        steps: Tuple of ReasoningStep entries.
    """

    strategy: str = "direct"
    max_steps: int = 5
    steps: Tuple[ReasoningStep, ...] = ()

    def __post_init__(self) -> None:
        if self.max_steps <= 0:
            raise ValueError(f"max_steps must be positive, got {self.max_steps}")
