"""Autonomous Engineering Agent (AEA²) — Execution Planning Pipeline.

Implements a deterministic seven-stage pipeline that transforms AdvisorReport
recommendations into safe, reviewable ExecutionPlans:

  TaskDecomposer
        ↓
  DependencyResolver
        ↓
  ConflictDetector
        ↓
  ParallelizationPlanner
        ↓
  RiskAnalyzer
        ↓
  ExecutionPlannerService  (coordinator + persistence)

No repository analysis, no LLM calls, no code modifications.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple

from models.execution import (
    ConflictReport,
    ExecutionBatch,
    ExecutionPlan,
    ExecutionTask,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_RISK_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

_EFFORT_HOURS: Dict[str, float] = {
    "< 2 hours": 1.5,
    "Half day": 4.0,
    "1 day": 8.0,
    "2–3 days": 20.0,
    "1 week": 40.0,
    "Multi-week": 80.0,
    "unknown": 8.0,
}

# Task subtypes generated per recommendation category
_CATEGORY_SUBTASKS: Dict[str, List[Tuple[str, str, bool]]] = {
    # (title_suffix, description, is_rollback_point)
    "security": [
        ("Audit vulnerable dependency", "Identify and document the vulnerable package and affected versions.", False),
        ("Apply security patch", "Upgrade or replace the vulnerable dependency.", False),
        ("Verify patch", "Run security scans and integration tests to confirm resolution.", True),
    ],
    "architecture": [
        ("Identify refactoring boundaries", "Map the module boundaries that will change.", False),
        ("Refactor module structure", "Apply the structural change while preserving external interfaces.", False),
        ("Update integration points", "Adjust all callers/consumers of the modified module.", False),
        ("Verify architecture compliance", "Run architecture linting and integration tests.", True),
    ],
    "performance": [
        ("Profile hot-path", "Measure current performance baseline.", False),
        ("Implement optimization", "Apply the targeted performance improvement.", False),
        ("Benchmark and verify", "Confirm improvement against baseline and check for regressions.", True),
    ],
    "dependency": [
        ("Audit outdated dependencies", "List all affected packages and their current/target versions.", False),
        ("Upgrade dependencies", "Apply version upgrades incrementally.", False),
        ("Run compatibility tests", "Verify no breaking changes were introduced.", True),
    ],
    "complexity": [
        ("Identify complex units", "Mark functions and modules exceeding complexity thresholds.", False),
        ("Decompose complex logic", "Break large units into smaller, testable functions.", False),
        ("Verify test coverage", "Ensure decomposed units are covered by tests.", True),
    ],
    "dead_code": [
        ("Identify unused declarations", "Locate unreferenced symbols across the codebase.", False),
        ("Remove dead code", "Delete confirmed-unused declarations.", False),
        ("Verify build integrity", "Confirm the project builds and tests pass after removal.", True),
    ],
    "documentation": [
        ("Audit missing documentation", "Identify undocumented public APIs and modules.", False),
        ("Write documentation", "Add docstrings, README sections, or architecture notes.", True),
    ],
    "testing": [
        ("Audit test coverage gaps", "Identify critical code paths lacking test coverage.", False),
        ("Write missing tests", "Implement unit and integration tests for uncovered paths.", False),
        ("Verify coverage targets", "Confirm coverage meets the defined threshold.", True),
    ],
    "general": [
        ("Investigate issue", "Understand the root cause and define the remediation approach.", False),
        ("Implement remediation", "Apply the fix or improvement.", False),
        ("Verify resolution", "Confirm the issue is resolved and no regressions were introduced.", True),
    ],
}


# ---------------------------------------------------------------------------
# 1. Task Decomposer
# ---------------------------------------------------------------------------


class TaskDecomposer:
    """Splits AdvisorRecommendations into discrete, ordered ExecutionTasks."""

    def _subtask_id(self) -> str:
        return str(uuid.uuid4())

    def decompose(self, recommendations: List[Dict[str, Any]]) -> List[ExecutionTask]:
        """Returns a flat list of ExecutionTasks from all recommendations."""
        all_tasks: List[ExecutionTask] = []

        for rec in recommendations:
            category = rec.get("category", "general")
            subtask_templates = _CATEGORY_SUBTASKS.get(category, _CATEGORY_SUBTASKS["general"])
            rec_id = rec.get("id", "")
            affected = list(rec.get("affected_entities", []))
            effort = rec.get("estimated_effort", "unknown")

            prev_id: Optional[str] = None
            for suffix, description, is_rollback in subtask_templates:
                task_id = self._subtask_id()
                task = ExecutionTask(
                    id=task_id,
                    recommendation_id=rec_id,
                    title=f"{rec.get('title', 'Task')} — {suffix}",
                    description=description,
                    category=category,
                    dependencies=[prev_id] if prev_id else [],
                    estimated_effort=effort,
                    affected_entities=affected,
                    rollback_checkpoint=is_rollback,
                )
                all_tasks.append(task)
                prev_id = task_id

        return all_tasks


# ---------------------------------------------------------------------------
# 2. Dependency Resolver
# ---------------------------------------------------------------------------


class DependencyResolver:
    """Builds and validates the task dependency DAG.

    Ensures no circular dependencies using topological sort (Kahn's algorithm).
    """

    def _topological_sort(self, tasks: List[ExecutionTask]) -> List[ExecutionTask]:
        """Returns tasks in topological execution order."""
        id_map = {t.id: t for t in tasks}
        in_degree: Dict[str, int] = {t.id: 0 for t in tasks}
        adjacency: Dict[str, List[str]] = defaultdict(list)

        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in id_map:
                    adjacency[dep_id].append(task.id)
                    in_degree[task.id] += 1

        queue = deque(tid for tid, deg in in_degree.items() if deg == 0)
        ordered: List[ExecutionTask] = []

        while queue:
            tid = queue.popleft()
            ordered.append(id_map[tid])
            for neighbour in adjacency[tid]:
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        if len(ordered) != len(tasks):
            # Circular dependency detected — return original order with a warning
            logger.warning("Circular dependency detected; returning tasks in original order.")
            return tasks

        return ordered

    def resolve(self, tasks: List[ExecutionTask]) -> List[ExecutionTask]:
        """Returns tasks in valid dependency order."""
        return self._topological_sort(tasks)

    def compute_critical_path(self, tasks: List[ExecutionTask]) -> List[str]:
        """Returns the ordered task IDs forming the longest dependency chain."""
        id_map = {t.id: t for t in tasks}
        # Memoised DFS: returns the longest chain length ending at each node
        memo: Dict[str, int] = {}

        def chain_len(tid: str) -> int:
            if tid in memo:
                return memo[tid]
            task = id_map.get(tid)
            if not task or not task.dependencies:
                memo[tid] = 1
                return 1
            best = 1 + max(
                (chain_len(dep) for dep in task.dependencies if dep in id_map),
                default=0,
            )
            memo[tid] = best
            return best

        for t in tasks:
            chain_len(t.id)

        if not memo:
            return []

        # Walk back from the deepest node to reconstruct the path
        deepest = max(memo, key=memo.__getitem__)
        path: List[str] = []
        current = deepest
        while current:
            path.append(current)
            task = id_map.get(current)
            if not task or not task.dependencies:
                break
            current = max(
                (dep for dep in task.dependencies if dep in id_map),
                key=lambda d: memo.get(d, 0),
                default=None,  # type: ignore[arg-type]
            )
        return list(reversed(path))


# ---------------------------------------------------------------------------
# 3. Conflict Detector
# ---------------------------------------------------------------------------


class ConflictDetector:
    """Detects execution conflicts between tasks that would otherwise run concurrently."""

    def detect(self, tasks: List[ExecutionTask]) -> List[ConflictReport]:
        """Returns all detected conflicts between task pairs."""
        conflicts: List[ConflictReport] = []
        n = len(tasks)

        for i in range(n):
            for j in range(i + 1, n):
                a, b = tasks[i], tasks[j]
                conflict = self._check_pair(a, b)
                if conflict:
                    conflicts.append(conflict)

        return conflicts

    def _check_pair(self, a: ExecutionTask, b: ExecutionTask) -> Optional[ConflictReport]:
        """Checks two tasks for conflicts. Returns ConflictReport or None."""
        # Skip tasks that already have an explicit dependency ordering
        if b.id in a.dependencies or a.id in b.dependencies:
            return None

        # File collision: both tasks modify the same entities
        shared_entities = set(a.affected_entities) & set(b.affected_entities)
        if shared_entities and a.recommendation_id != b.recommendation_id:
            return ConflictReport(
                task_a_id=a.id,
                task_b_id=b.id,
                conflict_type="file_collision",
                description=(
                    f"Both tasks modify: {', '.join(sorted(shared_entities))}. "
                    "Concurrent modification may produce merge conflicts."
                ),
                resolution="serialize",
            )

        # Same-category concurrent modifications risk module ownership violations
        if (
            a.category == b.category
            and a.category in ("security", "architecture", "dependency")
            and a.recommendation_id != b.recommendation_id
            and not shared_entities  # Already reported above if entities overlap
        ):
            return ConflictReport(
                task_a_id=a.id,
                task_b_id=b.id,
                conflict_type="module_ownership",
                description=(
                    f"Both tasks make '{a.category}' changes concurrently. "
                    "Risk of overlapping scope or conflicting conventions."
                ),
                resolution="manual_review",
            )

        return None


# ---------------------------------------------------------------------------
# 4. Parallelization Planner
# ---------------------------------------------------------------------------


class ParallelizationPlanner:
    """Groups topologically-ordered tasks into parallel execution batches."""

    _BATCH_TITLES = {
        1: "Batch 1 — Security & Critical Fixes",
        2: "Batch 2 — Architecture & Structure",
        3: "Batch 3 — Performance & Complexity",
        4: "Batch 4 — Quality & Maintainability",
    }

    _CATEGORY_TO_BATCH = {
        "security": 1,
        "dependency": 1,
        "architecture": 2,
        "dead_code": 2,
        "performance": 3,
        "complexity": 3,
        "testing": 4,
        "documentation": 4,
        "general": 4,
    }

    def _effort_hours(self, tasks: List[ExecutionTask]) -> float:
        return sum(_EFFORT_HOURS.get(t.estimated_effort, 8.0) for t in tasks)

    def _hours_to_label(self, hours: float) -> str:
        for threshold, label in [
            (1.5, "< 2 hours"), (4.0, "Half day"), (8.0, "1 day"),
            (20.0, "2–3 days"), (40.0, "1 week"),
        ]:
            if hours <= threshold:
                return label
        return "Multi-week"

    def plan(self, tasks: List[ExecutionTask]) -> List[ExecutionBatch]:
        """Assigns tasks to ordered batches respecting dependency ordering."""
        id_map = {t.id: t for t in tasks}
        # Assign tasks to buckets
        buckets: Dict[int, List[ExecutionTask]] = defaultdict(list)

        for task in tasks:
            batch_num = self._CATEGORY_TO_BATCH.get(task.category, 4)
            # Tasks with dependencies in an earlier batch must go to that batch or later
            if task.dependencies:
                max_dep_batch = max(
                    (
                        self._CATEGORY_TO_BATCH.get(
                            id_map[dep].category if dep in id_map else "general", 4
                        )
                        for dep in task.dependencies
                        if dep in id_map
                    ),
                    default=0,
                )
                batch_num = max(batch_num, max_dep_batch)
            buckets[batch_num].append(task)

        batches: List[ExecutionBatch] = []
        for order, (num, bucket_tasks) in enumerate(sorted(buckets.items()), start=1):
            # Annotate parallel_with relationships within the same batch
            bucket_ids = [t.id for t in bucket_tasks]
            for task in bucket_tasks:
                task.parallel_with = [
                    tid for tid in bucket_ids
                    if tid != task.id and tid not in task.dependencies
                ]
            total_hours = self._effort_hours(bucket_tasks)
            batches.append(
                ExecutionBatch(
                    id=str(uuid.uuid4()),
                    order=order,
                    title=self._BATCH_TITLES.get(num, f"Batch {order}"),
                    tasks=bucket_tasks,
                    parallel=len(bucket_tasks) > 1,
                    estimated_total_effort=self._hours_to_label(total_hours),
                )
            )
        return batches


# ---------------------------------------------------------------------------
# 5. Risk Analyzer
# ---------------------------------------------------------------------------


class RiskAnalyzer:
    """Assigns deterministic risk levels to ExecutionTasks."""

    _CATEGORY_BASE_RISK = {
        "security": "high",
        "dependency": "medium",
        "architecture": "high",
        "dead_code": "low",
        "performance": "medium",
        "complexity": "medium",
        "documentation": "low",
        "testing": "low",
        "general": "medium",
    }

    _RISK_ESCALATION_THRESHOLDS = {
        "entities_high": 5,     # Many affected entities → escalate
        "dep_depth_high": 3,    # Deep dependency chain → escalate
    }

    def _escalate(self, base: str) -> str:
        levels = ["low", "medium", "high", "critical"]
        idx = levels.index(base) if base in levels else 1
        return levels[min(idx + 1, len(levels) - 1)]

    def _risk_rationale(self, task: ExecutionTask, risk: str, dep_depth: int) -> str:
        parts = [f"Category '{task.category}' baseline risk: {self._CATEGORY_BASE_RISK.get(task.category, 'medium')}."]
        if len(task.affected_entities) >= self._RISK_ESCALATION_THRESHOLDS["entities_high"]:
            parts.append(f"Affects {len(task.affected_entities)} entities (escalated).")
        if dep_depth >= self._RISK_ESCALATION_THRESHOLDS["dep_depth_high"]:
            parts.append(f"Dependency depth {dep_depth} (escalated).")
        return " ".join(parts)

    def analyze(
        self,
        tasks: List[ExecutionTask],
        dep_depths: Optional[Dict[str, int]] = None,
    ) -> List[ExecutionTask]:
        """Assigns risk levels to all tasks in place and returns them."""
        dep_depths = dep_depths or {}

        for task in tasks:
            base_risk = self._CATEGORY_BASE_RISK.get(task.category, "medium")
            risk = base_risk

            # Escalate for many affected entities
            if len(task.affected_entities) >= self._RISK_ESCALATION_THRESHOLDS["entities_high"]:
                risk = self._escalate(risk)

            # Escalate for deep dependency chains
            depth = dep_depths.get(task.id, len(task.dependencies))
            if depth >= self._RISK_ESCALATION_THRESHOLDS["dep_depth_high"]:
                risk = self._escalate(risk)

            task.risk = risk
            task.risk_rationale = self._risk_rationale(task, risk, depth)

        return tasks


# ---------------------------------------------------------------------------
# 6. Execution Planner Service
# ---------------------------------------------------------------------------


class ExecutionPlannerService:
    """Coordinates the full AEA² pipeline and manages plan persistence."""

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.base_dir = base_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "execution_plans",
        )
        self.decomposer = TaskDecomposer()
        self.resolver = DependencyResolver()
        self.conflict_detector = ConflictDetector()
        self.parallelization_planner = ParallelizationPlanner()
        self.risk_analyzer = RiskAnalyzer()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _repo_dir(self, repo_name: str) -> str:
        safe = repo_name.replace("/", "_").replace("\\", "_")
        path = os.path.join(self.base_dir, safe)
        os.makedirs(path, exist_ok=True)
        return path

    def _save(self, plan: ExecutionPlan) -> None:
        dir_path = self._repo_dir(plan.repository)
        ts_path = os.path.join(dir_path, f"{int(plan.generated_at)}.json")
        latest_path = os.path.join(dir_path, "latest.json")
        payload = plan.model_dump()
        for path in (ts_path, latest_path):
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2)
        logger.info("Saved ExecutionPlan for '%s' to %s", plan.repository, latest_path)

    def load_latest(self, repo_name: str) -> Optional[ExecutionPlan]:
        path = os.path.join(self._repo_dir(repo_name), "latest.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return ExecutionPlan.model_validate(json.load(fh))
        except Exception as exc:
            logger.error("Failed to load ExecutionPlan: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _compute_stats(
        self,
        tasks: List[ExecutionTask],
        batches: List[ExecutionBatch],
        conflicts: List[ConflictReport],
    ) -> Dict[str, Any]:
        by_risk: Dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        by_category: Dict[str, int] = {}
        for t in tasks:
            by_risk[t.risk] = by_risk.get(t.risk, 0) + 1
            by_category[t.category] = by_category.get(t.category, 0) + 1
        return {
            "total_tasks": len(tasks),
            "total_batches": len(batches),
            "total_conflicts": len(conflicts),
            "rollback_checkpoints": sum(1 for t in tasks if t.rollback_checkpoint),
            "by_risk": by_risk,
            "by_category": by_category,
        }

    # ------------------------------------------------------------------
    # Pipeline
    # ------------------------------------------------------------------

    def plan(
        self,
        repo_name: str,
        advisor_report: Dict[str, Any],
    ) -> ExecutionPlan:
        """Runs the full AEA² pipeline and returns a persisted ExecutionPlan."""
        generated_at = time.time()
        recommendations = advisor_report.get("recommendations", [])

        # Stage 1 — Decompose recommendations into tasks
        tasks = self.decomposer.decompose(recommendations)

        # Stage 2 — Resolve dependencies (topological sort, detect cycles)
        ordered_tasks = self.resolver.resolve(tasks)

        # Stage 3 — Compute critical path
        critical_path = self.resolver.compute_critical_path(ordered_tasks)

        # Stage 4 — Detect conflicts
        conflicts = self.conflict_detector.detect(ordered_tasks)

        # Serialise conflicting task pairs (add dependency to resolve ordering)
        conflict_pairs: Set[Tuple[str, str]] = {
            (c.task_a_id, c.task_b_id) for c in conflicts if c.resolution == "serialize"
        }
        id_map = {t.id: t for t in ordered_tasks}
        for a_id, b_id in conflict_pairs:
            if b_id in id_map and a_id not in id_map[b_id].dependencies:
                id_map[b_id].dependencies.append(a_id)

        # Stage 5 — Assign risk levels
        dep_depths: Dict[str, int] = {t.id: len(t.dependencies) for t in ordered_tasks}
        risk_scored = self.risk_analyzer.analyze(ordered_tasks, dep_depths)

        # Stage 6 — Parallelization and batching
        batches = self.parallelization_planner.plan(risk_scored)

        # Collect rollback points
        rollback_points = [t.id for t in risk_scored if t.rollback_checkpoint]

        # Build plan
        plan = ExecutionPlan(
            id=str(uuid.uuid4()),
            repository=repo_name,
            generated_at=generated_at,
            advisor_report_timestamp=advisor_report.get("generated_at"),
            batches=batches,
            critical_path=critical_path,
            rollback_points=rollback_points,
            conflicts=conflicts,
            statistics=self._compute_stats(risk_scored, batches, conflicts),
            metadata={
                "pipeline_stages": [
                    "TaskDecomposer",
                    "DependencyResolver",
                    "ConflictDetector",
                    "ParallelizationPlanner",
                    "RiskAnalyzer",
                ],
                "source_recommendations": len(recommendations),
            },
        )

        self._save(plan)
        return plan
