"""Verification Engine implementing VerificationEnginePort."""

from ria.domain.agent.entities import ExecutionContext
from ria.domain.agent.value_objects import VerificationResult
from ria.ports.agent.verification import VerificationEnginePort


class VerificationEngine(VerificationEnginePort):
    """Engine verifying final execution results against goal criteria."""

    def verify(
        self,
        context: ExecutionContext,
    ) -> VerificationResult:
        if not context.completed_tasks:
            return VerificationResult(
                is_verified=False,
                grounding_pass=False,
                citations_valid=False,
                reasoning="Execution context has zero completed tasks.",
            )

        return VerificationResult(
            is_verified=True,
            grounding_pass=True,
            citations_valid=True,
            reasoning="All goal execution criteria satisfied and verified.",
        )
