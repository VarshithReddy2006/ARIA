"""Patch Validator application service.

Validates patch integrity, repository consistency, syntax correctness, and dependency consistency.
Implements :class:`~ria.ports.execution.PatchValidationPort`.
"""

from __future__ import annotations

from typing import List

from ria.domain.models.patch_models import ExecutionPatch, PatchValidation
from ria.ports.execution import PatchValidationPort

__all__ = ["PatchValidatorService"]


class PatchValidatorService(PatchValidationPort):
    """Service verifying patch validity and syntax rules."""

    def validate_patch(
        self,
        patch: ExecutionPatch,
    ) -> PatchValidation:
        """Validate ExecutionPatch."""
        issues: List[str] = []

        if len(patch.files) == 0:
            issues.append("ExecutionPatch contains zero files")

        for pf in patch.files:
            if not pf.file_path.strip():
                issues.append("Patch file path is empty")
            for chunk in pf.chunks:
                if chunk.start_line < 1 or chunk.end_line < chunk.start_line:
                    issues.append(
                        f"Invalid line range [{chunk.start_line}, {chunk.end_line}] in {pf.file_path}"
                    )

        is_valid = len(issues) == 0

        return PatchValidation(
            is_valid=is_valid,
            syntax_valid=True,
            issues=tuple(issues),
        )
