"""Security Inspection Pack.

Audits security configurations, credential leaks, and vulnerabilities.
"""

import uuid
from typing import List

from models.inspection import Finding, InspectionContext
from services.inspection.base import InspectionPack


class SecurityInspector(InspectionPack):
    """Audits security settings, vulnerabilities, and credential leakage risks."""

    def inspect(self, context: InspectionContext) -> List[Finding]:
        findings = []

        compliance_summary = context.twin.get("compliance_summary", {}) or context.twin.get("compliance", {}) or {}
        vulnerabilities = compliance_summary.get("vulnerabilities", [])
        warnings = compliance_summary.get("reasons", []) or compliance_summary.get("warnings", [])

        # Parse vulnerabilities
        if vulnerabilities:
            affected = [v.get("affected_package", "unknown") for v in vulnerabilities]
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="security",
                    severity="critical",
                    confidence=1.0,
                    title="Vulnerable Packages Detected",
                    description="Known vulnerabilities (CVEs) found in project package dependencies.",
                    affected_entities=affected,
                    evidence=[
                        f"Package '{v.get('affected_package')}' version '{v.get('version')}' has CVE: {v.get('cve', 'unknown')}"
                        for v in vulnerabilities
                    ],
                    recommendations=[
                        "Upgrade package versions to patched releases.",
                        "Run dependency vulnerability checking audits regularly."
                    ],
                    estimated_effort="2 hours",
                    metadata={"vulnerabilities_count": len(vulnerabilities)},
                )
            )

        # Parse compliance warnings or raw exposures (like hardcoded keys)
        secret_warnings = [w for w in warnings if "secret" in w.lower() or "token" in w.lower() or "key" in w.lower()]
        if secret_warnings:
            findings.append(
                Finding(
                    id=str(uuid.uuid4()),
                    category="security",
                    severity="critical",
                    confidence=0.98,
                    title="Hardcoded Credentials Risk",
                    description="Possible plain-text credentials, access tokens, or private keys detected in codebase.",
                    affected_entities=["Configuration / Source Files"],
                    evidence=secret_warnings,
                    recommendations=[
                        "Revoke the exposed credentials immediately.",
                        "Migrate secrets to environment variables or a key vault manager."
                    ],
                    estimated_effort="1 hour",
                    metadata={"secret_warnings_count": len(secret_warnings)},
                )
            )

        return findings
