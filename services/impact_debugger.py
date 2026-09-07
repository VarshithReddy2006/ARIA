"""Impact Debugger: Generates explainable provenance traces for candidate impact files.

Enables developers, tests, evaluation, UI, and MCP to inspect *why* each file
was classified as impacted, how impact propagated from root symbols, what verified
relationships exist, and which confidence tier it belongs to.
"""

from typing import List, Dict, Any, Optional
from models.phase2 import (
    EvidenceStrength,
    ConfidenceTier,
    ImpactedFileDetail,
    TestImpactItem,
    CallerInfo,
)


class ImpactDebugger:
    """Canonical engine for tracking, explaining, and formatting file impact provenance."""

    @staticmethod
    def format_caller_explanation(caller: CallerInfo) -> str:
        """Format a single caller's semantic resolution details as human-readable text."""
        rec_info = (
            f" (receiver: {caller.receiver_expr} [{caller.receiver_type}])"
            if caller.receiver_expr
            else ""
        )
        rel_str = caller.relationship or "DIRECT_CALL"
        conf_str = caller.confidence_tier or ("HIGH" if caller.is_direct else "MEDIUM")
        loc_str = (
            f"{caller.file_path}:{caller.line_number}"
            if caller.line_number
            else caller.file_path
        )
        status_str = "RESOLVED" if rel_str != "UNRESOLVED_CALL" else "UNCERTAIN"
        return f"{caller.caller_name} -> {rel_str}{rec_info} at {loc_str} [{status_str}, Confidence: {conf_str}]"

    @staticmethod
    def create_detail(
        file_path: str,
        confidence_tier: ConfidenceTier,
        evidence_strength: EvidenceStrength,
        reason: str,
        propagation_path: Optional[List[str]] = None,
        target_symbols: Optional[List[str]] = None,
        verifications: Optional[Dict[str, Any]] = None,
        confidence_score: Optional[float] = None,
    ) -> ImpactedFileDetail:
        """Create a structured ImpactedFileDetail instance."""
        score = (
            confidence_score
            if confidence_score is not None
            else evidence_strength.weight
        )
        return ImpactedFileDetail(
            file_path=file_path,
            confidence_tier=confidence_tier.value,
            confidence_score=round(score, 2),
            evidence_strength=evidence_strength.value,
            reason=reason,
            propagation_path=propagation_path or [file_path],
            target_symbols=target_symbols or [],
            verifications=verifications or {},
        )

    @staticmethod
    def format_explanation(detail: ImpactedFileDetail) -> str:
        """Format a single file's impact justification as human-readable text."""
        lines = [
            f"File: {detail.file_path}",
            f"Classification: {detail.confidence_tier} CONFIDENCE",
            f"Evidence Strength: {detail.evidence_strength} (score: {detail.confidence_score:.2f})",
            f"Reason: {detail.reason}",
        ]
        if detail.target_symbols:
            lines.append(f"Target Symbols: {', '.join(detail.target_symbols)}")
        if len(detail.propagation_path) > 1:
            lines.append("Propagation:")
            for idx, step in enumerate(detail.propagation_path):
                prefix = "  " + ("↓ " if idx > 0 else "")
                lines.append(f"{prefix}{step}")
        if detail.verifications:
            lines.append("Verified Relationships:")
            for k, v in detail.verifications.items():
                status = "✓" if v else "✗"
                lines.append(f"  {status} {k.replace('_', ' ')}")
        return "\n".join(lines)

    @staticmethod
    def format_full_debug_report(details: List[ImpactedFileDetail]) -> str:
        """Format a multi-file debugging report grouped by confidence tier."""
        high = [d for d in details if d.confidence_tier == ConfidenceTier.HIGH.value]
        med = [d for d in details if d.confidence_tier == ConfidenceTier.MEDIUM.value]
        low = [d for d in details if d.confidence_tier == ConfidenceTier.LOW.value]

        lines = [
            "=" * 75,
            "ARIA IMPACT ANALYSIS DEBUGGER REPORT",
            "=" * 75,
            f"Total Candidates Analyzed: {len(details)}",
            f"  • HIGH Confidence:   {len(high)}",
            f"  • MEDIUM Confidence: {len(med)}",
            f"  • LOW Confidence:    {len(low)}",
            "",
        ]

        def _dump_tier(name: str, items: List[ImpactedFileDetail]):
            if not items:
                return
            lines.append("-" * 60)
            lines.append(f"[{name.upper()} CONFIDENCE FILES ({len(items)})]")
            lines.append("-" * 60)
            for it in items:
                lines.append(ImpactDebugger.format_explanation(it))
                lines.append("")

        _dump_tier("High", high)
        _dump_tier("Medium", med)
        _dump_tier("Low", low)

        return "\n".join(lines)

    @staticmethod
    def format_test_explanation(item: TestImpactItem) -> str:
        """Format a single affected test's justification as human-readable text."""
        lines = [
            f"Test File: {item.test_file}",
            f"Confidence: {item.confidence_tier} ({item.impact_type})",
            f"Evidence Strength: {item.evidence_strength}",
            f"Reason: {item.reason}",
        ]
        if item.source_reference:
            lines.append(f"Source Reference: {item.source_reference}")
        if item.propagation_path and len(item.propagation_path) > 1:
            lines.append("Propagation:")
            for idx, step in enumerate(item.propagation_path):
                prefix = "  " + ("↓ " if idx > 0 else "")
                lines.append(f"{prefix}{step}")
        if item.evidence_paths:
            lines.append(f"Evidence Paths ({len(item.evidence_paths)}):")
            for ep in item.evidence_paths:
                lvl = ep.get("level", "UNKNOWN")
                rsn = ep.get("reason", "")
                lines.append(f"  • [{lvl}] {rsn}")
        return "\n".join(lines)

    @staticmethod
    def format_test_debug_report(tests: List[TestImpactItem]) -> str:
        """Format a multi-test debugging report grouped by confidence tier."""
        high = [t for t in tests if t.confidence_tier == "HIGH"]
        med = [t for t in tests if t.confidence_tier == "MEDIUM"]
        low = [t for t in tests if t.confidence_tier == "LOW"]

        lines = [
            "=" * 75,
            "ARIA AFFECTED TESTS DEBUGGER REPORT",
            "=" * 75,
            f"Total Tests Impacted: {len(tests)}",
            f"  • HIGH Confidence:   {len(high)}",
            f"  • MEDIUM Confidence: {len(med)}",
            f"  • LOW Confidence:    {len(low)}",
            "",
        ]

        def _dump_test_tier(name: str, items: List[TestImpactItem]):
            if not items:
                return
            lines.append("-" * 60)
            lines.append(f"[{name.upper()} CONFIDENCE TESTS ({len(items)})]")
            lines.append("-" * 60)
            for it in items:
                lines.append(ImpactDebugger.format_test_explanation(it))
                lines.append("")

        _dump_test_tier("High", high)
        _dump_test_tier("Medium", med)
        _dump_test_tier("Low", low)

        return "\n".join(lines)

    @staticmethod
    def format_developer_safety_view(
        details: List[ImpactedFileDetail],
        tests: Optional[List[TestImpactItem]] = None,
    ) -> str:
        """Format an actionable developer-safety impact view (VERIFIED vs LIKELY vs CANDIDATES)."""
        verified_files = [
            d
            for d in details
            if d.confidence_tier == ConfidenceTier.HIGH.value
            and not d.verifications.get("is_test")
        ]
        likely_files = [
            d
            for d in details
            if d.confidence_tier == ConfidenceTier.MEDIUM.value
            and not d.verifications.get("is_test")
        ]
        candidate_files = [
            d
            for d in details
            if d.confidence_tier == ConfidenceTier.LOW.value
            and not d.verifications.get("is_test")
        ]

        verified_tests = [t for t in (tests or []) if t.confidence_tier == "HIGH"]
        likely_tests = [t for t in (tests or []) if t.confidence_tier == "MEDIUM"]
        candidate_tests = [t for t in (tests or []) if t.confidence_tier == "LOW"]

        lines = [
            "=" * 75,
            "DEVELOPER SAFETY IMPACT READOUT",
            "=" * 75,
            f"VERIFIED IMPACTS ({len(verified_files)} files, {len(verified_tests)} tests) [Zero-Noise Ground Truth]",
        ]
        for f in verified_files:
            lines.append(f"  ├── [FILE] {f.file_path} (via {f.evidence_strength})")
        for t in verified_tests:
            lines.append(f"  ├── [TEST] {t.test_file} (via {t.evidence_strength})")

        lines.append("")
        lines.append(
            f"LIKELY IMPACTS ({len(likely_files)} files, {len(likely_tests)} tests) [Transitive & Helper Chains]"
        )
        for f in likely_files:
            lines.append(f"  ├── [FILE] {f.file_path} ({f.reason})")
        for t in likely_tests:
            lines.append(f"  ├── [TEST] {t.test_file} ({t.reason})")

        lines.append("")
        lines.append(
            f"EXPLORATORY CANDIDATES ({len(candidate_files)} files, {len(candidate_tests)} tests) [Module Hops & Heuristics]"
        )
        for f in candidate_files[:10]:
            lines.append(f"  ├── [FILE] {f.file_path}")
        if len(candidate_files) > 10:
            lines.append(
                f"  └── ... and {len(candidate_files) - 10} more exploratory files"
            )
        for t in candidate_tests[:10]:
            lines.append(f"  ├── [TEST] {t.test_file}")

        return "\n".join(lines)
