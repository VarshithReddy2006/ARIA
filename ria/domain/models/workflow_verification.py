"""Workflow verification domain models.

Defines VerificationResult.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

__all__ = ["VerificationResult"]


@dataclass(frozen=True)
class VerificationResult:
    """Result status of workflow verification pipeline.

    Attributes:
        is_verified: True if all verification checks passed.
        tool_success: True if tool invocation returned success.
        evidence_consistent: True if outputs match prompt context evidence.
        issues: Tuple of reported issue string descriptions.
    """

    is_verified: bool
    tool_success: bool = True
    evidence_consistent: bool = True
    issues: Tuple[str, ...] = ()
