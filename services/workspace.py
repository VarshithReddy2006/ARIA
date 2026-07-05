"""Intelligent IDE Workspace — Service Layer.

Implements:
  WorkspaceCoordinator  — reads from all platform layers (graceful degradation)
  NavigationService     — resolves navigation requests against the Knowledge Graph
  PanelComposer         — builds panel-specific DTOs from raw platform data
  WorkspaceService      — public façade coordinating all workspace operations

No new analysis, reasoning, or repository intelligence is introduced here.
This is a pure presentation orchestration layer.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models.workspace import (
    AdvisorPanel,
    BatchSummary,
    ChatSessionMeta,
    ExecutionPanel,
    ExplorerNode,
    ExplorerPanel,
    FindingsPanel,
    FindingsSummary,
    HealthSummary,
    MonitorPanel,
    OverviewPanel,
    TimelineEntry,
    TimelinePanel,
    WorkspaceSnapshot,
    WorkspaceState,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1. Workspace Coordinator
#    Reads existing outputs from every platform layer. All reads are
#    non-fatal — missing data produces an empty/default panel.
# ---------------------------------------------------------------------------


class WorkspaceCoordinator:
    """Collects data from all platform layers for a given repository.

    Accepts optional platform service references so the coordinator can be
    constructed independently of the FastAPI dependency graph (useful in tests).
    """

    def __init__(
        self,
        twin_builder=None,
        knowledge_graph_builder=None,
        repository_inspector=None,
        engineering_memory_service=None,
        continuous_monitoring_service=None,
        advisor_service=None,
        execution_planner_service=None,
    ) -> None:
        self._twin = twin_builder
        self._kg = knowledge_graph_builder
        self._inspector = repository_inspector
        self._memory = engineering_memory_service
        self._monitoring = continuous_monitoring_service
        self._advisor = advisor_service
        self._execution = execution_planner_service

    # ------------------------------------------------------------------
    # Internal safe-read helpers
    # ------------------------------------------------------------------

    def _safe(self, fn, *args, default=None, **kwargs):
        """Calls fn(*args, **kwargs) and returns default on any exception."""
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            logger.debug("WorkspaceCoordinator safe-read failed: %s", exc)
            return default

    # ------------------------------------------------------------------
    # Public data accessors
    # ------------------------------------------------------------------

    def get_twin(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._twin:
            return None
        result = self._safe(self._twin.build_twin, repo_name)
        return result.model_dump() if result and hasattr(result, "model_dump") else result

    def get_knowledge_graph(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._kg:
            return None
        result = self._safe(self._kg.build_graph, repo_name)
        return result.model_dump() if result and hasattr(result, "model_dump") else result

    def get_inspection_report(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._inspector:
            return None
        result = self._safe(self._inspector.load_latest, repo_name)
        return result.model_dump() if result and hasattr(result, "model_dump") else result

    def get_memory_context(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._memory:
            return None
        try:
            from services.memory_service import RecentHistoryPolicy
            ctx = self._safe(
                self._memory.navigator.get_memory_context,
                repo_name,
                RecentHistoryPolicy(limit=10),
            )
            return ctx.model_dump() if ctx and hasattr(ctx, "model_dump") else ctx
        except Exception:
            return None

    def get_monitoring_status(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._monitoring:
            return None
        result = self._safe(self._monitoring.get_status, repo_name)
        return result.model_dump() if result and hasattr(result, "model_dump") else result

    def get_monitoring_history(self, repo_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self._monitoring:
            return []
        runs = self._safe(self._monitoring.get_history, repo_name, default=[])
        items = runs or []
        return [
            r.model_dump() if hasattr(r, "model_dump") else r
            for r in items[-limit:]
        ]

    def get_advisor_report(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._advisor:
            return None
        result = self._safe(self._advisor.load_latest, repo_name)
        return result.model_dump() if result and hasattr(result, "model_dump") else result

    def get_execution_plan(self, repo_name: str) -> Optional[Dict[str, Any]]:
        if not self._execution:
            return None
        result = self._safe(self._execution.load_latest, repo_name)
        return result.model_dump() if result and hasattr(result, "model_dump") else result


# ---------------------------------------------------------------------------
# 2. Navigation Service
#    Resolves navigation requests (file, symbol, dependency) against the
#    Knowledge Graph without duplicating traversal logic.
# ---------------------------------------------------------------------------


class NavigationService:
    """Handles navigation requests within the IDE workspace."""

    def __init__(self, coordinator: WorkspaceCoordinator) -> None:
        self._coordinator = coordinator

    def navigate_to_file(self, repo_name: str, file_path: str) -> Dict[str, Any]:
        """Returns Knowledge Graph context for a specific file."""
        kg = self._coordinator.get_knowledge_graph(repo_name)
        if not kg:
            return {"file": file_path, "nodes": [], "edges": []}
        nodes = [
            n for n in kg.get("nodes", [])
            if file_path in (n.get("file_path", "") or "")
        ]
        return {"file": file_path, "nodes": nodes, "edge_count": len(kg.get("edges", []))}

    def navigate_to_symbol(self, repo_name: str, symbol: str) -> Dict[str, Any]:
        """Returns Knowledge Graph context for a specific symbol."""
        kg = self._coordinator.get_knowledge_graph(repo_name)
        if not kg:
            return {"symbol": symbol, "nodes": [], "references": []}
        nodes = [
            n for n in kg.get("nodes", [])
            if symbol.lower() in (n.get("label", "") or "").lower()
        ]
        return {"symbol": symbol, "nodes": nodes}

    def get_call_hierarchy(self, repo_name: str, symbol: str) -> Dict[str, Any]:
        """Returns callers and callees for a symbol from the Knowledge Graph."""
        kg = self._coordinator.get_knowledge_graph(repo_name)
        if not kg:
            return {"symbol": symbol, "callers": [], "callees": []}
        edges = kg.get("edges", [])
        callers = [e["source"] for e in edges if e.get("target") == symbol and e.get("kind") == "calls"]
        callees = [e["target"] for e in edges if e.get("source") == symbol and e.get("kind") == "calls"]
        return {"symbol": symbol, "callers": callers, "callees": callees}


# ---------------------------------------------------------------------------
# 3. Panel Composer
#    Builds panel-specific DTOs from raw platform data dictionaries.
#    Pure transformation — no analysis, no I/O.
# ---------------------------------------------------------------------------


class PanelComposer:
    """Transforms raw platform data into presentation-ready panel DTOs."""

    # ------------------------------------------------------------------
    # Overview panel
    # ------------------------------------------------------------------

    def compose_overview(self, repo_name: str, twin: Optional[Dict], inspection: Optional[Dict]) -> OverviewPanel:
        health = HealthSummary()

        if inspection:
            stats = inspection.get("statistics", {})
            health.critical_count = int(stats.get("critical", 0))
            health.high_count = int(stats.get("high", 0))
            health.medium_count = int(stats.get("medium", 0))
            health.low_count = int(stats.get("low", 0))
            health.overall_score = inspection.get("overall_score")

        if not twin:
            return OverviewPanel(repository=repo_name, health=health)

        metadata = twin.get("metadata", {})
        languages = twin.get("languages", [])
        if isinstance(languages, dict):
            langs = list(languages.keys())
            primary = max(languages, key=languages.get) if languages else None
        else:
            langs = list(languages) if languages else []
            primary = langs[0] if langs else None

        return OverviewPanel(
            repository=repo_name,
            description=metadata.get("description"),
            primary_language=primary,
            languages=langs,
            total_files=twin.get("file_count", 0),
            total_symbols=twin.get("symbol_count", 0),
            architecture_style=twin.get("architecture_style"),
            dependency_count=twin.get("dependency_count", 0),
            health=health,
            last_indexed_at=twin.get("indexed_at"),
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Explorer panel
    # ------------------------------------------------------------------

    def compose_explorer(self, repo_name: str, kg: Optional[Dict]) -> ExplorerPanel:
        if not kg:
            return ExplorerPanel(repository=repo_name)

        nodes_raw = kg.get("nodes", [])
        edges_raw = kg.get("edges", [])

        # Build top-level nodes (those with no incoming "contains" edges)
        child_ids = {e.get("target") for e in edges_raw if e.get("kind") == "contains"}
        root_raw = [n for n in nodes_raw if n.get("id") not in child_ids][:20]

        root_nodes = [
            ExplorerNode(
                id=n.get("id", ""),
                label=n.get("label", ""),
                kind=n.get("kind", "module"),
                metadata={k: v for k, v in n.items() if k not in ("id", "label", "kind")},
            )
            for n in root_raw
        ]

        # Dependency count by type
        dep_summary: Dict[str, int] = {}
        for e in edges_raw:
            kind = e.get("kind", "unknown")
            dep_summary[kind] = dep_summary.get(kind, 0) + 1

        return ExplorerPanel(
            repository=repo_name,
            total_nodes=len(nodes_raw),
            total_edges=len(edges_raw),
            root_nodes=root_nodes,
            dependency_summary=dep_summary,
        )

    # ------------------------------------------------------------------
    # Chat panel
    # ------------------------------------------------------------------

    def compose_chat(self, repo_name: str, kg: Optional[Dict]) -> ChatSessionMeta:
        node_count = len(kg.get("nodes", [])) if kg else 0
        return ChatSessionMeta(
            repository=repo_name,
            grounding_available=node_count > 0,
            context_nodes=node_count,
            suggested_questions=[
                "What are the main modules in this repository?",
                "Which files have the most dependencies?",
                "What are the current security findings?",
                "Summarize the architecture of this repository.",
                "What changed in the last engineering memory snapshot?",
            ],
        )

    # ------------------------------------------------------------------
    # Findings panel
    # ------------------------------------------------------------------

    def compose_findings(self, repo_name: str, inspection: Optional[Dict]) -> FindingsPanel:
        if not inspection:
            return FindingsPanel(repository=repo_name)

        raw_findings = inspection.get("findings", [])
        by_severity: Dict[str, int] = {}
        by_category: Dict[str, int] = {}
        summaries: List[FindingsSummary] = []

        for f in raw_findings:
            sev = f.get("severity", "low")
            cat = f.get("category", "general")
            by_severity[sev] = by_severity.get(sev, 0) + 1
            by_category[cat] = by_category.get(cat, 0) + 1
            summaries.append(FindingsSummary(
                id=f.get("id", ""),
                title=f.get("title", ""),
                category=cat,
                severity=sev,
                confidence=float(f.get("confidence", 0.8)),
                affected_entities=list(f.get("affected_entities", [])),
                recommendation_count=len(f.get("recommendations", [])),
            ))

        return FindingsPanel(
            repository=repo_name,
            total_findings=len(summaries),
            findings=summaries,
            by_severity=by_severity,
            by_category=by_category,
            last_inspected_at=inspection.get("generated_at"),
        )

    # ------------------------------------------------------------------
    # Timeline panel
    # ------------------------------------------------------------------

    def compose_timeline(self, repo_name: str, memory: Optional[Dict]) -> TimelinePanel:
        if not memory:
            return TimelinePanel(repository=repo_name)

        snapshots = memory.get("snapshots", [])
        entries = [
            TimelineEntry(
                snapshot_id=s.get("id", ""),
                timestamp=float(s.get("timestamp", 0)),
                commit_hash=s.get("commit_hash"),
                summary=s.get("summary", ""),
                metrics=s.get("metrics", {}),
            )
            for s in snapshots
        ]

        return TimelinePanel(
            repository=repo_name,
            snapshot_count=len(entries),
            timeline=entries,
            trends=memory.get("trends", {}),
        )

    # ------------------------------------------------------------------
    # Monitor panel
    # ------------------------------------------------------------------

    def compose_monitor(
        self,
        repo_name: str,
        status: Optional[Dict],
        history: List[Dict],
    ) -> MonitorPanel:
        if not status and not history:
            return MonitorPanel(repository=repo_name)

        # Extract alerts: any run with critical or high findings
        alerts = []
        for run in history:
            counts = run.get("finding_counts", {})
            if counts.get("critical", 0) > 0 or counts.get("high", 0) > 0:
                alerts.append({
                    "run_id": run.get("id"),
                    "trigger": run.get("trigger"),
                    "critical": counts.get("critical", 0),
                    "high": counts.get("high", 0),
                })

        return MonitorPanel(
            repository=repo_name,
            status=status.get("status", "unknown") if status else "unknown",
            last_run_at=status.get("last_run_at") if status else None,
            last_trigger=status.get("last_trigger") if status else None,
            run_count=status.get("run_count", len(history)) if status else len(history),
            health_trend=status.get("health_trend") if status else None,
            overall_health_score=status.get("overall_health_score") if status else None,
            recent_runs=history,
            alerts=alerts,
        )

    # ------------------------------------------------------------------
    # Advisor panel
    # ------------------------------------------------------------------

    def compose_advisor(self, repo_name: str, advisor_report: Optional[Dict]) -> AdvisorPanel:
        if not advisor_report:
            return AdvisorPanel(repository=repo_name)

        recs = advisor_report.get("recommendations", [])
        top_recs = [
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "priority": r.get("priority"),
                "category": r.get("category"),
                "estimated_effort": r.get("estimated_effort"),
            }
            for r in recs[:10]
        ]

        roadmap = advisor_report.get("roadmap", [])
        roadmap_summary = [
            {
                "phase": p.get("phase"),
                "title": p.get("title"),
                "recommendation_count": len(p.get("recommendations", [])),
                "estimated_effort": p.get("estimated_total_effort"),
            }
            for p in roadmap
        ]

        return AdvisorPanel(
            repository=repo_name,
            overall_priority=advisor_report.get("overall_priority", "low"),
            total_recommendations=len(recs),
            top_recommendations=top_recs,
            roadmap_phases=len(roadmap),
            roadmap_summary=roadmap_summary,
        )

    # ------------------------------------------------------------------
    # Execution panel
    # ------------------------------------------------------------------

    def compose_execution(self, repo_name: str, plan: Optional[Dict]) -> ExecutionPanel:
        if not plan:
            return ExecutionPanel(repository=repo_name)

        batches_raw = plan.get("batches", [])
        batch_summaries = [
            BatchSummary(
                batch_id=b.get("id", ""),
                order=b.get("order", 0),
                title=b.get("title", ""),
                task_count=len(b.get("tasks", [])),
                parallel=b.get("parallel", False),
                estimated_effort=b.get("estimated_total_effort", "unknown"),
            )
            for b in batches_raw
        ]

        stats = plan.get("statistics", {})
        risk_counts = stats.get("by_risk", {})
        overall_risk = "low"
        for level in ("critical", "high", "medium"):
            if risk_counts.get(level, 0) > 0:
                overall_risk = level
                break

        return ExecutionPanel(
            repository=repo_name,
            total_tasks=stats.get("total_tasks", 0),
            total_batches=stats.get("total_batches", 0),
            critical_path_length=len(plan.get("critical_path", [])),
            rollback_checkpoints=stats.get("rollback_checkpoints", 0),
            conflict_count=stats.get("total_conflicts", 0),
            overall_risk=overall_risk,
            batches=batch_summaries,
            critical_path=plan.get("critical_path", []),
        )


# ---------------------------------------------------------------------------
# 4. Workspace Service
#    Public façade that wires coordinator + composer together.
# ---------------------------------------------------------------------------


class WorkspaceService:
    """Coordinates workspace state and panel composition for the IDE."""

    def __init__(self, coordinator: WorkspaceCoordinator) -> None:
        self.coordinator = coordinator
        self.navigator = NavigationService(coordinator)
        self.composer = PanelComposer()

    def _default_state(self, repo_name: str) -> WorkspaceState:
        return WorkspaceState(repository=repo_name)

    # ------------------------------------------------------------------
    # Individual panel builders
    # ------------------------------------------------------------------

    def get_overview(self, repo_name: str) -> OverviewPanel:
        twin = self.coordinator.get_twin(repo_name)
        inspection = self.coordinator.get_inspection_report(repo_name)
        return self.composer.compose_overview(repo_name, twin, inspection)

    def get_explorer(self, repo_name: str) -> ExplorerPanel:
        kg = self.coordinator.get_knowledge_graph(repo_name)
        return self.composer.compose_explorer(repo_name, kg)

    def get_chat(self, repo_name: str) -> ChatSessionMeta:
        kg = self.coordinator.get_knowledge_graph(repo_name)
        return self.composer.compose_chat(repo_name, kg)

    def get_findings(self, repo_name: str) -> FindingsPanel:
        inspection = self.coordinator.get_inspection_report(repo_name)
        return self.composer.compose_findings(repo_name, inspection)

    def get_timeline(self, repo_name: str) -> TimelinePanel:
        memory = self.coordinator.get_memory_context(repo_name)
        return self.composer.compose_timeline(repo_name, memory)

    def get_monitor(self, repo_name: str) -> MonitorPanel:
        status = self.coordinator.get_monitoring_status(repo_name)
        history = self.coordinator.get_monitoring_history(repo_name)
        return self.composer.compose_monitor(repo_name, status, history)

    def get_advisor(self, repo_name: str) -> AdvisorPanel:
        report = self.coordinator.get_advisor_report(repo_name)
        return self.composer.compose_advisor(repo_name, report)

    def get_execution(self, repo_name: str) -> ExecutionPanel:
        plan = self.coordinator.get_execution_plan(repo_name)
        return self.composer.compose_execution(repo_name, plan)

    # ------------------------------------------------------------------
    # Full workspace snapshot
    # ------------------------------------------------------------------

    def get_workspace(self, repo_name: str, state: Optional[WorkspaceState] = None) -> WorkspaceSnapshot:
        """Returns the complete workspace snapshot for a repository."""
        if state is None:
            state = self._default_state(repo_name)

        # Collect all panels (each is non-fatal)
        overview = self.get_overview(repo_name)
        explorer = self.get_explorer(repo_name)
        chat = self.get_chat(repo_name)
        findings = self.get_findings(repo_name)
        timeline = self.get_timeline(repo_name)
        monitor = self.get_monitor(repo_name)
        advisor = self.get_advisor(repo_name)
        execution = self.get_execution(repo_name)

        # Determine which panels have real data
        available = ["overview", "explorer", "chat"]
        if findings.total_findings > 0:
            available.append("findings")
        if timeline.snapshot_count > 0:
            available.append("timeline")
        if monitor.status != "unknown":
            available.append("monitor")
        if advisor.total_recommendations > 0:
            available.append("advisor")
        if execution.total_tasks > 0:
            available.append("execution")

        return WorkspaceSnapshot(
            state=state,
            overview=overview,
            explorer=explorer,
            chat=chat,
            findings=findings,
            timeline=timeline,
            monitor=monitor,
            advisor=advisor,
            execution=execution,
            available_panels=available,
        )
