"""Dead Code Inspection Pack.

Audits unreferenced/dead declarations, unreachable functions, and orphaned modules.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class DeadCodeInspector(InspectionPack):
    """Audits unreachable components, unused exports, and dead files."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        # Or look for warnings
        compliance_summary = (
            context.twin.get("compliance_summary", {})
            or context.twin.get("compliance", {})
            or {}
        )
        warnings = compliance_summary.get("reasons", []) or compliance_summary.get(
            "warnings", []
        )
        dead_code_warnings = [
            w
            for w in warnings
            if "unused" in w.lower()
            or "dead" in w.lower()
            or "unreferenced" in w.lower()
        ]

        if dead_code_warnings:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="dead_code",
                    severity="low",
                    confidence=0.85,
                    title="Unreferenced Code Elements Detected",
                    description="Unused declarations, imports, or dead functions remain in the codebase, cluttering the index.",
                    affected_entities=["Source Files"],
                    evidence=dead_code_warnings,
                    recommendations=[
                        "Remove or safely comment out the unreferenced elements.",
                        "Use build/lint tools to automatically prune unused imports.",
                    ],
                    estimated_effort="1 hour",
                    metadata={"dead_code_warnings_count": len(dead_code_warnings)},
                )
            )

        return findings
