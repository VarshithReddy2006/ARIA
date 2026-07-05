"""AI Engineering Advisor (AEA) — Pipeline Service.

Implements a deterministic orchestration pipeline:

  RecommendationAggregator
        ↓
  DuplicateResolver
        ↓
  PriorityEngine
        ↓
  EffortEstimator
        ↓
  RoadmapPlanner
        ↓
  AdvisorService (coordinator + persistence)

No new repository analysis is performed here.
The Advisor consumes existing intelligence outputs only.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from models.advisor import AdvisorRecommendation, AdvisorReport, RoadmapPhase

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

_CATEGORY_TO_PHASE: Dict[str, int] = {
    "security": 1,
    "dependency": 1,
    "architecture": 2,
    "dead_code": 2,
    "performance": 3,
    "complexity": 3,
    "documentation": 4,
    "testing": 4,
    "general": 4,
}

_PHASE_META: Dict[int, Tuple[str, str]] = {
    1: ("Phase 1 — Security & Stability", "Resolve critical security vulnerabilities and stability blockers."),
    2: ("Phase 2 — Architecture & Structure", "Improve architectural boundaries and remove structural debt."),
    3: ("Phase 3 — Performance & Complexity", "Optimize hot paths and reduce code complexity."),
    4: ("Phase 4 — Maintainability", "Improve documentation, test coverage, and long-term maintainability."),
}

_EFFORT_LEVELS = [
    (1, "< 2 hours"),
    (3, "Half day"),
    (8, "1 day"),
    (24, "2–3 days"),
    (40, "1 week"),
    (float("inf"), "Multi-week"),
]

# ---------------------------------------------------------------------------
# 1. Recommendation Aggregator
# ---------------------------------------------------------------------------


class RecommendationAggregator:
    """Collects and normalises recommendations from all supported platform sources.

    Consumes existing outputs only — no new analysis is performed.
    """

    # ------------------------------------------------------------------
    # Source: Repository Inspector findings
    # ------------------------------------------------------------------

    def from_inspection_report(self, report: Dict[str, Any]) -> List[AdvisorRecommendation]:
        """Normalises InspectionReport findings into AdvisorRecommendations."""
        results: List[AdvisorRecommendation] = []
        for finding in report.get("findings", []):
            for raw_rec in finding.get("recommendations", []):
                results.append(
                    AdvisorRecommendation(
                        id=str(uuid.uuid4()),
                        title=finding.get("title", "Inspection Finding"),
                        description=f"{finding.get('description', '')}  Recommendation: {raw_rec}",
                        category=finding.get("category", "general"),
                        priority=finding.get("severity", "low"),
                        estimated_effort=finding.get("estimated_effort", "unknown"),
                        confidence=float(finding.get("confidence", 0.8)),
                        sources=["RepositoryInspector"],
                        affected_entities=list(finding.get("affected_entities", [])),
                        evidence=list(finding.get("evidence", [])),
                        metadata={"finding_id": finding.get("id", "")},
                    )
                )
            # If no recommendations, create one from the finding itself
            if not finding.get("recommendations"):
                results.append(
                    AdvisorRecommendation(
                        id=str(uuid.uuid4()),
                        title=finding.get("title", "Inspection Finding"),
                        description=finding.get("description", ""),
                        category=finding.get("category", "general"),
                        priority=finding.get("severity", "low"),
                        estimated_effort=finding.get("estimated_effort", "unknown"),
                        confidence=float(finding.get("confidence", 0.8)),
                        sources=["RepositoryInspector"],
                        affected_entities=list(finding.get("affected_entities", [])),
                        evidence=list(finding.get("evidence", [])),
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Source: Engineering Reasoning Engine
    # ------------------------------------------------------------------

    def from_reasoning_result(self, reasoning: Dict[str, Any]) -> List[AdvisorRecommendation]:
        """Normalises EngineeringReasoningResult recommendations."""
        results: List[AdvisorRecommendation] = []
        for rec in reasoning.get("recommendations", []):
            results.append(
                AdvisorRecommendation(
                    id=str(uuid.uuid4()),
                    title=rec.get("title", "Engineering Recommendation"),
                    description=rec.get("rationale", rec.get("description", "")),
                    category=rec.get("category", "general"),
                    priority=rec.get("priority", "medium"),
                    estimated_effort=rec.get("estimated_effort", "unknown"),
                    confidence=float(rec.get("confidence", 0.75)),
                    sources=["EngineeringReasoningEngine"],
                    affected_entities=list(rec.get("related_entities", [])),
                    evidence=list(rec.get("evidence_ids", [])),
                )
            )
        return results

    # ------------------------------------------------------------------
    # Source: Engineering Memory trends
    # ------------------------------------------------------------------

    def from_memory_context(self, memory: Dict[str, Any]) -> List[AdvisorRecommendation]:
        """Derives recommendations from recurring trend signals in Engineering Memory."""
        results: List[AdvisorRecommendation] = []
        for trend in memory.get("trends", []):
            if trend.get("direction") == "degrading":
                results.append(
                    AdvisorRecommendation(
                        id=str(uuid.uuid4()),
                        title=f"Recurring degradation in {trend.get('metric', 'unknown metric')}",
                        description=(
                            f"The '{trend.get('metric')}' metric has been degrading "
                            f"over the past {trend.get('window', 'N')} snapshots. "
                            "Prioritize stabilization before it impacts production."
                        ),
                        category="architecture",
                        priority="high",
                        estimated_effort="1 day",
                        confidence=float(trend.get("confidence", 0.7)),
                        sources=["EngineeringMemory"],
                        recurrence_count=int(trend.get("window", 1)),
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Source: Continuous Monitoring run
    # ------------------------------------------------------------------

    def from_monitoring_run(self, run: Dict[str, Any]) -> List[AdvisorRecommendation]:
        """Derives a recommendation when a monitoring run flags elevated severity."""
        results: List[AdvisorRecommendation] = []
        finding_counts = run.get("finding_counts", {})
        critical_count = int(finding_counts.get("critical", 0))
        high_count = int(finding_counts.get("high", 0))

        if critical_count > 0:
            results.append(
                AdvisorRecommendation(
                    id=str(uuid.uuid4()),
                    title=f"Monitoring detected {critical_count} critical finding(s)",
                    description=(
                        f"The latest monitoring run (trigger: {run.get('trigger', 'unknown')}) "
                        f"detected {critical_count} critical findings. "
                        "Immediate remediation is required."
                    ),
                    category="security",
                    priority="critical",
                    estimated_effort="< 2 hours",
                    confidence=0.95,
                    sources=["ContinuousMonitoring"],
                    recurrence_count=1,
                    metadata={"run_id": run.get("id", ""), "trigger": run.get("trigger", "")},
                )
            )
        elif high_count > 0:
            results.append(
                AdvisorRecommendation(
                    id=str(uuid.uuid4()),
                    title=f"Monitoring detected {high_count} high-severity finding(s)",
                    description=(
                        f"The latest monitoring run detected {high_count} high-severity findings. "
                        "Review and schedule remediation within the current sprint."
                    ),
                    category="architecture",
                    priority="high",
                    estimated_effort="Half day",
                    confidence=0.85,
                    sources=["ContinuousMonitoring"],
                    recurrence_count=1,
                    metadata={"run_id": run.get("id", ""), "trigger": run.get("trigger", "")},
                )
            )
        return results

    # ------------------------------------------------------------------
    # Source: Graph-RAG validated recommendations
    # ------------------------------------------------------------------

    def from_graph_rag_result(self, rag_result: Dict[str, Any]) -> List[AdvisorRecommendation]:
        """Imports pre-validated recommendations from a Graph-RAG response."""
        results: List[AdvisorRecommendation] = []
        for rec in rag_result.get("recommendations", []):
            if not rag_result.get("grounded", True):
                continue  # Skip ungrounded recommendations
            results.append(
                AdvisorRecommendation(
                    id=str(uuid.uuid4()),
                    title=rec.get("title", "Graph-RAG Recommendation"),
                    description=rec.get("description", ""),
                    category=rec.get("category", "general"),
                    priority=rec.get("priority", "medium"),
                    estimated_effort=rec.get("estimated_effort", "unknown"),
                    confidence=float(rag_result.get("confidence", 0.7)),
                    sources=["GraphRAG"],
                    affected_entities=list(rec.get("entities", [])),
                )
            )
        return results

    def aggregate(
        self,
        inspection_report: Optional[Dict[str, Any]] = None,
        reasoning_result: Optional[Dict[str, Any]] = None,
        memory_context: Optional[Dict[str, Any]] = None,
        monitoring_run: Optional[Dict[str, Any]] = None,
        graph_rag_result: Optional[Dict[str, Any]] = None,
    ) -> List[AdvisorRecommendation]:
        """Combines all available sources into a single flat recommendation list."""
        all_recs: List[AdvisorRecommendation] = []
        if inspection_report:
            all_recs.extend(self.from_inspection_report(inspection_report))
        if reasoning_result:
            all_recs.extend(self.from_reasoning_result(reasoning_result))
        if memory_context:
            all_recs.extend(self.from_memory_context(memory_context))
        if monitoring_run:
            all_recs.extend(self.from_monitoring_run(monitoring_run))
        if graph_rag_result:
            all_recs.extend(self.from_graph_rag_result(graph_rag_result))
        return all_recs


# ---------------------------------------------------------------------------
# 2. Duplicate Resolver
# ---------------------------------------------------------------------------


class DuplicateResolver:
    """Merges duplicate recommendations preserving evidence and provenance."""

    _SIMILARITY_THRESHOLD = 0.72

    def _similar(self, a: str, b: str) -> bool:
        return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= self._SIMILARITY_THRESHOLD

    def _same_entity_overlap(self, a: AdvisorRecommendation, b: AdvisorRecommendation) -> bool:
        """Returns True when the two recommendations share at least one affected entity."""
        set_a = set(a.affected_entities)
        set_b = set(b.affected_entities)
        return bool(set_a & set_b)

    def resolve(self, recs: List[AdvisorRecommendation]) -> List[AdvisorRecommendation]:
        """Returns a deduplicated list where overlapping recommendations are merged."""
        merged: List[AdvisorRecommendation] = []

        for candidate in recs:
            matched: Optional[AdvisorRecommendation] = None
            for existing in merged:
                title_similar = self._similar(existing.title, candidate.title)
                same_category = existing.category == candidate.category
                entity_overlap = self._same_entity_overlap(existing, candidate)

                if title_similar or (same_category and entity_overlap):
                    matched = existing
                    break

            if matched is not None:
                # Merge provenance
                for src in candidate.sources:
                    if src not in matched.sources:
                        matched.sources.append(src)
                for ev in candidate.evidence:
                    if ev not in matched.evidence:
                        matched.evidence.append(ev)
                for ent in candidate.affected_entities:
                    if ent not in matched.affected_entities:
                        matched.affected_entities.append(ent)
                # Take maximum confidence
                matched.confidence = round(max(matched.confidence, candidate.confidence), 2)
                # Escalate priority if higher
                if _PRIORITY_ORDER.get(candidate.priority, 0) > _PRIORITY_ORDER.get(matched.priority, 0):
                    matched.priority = candidate.priority
                # Accumulate recurrence
                matched.recurrence_count += candidate.recurrence_count
            else:
                merged.append(candidate.model_copy(deep=True))

        return merged


# ---------------------------------------------------------------------------
# 3. Priority Engine
# ---------------------------------------------------------------------------


class PriorityEngine:
    """Assigns deterministic priority scores and labels to every recommendation."""

    # Scoring weights (all additive)
    _PRIORITY_BASE = {"critical": 100, "high": 60, "medium": 30, "low": 10}
    _CATEGORY_BONUS = {
        "security": 30,
        "dependency": 20,
        "architecture": 15,
        "dead_code": 5,
        "performance": 10,
        "complexity": 8,
        "documentation": 3,
        "testing": 5,
        "general": 0,
    }
    _RECURRENCE_BONUS_PER_RUN = 5
    _MAX_RECURRENCE_BONUS = 25
    _CONFIDENCE_MULTIPLIER = 1.0  # applied to total score

    def _compute_score(self, rec: AdvisorRecommendation) -> float:
        base = self._PRIORITY_BASE.get(rec.priority, 10)
        category_bonus = self._CATEGORY_BONUS.get(rec.category, 0)
        recurrence_bonus = min(
            self._RECURRENCE_BONUS_PER_RUN * (rec.recurrence_count - 1),
            self._MAX_RECURRENCE_BONUS,
        )
        entity_bonus = min(len(rec.affected_entities) * 2, 20)
        raw = (base + category_bonus + recurrence_bonus + entity_bonus) * rec.confidence
        return round(raw, 2)

    def _score_to_label(self, score: float) -> str:
        if score >= 100:
            return "critical"
        if score >= 60:
            return "high"
        if score >= 30:
            return "medium"
        return "low"

    def prioritize(self, recs: List[AdvisorRecommendation]) -> List[AdvisorRecommendation]:
        """Rescores and reorders recommendations by deterministic priority."""
        for rec in recs:
            score = self._compute_score(rec)
            rec.priority = self._score_to_label(score)
            rec.metadata["priority_score"] = score

        recs.sort(key=lambda r: r.metadata.get("priority_score", 0), reverse=True)
        return recs


# ---------------------------------------------------------------------------
# 4. Effort Estimator
# ---------------------------------------------------------------------------


class EffortEstimator:
    """Assigns deterministic effort estimates based on existing metadata."""

    _CATEGORY_BASE_HOURS = {
        "security": 2,
        "dependency": 1,
        "architecture": 8,
        "dead_code": 1,
        "performance": 4,
        "complexity": 6,
        "documentation": 2,
        "testing": 4,
        "general": 3,
    }

    def _hours_to_label(self, hours: float) -> str:
        for threshold, label in _EFFORT_LEVELS:
            if hours <= threshold:
                return label
        return "Multi-week"

    def _estimate_hours(self, rec: AdvisorRecommendation) -> float:
        base = self._CATEGORY_BASE_HOURS.get(rec.category, 3)
        # Scale by number of affected entities (diminishing returns)
        entity_factor = 1.0 + min(len(rec.affected_entities) * 0.25, 2.0)
        # Critical items typically require additional triage and review time
        priority_factor = {"critical": 1.5, "high": 1.2, "medium": 1.0, "low": 0.8}.get(rec.priority, 1.0)
        return round(base * entity_factor * priority_factor, 1)

    def estimate(self, recs: List[AdvisorRecommendation]) -> List[AdvisorRecommendation]:
        """Fills `estimated_effort` for any recommendation lacking an explicit value."""
        for rec in recs:
            if rec.estimated_effort in ("unknown", "", None):
                hours = self._estimate_hours(rec)
                rec.estimated_effort = self._hours_to_label(hours)
                rec.metadata["estimated_hours"] = hours
        return recs


# ---------------------------------------------------------------------------
# 5. Roadmap Planner
# ---------------------------------------------------------------------------


class RoadmapPlanner:
    """Groups prioritized recommendations into ordered execution phases."""

    def _effort_label_to_hours(self, label: str) -> float:
        mapping = {
            "< 2 hours": 1.5,
            "Half day": 4.0,
            "1 day": 8.0,
            "2–3 days": 20.0,
            "1 week": 40.0,
            "Multi-week": 80.0,
        }
        return mapping.get(label, 8.0)

    def _aggregate_effort(self, recs: List[AdvisorRecommendation]) -> str:
        total_hours = sum(self._effort_label_to_hours(r.estimated_effort) for r in recs)
        for threshold, label in _EFFORT_LEVELS:
            if total_hours <= threshold:
                return label
        return "Multi-week"

    def plan(self, recs: List[AdvisorRecommendation]) -> List[RoadmapPhase]:
        """Organises recommendations into phases without generating new recommendations."""
        phase_buckets: Dict[int, List[AdvisorRecommendation]] = {1: [], 2: [], 3: [], 4: []}

        for rec in recs:
            phase = _CATEGORY_TO_PHASE.get(rec.category, 4)
            # Critical items always escalate to Phase 1
            if rec.priority == "critical":
                phase = 1
            phase_buckets[phase].append(rec)

        phases: List[RoadmapPhase] = []
        for phase_num in sorted(phase_buckets):
            bucket = phase_buckets[phase_num]
            if not bucket:
                continue
            title, description = _PHASE_META[phase_num]
            phases.append(
                RoadmapPhase(
                    phase=phase_num,
                    title=title,
                    description=description,
                    recommendations=bucket,
                    estimated_total_effort=self._aggregate_effort(bucket),
                )
            )
        return phases


# ---------------------------------------------------------------------------
# 6. Advisor Service
# ---------------------------------------------------------------------------


class AdvisorService:
    """Coordinates the full AEA pipeline and manages report persistence."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base_dir = base_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "advisor",
        )
        self.aggregator = RecommendationAggregator()
        self.resolver = DuplicateResolver()
        self.priority_engine = PriorityEngine()
        self.effort_estimator = EffortEstimator()
        self.roadmap_planner = RoadmapPlanner()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _repo_dir(self, repo_name: str) -> str:
        safe = repo_name.replace("/", "_").replace("\\", "_")
        path = os.path.join(self.base_dir, safe)
        os.makedirs(path, exist_ok=True)
        return path

    def _save(self, report: AdvisorReport) -> None:
        dir_path = self._repo_dir(report.repository)
        ts_path = os.path.join(dir_path, f"{int(report.generated_at)}.json")
        latest_path = os.path.join(dir_path, "latest.json")
        payload = report.model_dump()
        for path in (ts_path, latest_path):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        logger.info("Saved AdvisorReport for '%s' to %s", report.repository, latest_path)

    def load_latest(self, repo_name: str) -> Optional[AdvisorReport]:
        """Loads the latest persisted AdvisorReport."""
        path = os.path.join(self._repo_dir(repo_name), "latest.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return AdvisorReport.model_validate(json.load(fh))
        except Exception as exc:
            logger.error("Failed to load AdvisorReport: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def _compute_statistics(
        self,
        recs: List[AdvisorRecommendation],
        roadmap: List[RoadmapPhase],
    ) -> Dict[str, Any]:
        by_priority: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        by_category: Dict[str, int] = {}
        for rec in recs:
            by_priority[rec.priority] = by_priority.get(rec.priority, 0) + 1
            by_category[rec.category] = by_category.get(rec.category, 0) + 1
        return {
            "total_recommendations": len(recs),
            "by_priority": by_priority,
            "by_category": by_category,
            "phases": len(roadmap),
        }

    def _overall_priority(self, recs: List[AdvisorRecommendation]) -> str:
        if not recs:
            return "low"
        highest = max((_PRIORITY_ORDER.get(r.priority, 0) for r in recs), default=0)
        return {4: "critical", 3: "high", 2: "medium", 1: "low"}.get(highest, "low")

    def advise(
        self,
        repo_name: str,
        inspection_report: Optional[Dict[str, Any]] = None,
        reasoning_result: Optional[Dict[str, Any]] = None,
        memory_context: Optional[Dict[str, Any]] = None,
        monitoring_run: Optional[Dict[str, Any]] = None,
        graph_rag_result: Optional[Dict[str, Any]] = None,
    ) -> AdvisorReport:
        """Runs the full AEA pipeline and returns a persisted AdvisorReport."""
        generated_at = time.time()

        # Stage 1 — Aggregate from all sources
        raw = self.aggregator.aggregate(
            inspection_report=inspection_report,
            reasoning_result=reasoning_result,
            memory_context=memory_context,
            monitoring_run=monitoring_run,
            graph_rag_result=graph_rag_result,
        )

        # Stage 2 — Resolve duplicates
        resolved = self.resolver.resolve(raw)

        # Stage 3 — Prioritize
        prioritized = self.priority_engine.prioritize(resolved)

        # Stage 4 — Estimate effort
        estimated = self.effort_estimator.estimate(prioritized)

        # Stage 5 — Build roadmap
        roadmap = self.roadmap_planner.plan(estimated)

        # Build report
        report = AdvisorReport(
            repository=repo_name,
            generated_at=generated_at,
            overall_priority=self._overall_priority(estimated),
            recommendations=estimated,
            roadmap=roadmap,
            statistics=self._compute_statistics(estimated, roadmap),
            metadata={
                "sources_consulted": [
                    s for s, v in [
                        ("inspection_report", inspection_report),
                        ("reasoning_result", reasoning_result),
                        ("memory_context", memory_context),
                        ("monitoring_run", monitoring_run),
                        ("graph_rag_result", graph_rag_result),
                    ] if v is not None
                ],
                "pipeline_stages": [
                    "RecommendationAggregator",
                    "DuplicateResolver",
                    "PriorityEngine",
                    "EffortEstimator",
                    "RoadmapPlanner",
                ],
            },
        )

        self._save(report)
        return report
