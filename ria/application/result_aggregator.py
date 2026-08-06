"""Result Aggregator application service.

Merges individual agent outputs, evidence snippets, citations, and reasoning metadata into an ExecutionReport.
Implements :class:`~ria.ports.agent.ResultAggregatorPort`.
"""

from __future__ import annotations

from typing import List, Tuple

from ria.domain.models.agent_result import AgentStatistics, ExecutionReport
from ria.domain.models.agent_task import TaskResult
from ria.domain.models.prompt_context import ContextCitation
from ria.ports.agent import ResultAggregatorPort

__all__ = ["ResultAggregatorService"]


class ResultAggregatorService(ResultAggregatorPort):
    """Service aggregating agent task outputs into a unified ExecutionReport."""

    def aggregate_results(
        self,
        session_id: str,
        task_results: Tuple[TaskResult, ...],
    ) -> ExecutionReport:
        """Merge TaskResults into final ExecutionReport."""
        summary_blocks: List[str] = []
        citations: List[ContextCitation] = []
        succeeded = 0
        failed = 0

        for r in task_results:
            if r.failure is not None:
                failed += 1
                summary_blocks.append(
                    f"Task {r.task_id} Failed: {r.failure.error_message}"
                )
            else:
                succeeded += 1
                summary_blocks.append(
                    f"=== Task {r.task_id} Output ===\n{r.output_text}"
                )
                if r.reasoning_result is not None:
                    for cit in r.reasoning_result.citations:
                        citations.append(
                            ContextCitation(
                                repository=cit.repository,
                                file_path=cit.file_path,
                                symbol_name=cit.symbol_name,
                            )
                        )

        summary_text = "\n\n".join(summary_blocks)
        stats = AgentStatistics(
            tasks_scheduled=len(task_results),
            tasks_succeeded=succeeded,
            tasks_failed=failed,
        )

        return ExecutionReport(
            session_id=session_id,
            summary_text=summary_text,
            task_results=task_results,
            report_citations=tuple(citations),
            statistics=stats,
        )
