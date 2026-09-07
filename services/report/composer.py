"""Report Composer Service.

Aggregates raw analysis metrics from multiple services, calculates
the Repository Health Score, and returns the unified ReportDataModel.
"""

import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import networkx as nx

from models.report import (
    ReportDataModel,
    ReportMetadata,
    ScoreBreakdown,
    ArchReportSection,
    ApiReportSection,
    HygieneReportSection,
    OnboardingReportSection,
    RuleViolationItem,
    WhyThisScoreItem,
    SignalAttentionItem,
)
from services.architecture.rules import evaluate_rules
from storage.migrations import get_db_connection


def _normalize_repo_path(path: str) -> str:
    """Strip absolute prefixes, Windows drive letters, workspace prefixes, and internal data directories."""
    if not path:
        return ""
    p = path.replace("\\", "/").strip()
    if ":" in p:
        p = p.split(":", 1)[1].lstrip("/")

    # Handle data/cloned_repos/owner/repo/subpath or cloned_repos/owner/repo/subpath
    for prefix in ("data/cloned_repos/", "cloned_repos/"):
        if p.startswith(prefix):
            remainder = p[len(prefix) :]
            parts = remainder.split("/", 2)
            if len(parts) >= 3:
                p = parts[2]
            elif len(parts) == 2:
                p = parts[1]

    # Handle standard workspace or repo directory markers in absolute paths
    for marker in ("Repo-Intelligence-Agent/", "workspace/", "/repo/"):
        if marker in p:
            p = p.split(marker, 1)[1]

    # Handle standard test/venv/data prefixes
    for prefix in ("data/", "testenv/", "env/", "venv/", ".venv/"):
        if p.startswith(prefix):
            parts = p[len(prefix) :].split("/", 1)
            if len(parts) > 1:
                p = parts[1]

    return p.lstrip("/")


normalize_repo_path = _normalize_repo_path


def _get_reports_dir() -> str:
    import os
    from core.config import settings

    analysis_path = getattr(settings, "analysis_store_path", None) or os.environ.get(
        "ANALYSIS_STORE_PATH"
    )
    if analysis_path:
        base = os.path.dirname(os.path.abspath(analysis_path))
    else:
        base = "data"
    reports_dir = os.path.join(base, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir


def save_report_artifact(report: ReportDataModel) -> None:
    """Persists report JSON artifact to shared reports directory."""
    import logging
    import os
    from core.concurrency import write_json_atomic

    try:
        reports_dir = _get_reports_dir()
        safe_name = report.metadata.repo_name.replace("/", "_").replace("\\", "_")
        report_file = os.path.join(reports_dir, f"{safe_name}.json")
        data = report.model_dump(mode="json")
        write_json_atomic(report_file, data, indent=2)
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Failed to save report JSON artifact: %s", exc
        )


class ReportComposer:
    """Calculates and aggregates codebase analysis data into a ReportDataModel."""

    _normalize_repo_path = staticmethod(_normalize_repo_path)

    def __init__(
        self,
        store: Optional[Dict[str, Any]] = None,
        symbol_service: Optional[Any] = None,
        call_graph_service: Optional[Any] = None,
        dead_code_service: Optional[Any] = None,
        git_history_service: Optional[Any] = None,
        graph_service: Optional[Any] = None,
    ) -> None:
        self.store = store if store is not None else {}
        self.symbol_service = symbol_service
        self.call_graph_service = call_graph_service
        self.dead_code_service = dead_code_service
        self.git_history_service = git_history_service
        self.graph_service = graph_service

    def compose_report(self, repo_name: str) -> ReportDataModel:
        """Assembles unified metrics, calculates scores, and returns ReportDataModel."""
        start_time = time.time()

        # 1. Fetch analysis metadata from ANALYSIS_STORE
        if repo_name not in self.store:
            raise ValueError(
                f"Repository '{repo_name}' is not indexed. Analyze it first."
            )

        entry = self.store[repo_name]
        analysis_data = entry["analysis"]
        architecture_data = entry["architecture"]

        owner, name = repo_name.split("/", 1)

        # Extract loc, commits, etc. from metadata
        metadata_dict = getattr(analysis_data, "metadata", {}) or {}
        total_loc = int(metadata_dict.get("loc", 0))
        commits_count = int(metadata_dict.get("commits_count", 0))
        languages_dict = getattr(analysis_data, "tech_stack", []) or []

        # Fetch other components
        symbol_index = (
            self.symbol_service.load(repo_name) if self.symbol_service else None
        )
        dead_code_result = (
            self.dead_code_service.analyze(repo_name)
            if self.dead_code_service
            else None
        )
        churn_summary = (
            self.git_history_service.load(repo_name)
            if self.git_history_service
            else None
        )
        file_graph = (
            self.graph_service.load_graph(repo_name) if self.graph_service else None
        )

        # 2. Gather Architecture Metrics & ArchUnit Rules
        cycles: List[List[str]] = []
        strongly_connected_components = 0
        rule_violations: List[RuleViolationItem] = []
        smells: List[str] = []

        if file_graph is not None and file_graph.number_of_nodes() > 0:
            non_trivial_sccs = [
                c for c in nx.strongly_connected_components(file_graph) if len(c) > 1
            ]
            strongly_connected_components = len(non_trivial_sccs)
            # Find simple cycles (bounded to prevent combinatorial explosion on dense graphs)
            try:
                import itertools

                raw_cycles = list(itertools.islice(nx.simple_cycles(file_graph), 25))
                for rc in raw_cycles:
                    cycles.append([_normalize_repo_path(node) for node in rc])
            except Exception:
                pass

            # Evaluate layer boundary rules across all edges
            try:
                raw_edges = [
                    {
                        "source": _normalize_repo_path(u),
                        "target": _normalize_repo_path(v),
                    }
                    for u, v in file_graph.edges()
                ]
                rules_eval = evaluate_rules(raw_edges)
                for v in rules_eval.get("violations", []):
                    rule_violations.append(
                        RuleViolationItem(
                            rule_id=v.get("rule_id", "ARCH-RULE"),
                            rule_name=v.get("rule_name", "Architecture Violation"),
                            severity=v.get("severity", "MAJOR"),
                            source_node=_normalize_repo_path(v.get("source_node", "")),
                            target_node=_normalize_repo_path(v.get("target_node", "")),
                            description=v.get("description", ""),
                        )
                    )
            except Exception:
                pass

        cycles_count = len(cycles)
        for cycle in cycles:
            smells.append(f"Circular dependency cycle: {' -> '.join(cycle)}")
        for rv in rule_violations:
            smells.append(f"[{rv.rule_id}] {rv.rule_name}: {rv.description}")

        # 3. Gather API Metrics & Martin's Instability Calculation
        total_exported_symbols = 0
        public_symbols = 0
        private_symbols = 0
        if symbol_index is not None:
            total_exported_symbols = symbol_index.symbol_count
            for sym in getattr(symbol_index, "symbols", []):
                is_public = not getattr(sym, "name", "").startswith("_")
                if is_public:
                    public_symbols += 1
                else:
                    private_symbols += 1

        pub_priv_ratio = public_symbols / max(1, private_symbols)

        # Martin's instability metrics (dynamic computation from dependency graph)
        avg_dist = 0.0
        unstable_modules_count = 0
        if file_graph is not None and file_graph.number_of_nodes() > 0:
            distances = []
            for node in file_graph.nodes():
                ca = file_graph.in_degree(node)
                ce = file_graph.out_degree(node)
                if ca + ce > 0:
                    instability = ce / float(ca + ce)
                    # Abstractness heuristic based on interface / model / schema naming
                    node_lower = node.lower()
                    is_abstract = any(
                        term in node_lower
                        for term in (
                            "model",
                            "types",
                            "interface",
                            "schema",
                            "base",
                            "protocol",
                            "abc",
                        )
                    )
                    abstractness = 0.8 if is_abstract else 0.1
                    # Distance from Main Sequence D = |A + I - 1|
                    d_val = abs(abstractness + instability - 1.0)
                    distances.append(d_val)
                    if instability > 0.8 and ce >= 3:
                        unstable_modules_count += 1
            if distances:
                avg_dist = round(sum(distances) / len(distances), 2)
            else:
                avg_dist = 0.15
        else:
            avg_dist = 0.15

        # 4. Gather Hygiene Metrics
        dead_functions_count = 0
        dead_functions: List[str] = []
        dead_code_ratio = 0.0
        if dead_code_result is not None:
            dead_functions = [
                _normalize_repo_path(f.file_path)
                for f in getattr(dead_code_result, "unused_files", [])
            ]
            dead_functions_count = len(dead_functions)
            if symbol_index and symbol_index.symbol_count > 0:
                dead_code_ratio = dead_functions_count / float(
                    symbol_index.symbol_count
                )

        # 5. Gather Onboarding Metrics
        raw_reading_path = getattr(architecture_data, "reading_order", []) or []
        recommended_reading_path = [_normalize_repo_path(p) for p in raw_reading_path]
        core_entry_points: List[str] = []
        if hasattr(architecture_data, "entry_points") and getattr(
            architecture_data, "entry_points"
        ):
            core_entry_points = [
                _normalize_repo_path(p)
                for p in getattr(architecture_data, "entry_points")
            ]
        elif file_graph is not None and file_graph.number_of_nodes() > 0:
            core_entry_points = [
                _normalize_repo_path(n) for n, d in file_graph.in_degree() if d == 0
            ][:8]

        reading_path_completeness = 1.0
        if recommended_reading_path:
            reading_path_completeness = min(1.0, len(recommended_reading_path) / 5.0)

        # 6. Calculate Deterministic Health Scores
        # Formula 1: S_arch
        s_arch = round(
            100.0
            * math.exp(
                -0.1
                * (
                    cycles_count
                    + 3.0 * strongly_connected_components
                    + 0.5 * len(rule_violations)
                )
            ),
            1,
        )
        s_arch = max(0.0, min(100.0, s_arch))

        # Formula 2: S_api
        s_api = round(100.0 * (1.0 - min(1.0, avg_dist)), 1)
        s_api = max(0.0, min(100.0, s_api))

        # Formula 3: S_hygiene
        s_hygiene = round(
            100.0 * (1.0 - min(1.0, dead_code_ratio)) * math.exp(-0.03 * len(smells)), 1
        )
        s_hygiene = max(0.0, min(100.0, s_hygiene))

        # Formula 4: S_churn
        hotspots_count = (
            len(churn_summary.hotspots)
            if churn_summary and hasattr(churn_summary, "hotspots")
            else 0
        )
        total_files_count = (
            len(churn_summary.file_records)
            if churn_summary and hasattr(churn_summary, "file_records")
            else 1
        )
        s_churn = round(
            100.0 * math.exp(-5.0 * (hotspots_count / max(1, total_files_count))), 1
        )
        s_churn = max(0.0, min(100.0, s_churn))

        # Formula 5: S_read
        s_read = round(100.0 * reading_path_completeness, 1)
        s_read = max(0.0, min(100.0, s_read))

        # Weighted Overall Score
        w_arch = 0.25
        w_api = 0.20
        w_hygiene = 0.20
        w_churn = 0.20
        w_read = 0.15

        overall_score = round(
            w_arch * s_arch
            + w_api * s_api
            + w_hygiene * s_hygiene
            + w_churn * s_churn
            + w_read * s_read,
            1,
        )

        if overall_score >= 90:
            grade = "A"
        elif overall_score >= 80:
            grade = "B"
        elif overall_score >= 70:
            grade = "C"
        elif overall_score >= 60:
            grade = "D"
        else:
            grade = "F"

        scores = ScoreBreakdown(
            overall=overall_score,
            architecture=s_arch,
            api=s_api,
            hygiene=s_hygiene,
            churn=s_churn,
            readability=s_read,
            grade=grade,
        )

        # 7. Refactoring priorities (Ordered by severity: Critical Rules -> Cycles -> Major Rules -> Hotspots -> Dead Code)
        refactoring_priorities = []
        for rv in rule_violations:
            if rv.severity == "CRITICAL":
                refactoring_priorities.append(
                    f"Fix critical layer boundary violation [{rv.rule_id}]: '{rv.source_node}' -> '{rv.target_node}' ({rv.description})"
                )

        for cycle in cycles[:5]:
            refactoring_priorities.append(
                f"Break circular dependency loop: {' -> '.join(cycle[:3])}{' -> ...' if len(cycle) > 3 else ''} ({len(cycle)} participating modules)"
            )

        for rv in rule_violations:
            if rv.severity == "MAJOR":
                refactoring_priorities.append(
                    f"Remediate layer boundary violation [{rv.rule_id}]: '{rv.source_node}' -> '{rv.target_node}'"
                )

        if churn_summary and hasattr(churn_summary, "hotspots"):
            for h in churn_summary.hotspots[:5]:
                norm_h_path = _normalize_repo_path(getattr(h, "file_path", ""))
                refactoring_priorities.append(
                    f"Refactor volatile hotspot module: {norm_h_path} (churn score: {getattr(h, 'churn_score', 0)})"
                )

        if dead_code_result and hasattr(dead_code_result, "unused_files"):
            for f in dead_code_result.unused_files[:3]:
                norm_f_path = _normalize_repo_path(getattr(f, "file_path", ""))
                refactoring_priorities.append(
                    f"Remove dead code file: {norm_f_path} ({getattr(f, 'recommendation', 'unused')})"
                )

        if not refactoring_priorities:
            refactoring_priorities.append(
                "No critical refactoring priorities found — architecture and hygiene baseline are optimal."
            )

        # 8. Structured "WHY THIS SCORE" Evidence Section
        why_this_score: List[WhyThisScoreItem] = []

        # Dimension 1: Architecture
        if s_arch < 80.0:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Architecture Stability",
                    score=s_arch,
                    status="attention",
                    evidence=f"{cycles_count} circular dependency cycles and {len(rule_violations)} layer rule violations detected.",
                    impact="Coupling locks and circular dependencies risk build deadlock and cascade failures.",
                    recommendation="Break cycles using dependency inversion and isolate layer boundaries.",
                )
            )
        else:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Architecture Stability",
                    score=s_arch,
                    status="healthy",
                    evidence=f"Clean acyclic graph structure with {strongly_connected_components} non-trivial SCC clusters.",
                    impact="Modular boundaries allow independent testing, fast builds, and safe refactoring.",
                    recommendation="Maintain decoupled module interfaces.",
                )
            )

        # Dimension 2: API Surface
        if (
            s_api < 80.0
            or avg_dist > 0.3
            or pub_priv_ratio < 0.1
            or pub_priv_ratio > 0.6
        ):
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="API Encapsulation",
                    score=s_api,
                    status="review",
                    evidence=f"Average distance from main sequence is {avg_dist:.2f} with public/private ratio {pub_priv_ratio:.2f}.",
                    impact="Over-exposed or unstable interfaces increase API contract fragility.",
                    recommendation="Encapsulate internal utilities and expose explicit public interface gateways.",
                )
            )
        else:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="API Encapsulation",
                    score=s_api,
                    status="healthy",
                    evidence=f"Balanced API stability along main sequence (D = {avg_dist:.2f}, {total_exported_symbols:,} symbols).",
                    impact="Clean public contracts protect against breaking downstream changes.",
                    recommendation="Continue following interface segregation.",
                )
            )

        # Dimension 3: Code Hygiene
        if s_hygiene < 80.0 or dead_functions_count > 5:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Code Hygiene & Pruning",
                    score=s_hygiene,
                    status="attention",
                    evidence=f"{dead_functions_count} orphan candidates ({dead_code_ratio * 100:.1f}% dead code ratio) and {len(smells)} design smells.",
                    impact="Unused code increases cognitive overhead and maintenance burden.",
                    recommendation="Prune unreachable functions and remove obsolete modules.",
                )
            )
        else:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Code Hygiene & Pruning",
                    score=s_hygiene,
                    status="healthy",
                    evidence="Zero significant dead code candidates detected in call graph sweeps.",
                    impact="Lean AST keeps codebase maintainable and fast to navigate.",
                    recommendation="Keep running continuous dead code pruning.",
                )
            )

        # Dimension 4: Hotspots & Churn
        if s_churn < 80.0 or hotspots_count > 0:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Hotspot & Churn Control",
                    score=s_churn,
                    status="review",
                    evidence=f"{hotspots_count} high-churn hotspots across {total_files_count} files.",
                    impact="Frequently modified files have higher defect density and review overhead.",
                    recommendation="Decompose high-churn files into single-responsibility units.",
                )
            )
        else:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Hotspot & Churn Control",
                    score=s_churn,
                    status="healthy",
                    evidence="Zero volatile hotspots detected in recent git history.",
                    impact="Evenly distributed modifications indicate stable component responsibilities.",
                    recommendation="Continue modular feature development.",
                )
            )

        # Dimension 5: Onboarding
        if s_read < 80.0:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Onboarding Clarity",
                    score=s_read,
                    status="review",
                    evidence=f"Reading path completeness is at {reading_path_completeness * 100:.0f}%.",
                    impact="Incomplete reading paths slow down new contributor onboarding.",
                    recommendation="Supplement entry points and logical reading order annotations.",
                )
            )
        else:
            why_this_score.append(
                WhyThisScoreItem(
                    dimension="Onboarding Clarity",
                    score=s_read,
                    status="healthy",
                    evidence=f"Complete topological reading path covering {len(recommended_reading_path)} core steps with {len(core_entry_points)} entry points.",
                    impact="Accelerates developer ramp-up and architecture understanding.",
                    recommendation="Keep documentation aligned with entry points.",
                )
            )

        # 9. Structured "SIGNALS NEEDING ATTENTION"
        signals_needing_attention: List[SignalAttentionItem] = []
        sig_idx = 1

        if cycles_count > 0:
            signals_needing_attention.append(
                SignalAttentionItem(
                    id=f"sig-{sig_idx}",
                    severity="HIGH",
                    title="Circular dependency structure",
                    evidence=f"{cycles_count} verified cycle{'s' if cycles_count > 1 else ''}",
                    meaning="Circular imports create tight module coupling and risk runtime import order locks.",
                    action_label="View in Graph",
                    action_target="graph",
                    affected_file=cycles[0][0] if cycles and cycles[0] else None,
                )
            )
            sig_idx += 1

        if rule_violations:
            has_crit = any(v.severity == "CRITICAL" for v in rule_violations)
            signals_needing_attention.append(
                SignalAttentionItem(
                    id=f"sig-{sig_idx}",
                    severity="CRITICAL" if has_crit else "HIGH",
                    title="Architecture layer boundary violations",
                    evidence=f"{len(rule_violations)} layer rule violation{'s' if len(rule_violations) > 1 else ''}",
                    meaning="Cross-layer violations bypass application pipelines (e.g. Domain -> Infrastructure).",
                    action_label="Inspect Violations",
                    action_target="architecture",
                    affected_file=rule_violations[0].source_node
                    if rule_violations
                    else None,
                )
            )
            sig_idx += 1

        if dead_functions_count > 0:
            signals_needing_attention.append(
                SignalAttentionItem(
                    id=f"sig-{sig_idx}",
                    severity="MEDIUM" if dead_functions_count > 5 else "LOW",
                    title="Unused orphan code candidates",
                    evidence=f"{dead_functions_count} orphan candidate{'s' if dead_functions_count > 1 else ''}",
                    meaning="Unreferenced functions increase cognitive clutter and dead AST weight.",
                    action_label="Inspect Dead Code",
                    action_target="dead_code",
                    affected_file=dead_functions[0] if dead_functions else None,
                )
            )
            sig_idx += 1

        if hotspots_count > 0:
            h_file = (
                _normalize_repo_path(
                    getattr(churn_summary.hotspots[0], "file_path", "")
                )
                if churn_summary and churn_summary.hotspots
                else None
            )
            signals_needing_attention.append(
                SignalAttentionItem(
                    id=f"sig-{sig_idx}",
                    severity="MEDIUM",
                    title="High git churn hotspots",
                    evidence=f"{hotspots_count} volatile hotspot{'s' if hotspots_count > 1 else ''}",
                    meaning="Frequently churned modules experience higher defect rates and merge conflicts.",
                    action_label="View Hotspots",
                    action_target="git_history",
                    affected_file=h_file,
                )
            )
            sig_idx += 1

        if unstable_modules_count > 0 or avg_dist > 0.3:
            signals_needing_attention.append(
                SignalAttentionItem(
                    id=f"sig-{sig_idx}",
                    severity="MEDIUM",
                    title="API surface packaging instability",
                    evidence=f"{unstable_modules_count} volatile modules (D = {avg_dist:.2f})",
                    meaning="Modules deviate from main sequence balance between abstractness and instability.",
                    action_label="Review API Surface",
                    action_target="api_surface",
                )
            )
            sig_idx += 1

        # 10. Structured "HEALTHY BASELINE"
        healthy_baseline: List[str] = []
        if cycles_count == 0:
            healthy_baseline.append(
                "Stable acyclic dependency graph with 0 circular loops"
            )
        if len(rule_violations) == 0:
            healthy_baseline.append(
                "Full architectural layer compliance (0 boundary violations)"
            )
        if pub_priv_ratio >= 0.1 and pub_priv_ratio <= 0.6:
            healthy_baseline.append(
                f"Balanced API encapsulation ({pub_priv_ratio:.2f} public-to-private ratio)"
            )
        if dead_functions_count == 0 or dead_code_ratio < 0.05:
            healthy_baseline.append(
                "Clean codebase hygiene with no widespread orphan declarations"
            )
        if reading_path_completeness >= 0.8:
            healthy_baseline.append(
                f"Complete topological onboarding path ({len(recommended_reading_path)} ordered steps)"
            )
        if hotspots_count == 0:
            healthy_baseline.append(
                "Controlled git churn with no volatile defect hotspots"
            )

        # Languages structure
        lang_percentages = {}
        if isinstance(languages_dict, list):
            for lang in languages_dict:
                lang_percentages[lang] = round(100.0 / max(1, len(languages_dict)), 1)
        elif isinstance(languages_dict, dict):
            lang_percentages = languages_dict

        metadata = ReportMetadata(
            repo_name=repo_name,
            owner=owner,
            name=name,
            total_loc=total_loc,
            commits_count=commits_count,
            languages=lang_percentages,
            generated_at=datetime.now(timezone.utc).isoformat(),
            execution_time_ms=round((time.time() - start_time) * 1000.0, 1),
        )

        arch_section = ArchReportSection(
            cycles_count=cycles_count,
            cycles=cycles,
            strongly_connected_components=strongly_connected_components,
            smells_count=len(smells),
            smells=smells,
            rule_violations=rule_violations,
        )

        api_section = ApiReportSection(
            total_exported_symbols=total_exported_symbols,
            public_private_ratio=round(pub_priv_ratio, 2),
            average_distance_main_sequence=avg_dist,
            unstable_modules_count=unstable_modules_count,
        )

        hygiene_section = HygieneReportSection(
            dead_functions_count=dead_functions_count,
            dead_functions=dead_functions,
            dead_code_ratio=round(dead_code_ratio * 100.0, 1),
        )

        onboarding_section = OnboardingReportSection(
            reading_path_completeness=round(reading_path_completeness * 100.0, 1),
            core_entry_points=core_entry_points,
            recommended_reading_path=recommended_reading_path,
        )

        report_model = ReportDataModel(
            metadata=metadata,
            scores=scores,
            architecture=arch_section,
            api_surface=api_section,
            hygiene=hygiene_section,
            onboarding=onboarding_section,
            refactoring_priorities=refactoring_priorities,
            why_this_score=why_this_score,
            signals_needing_attention=signals_needing_attention,
            healthy_baseline=healthy_baseline,
            ai_summary=None,
        )

        # Persist summary results to shared JSON artifact and local SQLite
        save_report_artifact(report_model)
        self.save_report_to_db(report_model)

        return report_model

    def save_report_to_db(self, report: ReportDataModel) -> None:
        """Saves report metadata and serialized JSON content to SQLite."""
        try:
            conn = get_db_connection()
            try:
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute(
                    "INSERT OR IGNORE INTO repositories (repo_name, owner, name) VALUES (?, ?, ?)",
                    (
                        report.metadata.repo_name,
                        report.metadata.owner,
                        report.metadata.name,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO repo_reports (
                        repo_name, overall_score, grade, architecture_score, api_score,
                        hygiene_score, churn_score, readability_score, generated_at, report_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report.metadata.repo_name,
                        report.scores.overall,
                        report.scores.grade,
                        report.scores.architecture,
                        report.scores.api,
                        report.scores.hygiene,
                        report.scores.churn,
                        report.scores.readability,
                        report.metadata.generated_at,
                        report.model_dump_json(),
                    ),
                )
                conn.execute("COMMIT;")
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK;")
                except Exception:
                    pass
                import logging

                logging.getLogger(__name__).error(
                    "Failed to save report to SQLite: %s", exc
                )
            finally:
                conn.close()
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error(
                "Failed to open connection to save report: %s", exc
            )
