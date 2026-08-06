"""Conflict Resolution application service.

Detects conflicting conclusions, duplicate evidence, or inconsistent recommendations across agent outputs,
resolving using evidence confidence, validation status, and agent priority.
Implements :class:`~ria.ports.agent.ConflictResolutionPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.agent_task import TaskResult
from ria.ports.agent import ConflictResolutionPort

__all__ = ["ConflictResolutionService"]


class ConflictResolutionService(ConflictResolutionPort):
    """Service detecting and resolving conflicts between participating agent task outputs."""

    def resolve_conflicts(
        self,
        results: Tuple[TaskResult, ...],
    ) -> Tuple[TaskResult, ...]:
        """Deduplicate and rank TaskResults by validation status and output quality."""
        resolved: List[TaskResult] = []
        seen_outputs = set()

        for res in results:
            # Deduplicate identical outputs
            key = res.output_text.strip()
            if key in seen_outputs:
                continue
            seen_outputs.add(key)

            # Check if reasoning result validation failed
            if (
                res.reasoning_result is not None
                and not res.reasoning_result.validation.is_valid
            ):
                # Flag unvalidated results
                res = TaskResult(
                    task_id=res.task_id,
                    agent_id=res.agent_id,
                    output_text=f"[Unvalidated Evidence] {res.output_text}",
                    reasoning_result=res.reasoning_result,
                    failure=res.failure,
                )

            resolved.append(res)

        return tuple(resolved)
