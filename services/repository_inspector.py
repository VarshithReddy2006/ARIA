"""Autonomous Repository Inspector — Pipeline Coordinator.

Implements InspectionPlanner, FindingAggregator, SeverityEngine,
ConfidenceEngine, RecommendationPlanner, and the main RepositoryInspector.
"""

from __future__ import annotations

import json
import logging
import os
import time
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from models.inspection import Finding, InspectionContext, InspectionReport
from services.inspection import (
    ArchitectureInspector,
    ComplexityInspector,
    DeadCodeInspector,
    DependencyInspector,
    DocumentationInspector,
    InspectionPack,
    PerformanceInspector,
    SecurityInspector,
    TestingInspector,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}

# ---------------------------------------------------------------------------
# Inspection Planner
# ---------------------------------------------------------------------------


class InspectionPlanner:
    """Resolves which inspection packs should execute given a requested policy."""

    _ALL: List[InspectionPack] = [
        ArchitectureInspector(),
        SecurityInspector(),
        PerformanceInspector(),
        DependencyInspector(),
        ComplexityInspector(),
        DeadCodeInspector(),
        DocumentationInspector(),
        TestingInspector(),
    ]

    _POLICY_MAP: Dict[str, List[str]] = {
        "architecture": [
            "ArchitectureInspector",
            "DependencyInspector",
            "ComplexityInspector",
        ],
        "security": ["SecurityInspector", "DependencyInspector"],
        "performance": ["PerformanceInspector", "ComplexityInspector"],
        "documentation": ["DocumentationInspector", "TestingInspector"],
        "default": None,  # run all
    }

    def plan(self, policy: str) -> List[InspectionPack]:
        """Returns ordered list of packs matching the requested policy."""
        policy = policy.lower().strip()
        allowed = self._POLICY_MAP.get(policy)
        if allowed is None:
            return list(self._ALL)
        return [pack for pack in self._ALL if type(pack).__name__ in allowed]


# ---------------------------------------------------------------------------
# Finding Aggregator
# ---------------------------------------------------------------------------


class FindingAggregator:
    """Deduplicates overlapping findings and merges their evidence and recommendations."""

    _SIMILARITY_THRESHOLD = 0.75

    def _similar(self, a: str, b: str) -> bool:
        """Returns True if two strings are semantically similar above the threshold."""
        ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
        return ratio >= self._SIMILARITY_THRESHOLD

    def aggregate(self, all_findings: List[Finding]) -> List[Finding]:
        """Merges duplicate findings into a single representative finding per issue."""
        merged: List[Finding] = []

        for candidate in all_findings:
            merged_into = None
            for existing in merged:
                if existing.category == candidate.category and self._similar(
                    existing.title, candidate.title
                ):
                    merged_into = existing
                    break

            if merged_into is not None:
                # Merge evidence, entities, and recommendations
                for e in candidate.evidence:
                    if e not in merged_into.evidence:
                        merged_into.evidence.append(e)
                for entity in candidate.affected_entities:
                    if entity not in merged_into.affected_entities:
                        merged_into.affected_entities.append(entity)
                for rec in candidate.recommendations:
                    if rec not in merged_into.recommendations:
                        merged_into.recommendations.append(rec)
                for path in candidate.graph_paths:
                    if path not in merged_into.graph_paths:
                        merged_into.graph_paths.append(path)
                # Escalate severity if candidate's is higher
                if _SEVERITY_ORDER.get(candidate.severity, 0) > _SEVERITY_ORDER.get(
                    merged_into.severity, 0
                ):
                    merged_into.severity = candidate.severity
                # Take max confidence
                merged_into.confidence = max(
                    merged_into.confidence, candidate.confidence
                )
            else:
                merged.append(candidate.model_copy(deep=True))

        return merged


# ---------------------------------------------------------------------------
# Severity Engine
# ---------------------------------------------------------------------------


class SeverityEngine:
    """Deterministically rescores finding severity using repository metrics."""

    def rescore(
        self, findings: List[Finding], twin_data: Dict[str, Any]
    ) -> List[Finding]:
        """Adjusts severity scores based on repository context signals."""
        twin_metadata = twin_data.get("metadata", {}) or {}
        health_score = float(twin_metadata.get("health_score", 100.0) or 100.0)
        complexity = float(twin_metadata.get("complexity", 1.0) or 1.0)
        dep_count = int(twin_metadata.get("dependency_count", 0) or 0)

        for finding in findings:
            current_rank = _SEVERITY_ORDER.get(finding.severity, 1)

            # Escalate findings when overall health is critically low
            if health_score < 50.0 and current_rank < _SEVERITY_ORDER["high"]:
                if current_rank == _SEVERITY_ORDER["medium"]:
                    finding.severity = "high"
                elif current_rank == _SEVERITY_ORDER["low"]:
                    finding.severity = "medium"

            # Escalate complexity-related findings when codebase complexity is extreme
            if finding.category == "complexity" and complexity > 8.0:
                if current_rank < _SEVERITY_ORDER["high"]:
                    finding.severity = "high"

            # Escalate dependency findings when there are many
            if (
                finding.category == "dependency"
                and dep_count > 50
                and current_rank < _SEVERITY_ORDER["high"]
            ):
                finding.severity = "high"

        return findings


# ---------------------------------------------------------------------------
# Confidence Engine
# ---------------------------------------------------------------------------


class ConfidenceEngine:
    """Deterministically calculates composite confidence scores from multiple signals."""

    def rescore(
        self, findings: List[Finding], twin_data: Dict[str, Any]
    ) -> List[Finding]:
        """Adjusts finding confidence given evidence quality and repository signals."""
        twin_metadata = twin_data.get("metadata", {}) or {}
        files_count = int(twin_metadata.get("files_count", 0) or 0)

        for finding in findings:
            base_confidence = finding.confidence
            # Reward findings with more evidence
            evidence_bonus = min(0.05 * len(finding.evidence), 0.15)
            # Penalize findings with too few affected entities if many files exist
            entity_penalty = 0.0
            if files_count > 20 and len(finding.affected_entities) == 0:
                entity_penalty = 0.10
            adjusted = min(
                1.0, max(0.0, base_confidence + evidence_bonus - entity_penalty)
            )
            finding.confidence = round(adjusted, 2)

        return findings


# ---------------------------------------------------------------------------
# Recommendation Planner
# ---------------------------------------------------------------------------


class RecommendationPlanner:
    """Enriches findings with structured, actionable engineering recommendations."""

    _CATEGORY_TEMPLATES: Dict[str, Tuple[str, str]] = {
        "architecture": (
            "Refactor component boundaries using SOLID principles.",
            "4 hours",
        ),
        "security": (
            "Perform a dedicated security audit and patch all critical CVEs.",
            "2 hours",
        ),
        "performance": (
            "Profile and optimize identified hot-path functions.",
            "4 hours",
        ),
        "dependency": (
            "Run `pip list --outdated` or equivalent and upgrade affected packages.",
            "2 hours",
        ),
        "complexity": (
            "Decompose complex functions into focused, testable units.",
            "4 hours",
        ),
        "dead_code": (
            "Use a linter or code coverage tool to prune unused declarations.",
            "1 hour",
        ),
        "documentation": (
            "Add docstrings and update README.md with architecture notes.",
            "2 hours",
        ),
        "testing": (
            "Write unit tests covering critical flows with ≥80% coverage targets.",
            "4 hours",
        ),
    }

    def enrich(self, findings: List[Finding]) -> List[Finding]:
        """Ensures every finding has at least one actionable recommendation."""
        for finding in findings:
            if not finding.recommendations:
                category = finding.category
                template_rec, template_effort = self._CATEGORY_TEMPLATES.get(
                    category, ("Review and remediate the identified issue.", "2 hours")
                )
                finding.recommendations.append(template_rec)
                if (
                    finding.estimated_effort == "unknown"
                    or not finding.estimated_effort
                ):
                    finding.estimated_effort = template_effort

        return findings


# ---------------------------------------------------------------------------
# Repository Inspector
# ---------------------------------------------------------------------------


class RepositoryInspector:
    """Main orchestrator that coordinates inspection packs and produces inspection reports."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        if base_dir is None:
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data",
                "inspection_reports",
            )
        self.base_dir = base_dir
        self.planner = InspectionPlanner()
        self.aggregator = FindingAggregator()
        self.severity_engine = SeverityEngine()
        self.confidence_engine = ConfidenceEngine()
        self.recommendation_planner = RecommendationPlanner()

    def _get_repo_dir(self, repo_name: str) -> str:
        safe = repo_name.replace("/", "_").replace("\\", "_")
        path = os.path.join(self.base_dir, safe)
        os.makedirs(path, exist_ok=True)
        return path

    def _save_report(self, repo_name: str, report: InspectionReport) -> None:
        """Saves the report to a separate inspection_reports layout."""
        dir_path = self._get_repo_dir(repo_name)
        # Save timestamped copy
        ts_path = os.path.join(dir_path, f"{int(report.timestamp)}.json")
        # Save latest
        latest_path = os.path.join(dir_path, "latest.json")
        payload = report.model_dump()
        for path in (ts_path, latest_path):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        logger.info("Saved InspectionReport for '%s' to %s", repo_name, latest_path)

    def load_latest(self, repo_name: str) -> Optional[InspectionReport]:
        """Loads the latest persisted inspection report for a repository."""
        latest_path = os.path.join(self._get_repo_dir(repo_name), "latest.json")
        if not os.path.exists(latest_path):
            return None
        try:
            with open(latest_path, "r", encoding="utf-8") as fh:
                return InspectionReport.model_validate(json.load(fh))
        except Exception as exc:
            logger.error("Failed to load inspection report: %s", exc)
            return None

    def _compute_overall_score(self, findings: List[Finding]) -> float:
        """Derives an overall 0–100 repository health score from findings."""
        if not findings:
            return 100.0
        deductions = {
            "critical": 15.0,
            "high": 8.0,
            "medium": 4.0,
            "low": 2.0,
            "info": 0.5,
        }
        total_deduction = sum(
            deductions.get(f.severity, 0) * f.confidence for f in findings
        )
        return round(max(0.0, 100.0 - total_deduction), 1)

    def _compute_statistics(self, findings: List[Finding]) -> Dict[str, Any]:
        """Computes severity distribution and category breakdown."""
        stats: Dict[str, Any] = {
            "total_findings": len(findings),
            "by_severity": {s: 0 for s in _SEVERITY_ORDER},
            "by_category": {},
        }
        for f in findings:
            stats["by_severity"][f.severity] = (
                stats["by_severity"].get(f.severity, 0) + 1
            )
            stats["by_category"][f.category] = (
                stats["by_category"].get(f.category, 0) + 1
            )
        return stats

    def inspect(
        self,
        repo_name: str,
        twin_data: Dict[str, Any],
        knowledge_graph_data: Dict[str, Any],
        memory_context: Optional[Dict[str, Any]] = None,
        policy: str = "default",
    ) -> InspectionReport:
        """Runs the full inspection pipeline and returns a structured InspectionReport."""
        start_ts = time.time()

        context = InspectionContext(
            repository=repo_name,
            twin=twin_data,
            knowledge_graph=knowledge_graph_data,
            memory_context=memory_context,
            metadata={"policy": policy},
        )

        # 1. Plan which packs to run
        packs = self.planner.plan(policy)
        logger.info(
            "Running %d inspection packs for '%s' (policy=%s)",
            len(packs),
            repo_name,
            policy,
        )

        # 2. Execute each pack independently and collect raw findings
        raw_findings: List[Finding] = []
        for pack in packs:
            try:
                pack_findings = pack.inspect(context)
                raw_findings.extend(pack_findings)
            except Exception as exc:
                logger.error(
                    "Pack %s failed: %s", type(pack).__name__, exc, exc_info=True
                )

        # 3. Aggregate (deduplicate and merge)
        aggregated = self.aggregator.aggregate(raw_findings)

        # 4. Rescore severity
        rescored = self.severity_engine.rescore(aggregated, twin_data)

        # 5. Rescore confidence
        rescored = self.confidence_engine.rescore(rescored, twin_data)

        # 6. Enrich recommendations
        enriched = self.recommendation_planner.enrich(rescored)

        # 7. Sort by severity descending
        enriched.sort(key=lambda f: _SEVERITY_ORDER.get(f.severity, 0), reverse=True)

        # 8. Build report
        overall_score = self._compute_overall_score(enriched)
        statistics = self._compute_statistics(enriched)
        elapsed_ms = round((time.time() - start_ts) * 1000, 1)

        report = InspectionReport(
            repository=repo_name,
            timestamp=start_ts,
            overall_score=overall_score,
            findings=enriched,
            statistics=statistics,
            summary={
                "total_findings": len(enriched),
                "overall_score": overall_score,
                "top_concern": enriched[0].title if enriched else "No issues found.",
            },
            inspection_metadata={
                "policy": policy,
                "packs_run": [type(p).__name__ for p in packs],
                "elapsed_ms": elapsed_ms,
                "analysis_version": "1.0",
            },
        )

        # 9. Persist separately from Engineering Memory
        self._save_report(repo_name, report)
        return report
