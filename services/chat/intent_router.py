"""Intent Router — Phase 4.

Routes classified intents to the appropriate Repository Intelligence sub-system
BEFORE falling back to vector search. This makes structured graph/symbol data
the primary source of truth; embeddings become supporting evidence.

Architecture:
  IntentRouter
    ├── ARCHITECTURE        → ArchitectureService.get_summary()
    ├── CIRCULAR_DEPENDENCY → ArchitectureService.get_cycles()
    ├── API_SURFACE         → APISurfaceService.load(repo_name)
    ├── CALL_GRAPH          → CallGraphService.load_summary(repo_name)
    ├── SYMBOL              → SymbolService.get_definition(repo_name, symbol_name)
    ├── READING_ORDER       → ReadingOrderService.generate_reading_order(repo_name)
    ├── IMPACT_ANALYSIS     → ImpactAnalysisService.analyze()
    ├── GENERAL_QA / UNKNOWN → (no structured data, fall through to vectors)
    └── All intents         → then vector retrieval for supporting code snippets

Each handler returns a RepositoryIntelligence dataclass containing:
  - structured_context: pre-formatted text block injected into the prompt
  - source_files: files referenced by the intelligence layer
  - metadata: arbitrary dict for observability
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .intent_detector import Intent, IntentResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


@dataclass
class RepositoryIntelligence:
    """Structured intelligence gathered from the Repository Intelligence Layer.

    Attributes:
        intent:             The intent that produced this data.
        structured_context: Pre-formatted text block for prompt injection.
                            Empty string when no structured data was found.
        source_files:       Files the intelligence layer referenced.
        metadata:           Raw data / metrics for observability.
        router_elapsed_ms:  Time taken by the router in milliseconds.
    """

    intent: Intent
    structured_context: str = ""
    source_files: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    router_elapsed_ms: float = 0.0

    @property
    def has_data(self) -> bool:
        return bool(self.structured_context.strip())


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class IntentRouter:
    """Routes intents to structured repository intelligence handlers.

    All service dependencies are injected so the router is testable in
    isolation without a running backend.
    """

    def __init__(
        self,
        architecture_service=None,
        graph_service=None,
        symbol_service=None,
        reading_order_service=None,
        impact_analysis_service=None,
        api_surface_service=None,
        call_graph_service=None,
    ) -> None:
        self._arch = architecture_service
        self._graph = graph_service
        self._symbols = symbol_service
        self._reading_order = reading_order_service
        self._impact = impact_analysis_service
        self._api_surface = api_surface_service
        self._call_graph = call_graph_service

    def route(
        self,
        repo_name: str,
        question: str,
        intent_result: IntentResult,
    ) -> RepositoryIntelligence:
        """Dispatch to the correct intelligence handler.

        Args:
            repo_name:     Repository identifier (owner/repo).
            question:      The (pronoun-resolved) user question.
            intent_result: Result from IntentDetector.

        Returns:
            RepositoryIntelligence with structured context (may be empty).
        """
        t0 = time.perf_counter()
        intent = intent_result.intent

        dispatch = {
            Intent.ARCHITECTURE: self._handle_architecture,
            Intent.CIRCULAR_DEPENDENCY: self._handle_circular_dependency,
            Intent.API_SURFACE: self._handle_api_surface,
            Intent.CALL_GRAPH: self._handle_call_graph,
            Intent.SYMBOL: self._handle_symbol,
            Intent.READING_ORDER: self._handle_reading_order,
            Intent.IMPACT_ANALYSIS: self._handle_impact_analysis,
        }

        handler = dispatch.get(intent)
        if handler is None:
            # GENERAL_QA and UNKNOWN fall through to vector search only
            result = RepositoryIntelligence(intent=intent)
        else:
            try:
                result = handler(repo_name, question, intent_result)
            except Exception as exc:
                logger.warning(
                    "IntentRouter: handler for %s failed (repo=%s): %s",
                    intent.value,
                    repo_name,
                    exc,
                )
                result = RepositoryIntelligence(intent=intent)

        result.router_elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "IntentRouter: repo=%s intent=%s has_data=%s elapsed=%.1fms",
            repo_name,
            intent.value,
            result.has_data,
            result.router_elapsed_ms,
        )
        return result

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _handle_architecture(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._arch:
            return RepositoryIntelligence(intent=ir.intent)

        summary = self._arch.get_summary(repo_name)
        if not summary:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_architecture_summary"},
            )

        lines = [
            "## Repository Architecture",
            f"- **Total files:** {summary.total_files}",
            f"- **Total dependencies:** {summary.total_dependencies}",
        ]
        from core.file_classifier import classify_file, CATEGORY_PRODUCTION

        prod_entries = []
        example_entries = []
        for ep in summary.entry_points or []:
            classification = classify_file(ep)
            if classification["category"] == CATEGORY_PRODUCTION:
                prod_entries.append(ep)
            else:
                example_entries.append(ep)

        if prod_entries:
            lines.append(
                "- **Primary Production Entry Points:** "
                + ", ".join(f"`{e}`" for e in prod_entries[:8])
            )
        elif summary.entry_points:
            lines.append(
                "- **Entry points:** "
                + ", ".join(f"`{e}`" for e in summary.entry_points[:8])
            )

        if example_entries:
            lines.append(
                "- **Example / Documentation Applications:** "
                + ", ".join(f"`{e}`" for e in example_entries[:5])
                + " (Note: these are sample/demo applications, not the core framework entry points)"
            )

        if summary.core_modules:
            lines.append(
                "- **Core modules:** "
                + ", ".join(f"`{m}`" for m in summary.core_modules[:10])
            )
        if summary.high_coupling_modules:
            lines.append(
                "- **High coupling:** "
                + ", ".join(f"`{m}`" for m in summary.high_coupling_modules[:8])
            )
        if hasattr(summary, "tech_stack") and summary.tech_stack:
            lines.append("- **Tech stack:** " + ", ".join(summary.tech_stack[:10]))

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context="\n".join(lines),
            source_files=list(prod_entries or summary.entry_points or [])[:5],
            metadata={
                "total_files": summary.total_files,
                "entry_points": list(summary.entry_points or []),
                "production_entry_points": prod_entries,
                "example_entry_points": example_entries,
            },
        )

    def _handle_circular_dependency(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._arch:
            return RepositoryIntelligence(intent=ir.intent)

        summary = self._arch.get_summary(repo_name)
        if not summary:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_architecture_summary"},
            )

        # Try to get cycle data from summary
        cycles = getattr(summary, "cycles", None) or []
        has_cycles = bool(cycles)
        cycle_count = len(cycles)

        if not has_cycles:
            context = (
                "## Circular Dependencies\n"
                "✅ No circular dependencies detected in this repository.\n"
                "The dependency graph is acyclic."
            )
        else:
            cycle_lines = [
                f"## Circular Dependencies — {cycle_count} cycle(s) detected"
            ]
            for i, cycle in enumerate(cycles[:10], 1):
                if isinstance(cycle, (list, tuple)):
                    cycle_lines.append(
                        f"**Cycle {i}:** " + " → ".join(f"`{n}`" for n in cycle)
                    )
                else:
                    cycle_lines.append(f"**Cycle {i}:** `{cycle}`")
            if cycle_count > 10:
                cycle_lines.append(f"… and {cycle_count - 10} more.")
            context = "\n".join(cycle_lines)

        involved_files = []
        for c in cycles[:5]:
            if isinstance(c, (list, tuple)):
                involved_files.extend(list(c)[:3])

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context=context,
            source_files=involved_files,
            metadata={"cycle_count": cycle_count, "has_cycles": has_cycles},
        )

    def _handle_api_surface(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._api_surface:
            return RepositoryIntelligence(intent=ir.intent)

        # FIX: APISurfaceService.load() takes a single repo_name string.
        # Previous code incorrectly split and passed (owner, repo) as two args.
        try:
            surface = self._api_surface.load(repo_name)
        except Exception as exc:
            logger.debug("API surface load failed: %s", exc)
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": str(exc)},
            )

        if not surface:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_api_surface_data"},
            )

        symbols = getattr(surface, "symbols", []) or []
        # ClassifiedSymbol.visibility is a Visibility enum — compare by value
        public = [
            s
            for s in symbols
            if getattr(s, "visibility", None) is not None
            and getattr(s.visibility, "value", s.visibility) in ("public", "PUBLIC")
        ]

        lines = [f"## API Surface ({len(public)} public symbols)"]
        for sym in public[:20]:
            kind = getattr(sym, "api_kind", None)
            kind_str = getattr(kind, "value", str(kind)) if kind else ""
            name = getattr(sym, "name", "")
            file_path = getattr(sym, "file_path", "")
            lines.append(f"- `{name}` ({kind_str}) — `{file_path}`")
        if len(public) > 20:
            lines.append(f"… and {len(public) - 20} more.")

        source_files = list(
            {
                getattr(s, "file_path", "")
                for s in public[:10]
                if getattr(s, "file_path", "")
            }
        )

        stats = getattr(surface, "stats", None)
        if stats:
            lines.append(
                f"\n**Stats:** {getattr(stats, 'public_count', 0)} public, "
                f"{getattr(stats, 'internal_count', 0)} internal, "
                f"{getattr(stats, 'orphan_public_count', 0)} orphaned."
            )

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context="\n".join(lines),
            source_files=source_files,
            metadata={"public_count": len(public)},
        )

    def _handle_call_graph(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._call_graph:
            return RepositoryIntelligence(intent=ir.intent)

        # FIX: CallGraphService.load_summary() takes a single repo_name string.
        # Previous code called non-existent get_summary(owner, repo).
        try:
            summary = self._call_graph.load_summary(repo_name)
        except Exception as exc:
            logger.debug("Call graph load failed: %s", exc)
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": str(exc)},
            )

        if not summary:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_call_graph_data"},
            )

        # CallGraphSummary fields: node_count, edge_count, top_fan_in, top_fan_out
        node_count = getattr(summary, "node_count", 0)
        edge_count = getattr(summary, "edge_count", 0)
        lines = [
            "## Call Graph Summary",
            f"- **Functions:** {node_count}",
            f"- **Call relationships:** {edge_count}",
        ]

        # top_fan_in is a list of dicts: [{"node_id": str, "fan_in": int}, ...]
        top_fan_in = getattr(summary, "top_fan_in", []) or []
        if top_fan_in:
            lines.append("\n**Most-called functions:**")
            for node in top_fan_in[:8]:
                # node is a dict with "node_id" and "fan_in" keys
                node_id = (
                    node.get("node_id", "")
                    if isinstance(node, dict)
                    else getattr(node, "node_id", "")
                )
                callers = (
                    node.get("fan_in", 0)
                    if isinstance(node, dict)
                    else getattr(node, "fan_in", 0)
                )
                # node_id format is "file_path::qualified_name" — extract the name part
                display = node_id.split("::")[-1] if "::" in node_id else node_id
                lines.append(f"  - `{display}` ← {callers} callers")

        for entity in ir.entities:
            lines.append(
                f"\n*(Tip: use /api/call-graph to trace calls to/from `{entity}`)*"
            )
            break

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context="\n".join(lines),
            source_files=[],
            metadata={"node_count": node_count, "edge_count": edge_count},
        )

    def _handle_symbol(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._symbols or not ir.entities:
            return RepositoryIntelligence(intent=ir.intent)

        # FIX: SymbolService.get_definition(repo_name, symbol_name) takes two
        # args and returns Optional[Symbol] (not a list).
        # Previous code called non-existent find_definition(owner, repo, entity).
        found_symbols = []
        for entity in ir.entities[:3]:
            try:
                sym = self._symbols.get_definition(repo_name, entity)
                if sym is not None:
                    found_symbols.append(sym)
            except Exception as exc:
                logger.debug("Symbol lookup failed for '%s': %s", entity, exc)

        if not found_symbols:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_symbols_found", "entities": ir.entities},
            )

        lines = [f"## Symbol Lookup — {len(found_symbols)} result(s)"]
        source_files = []
        for sym in found_symbols:
            name = getattr(sym, "name", "")
            sym_type = getattr(sym, "type", "")
            file_path = getattr(sym, "file_path", "")
            line_number = getattr(sym, "line_number", None)
            loc = f"line {line_number}" if line_number else ""
            lines.append(f"- `{name}` ({sym_type}) in `{file_path}` {loc}".strip())
            if file_path:
                source_files.append(file_path)

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context="\n".join(lines),
            source_files=list(dict.fromkeys(source_files)),
            metadata={"entities_searched": ir.entities},
        )

    def _handle_reading_order(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._reading_order:
            return RepositoryIntelligence(intent=ir.intent)

        # FIX: ReadingOrderService.generate_reading_order(repo_name) takes a
        # single string and returns ReadingOrder with ordered_files (not entries).
        # Previous code called non-existent get_reading_order(owner, repo).
        try:
            reading_order = self._reading_order.generate_reading_order(repo_name)
        except Exception as exc:
            logger.debug("Reading order generation failed: %s", exc)
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": str(exc)},
            )

        if not reading_order:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_reading_order_data"},
            )

        # ReadingOrder.ordered_files is a List[ReadingOrderEntry]
        # ReadingOrderEntry fields: rank, file_path, reason, tier, score
        ordered_files = getattr(reading_order, "ordered_files", []) or []

        lines = [f"## Recommended Reading Order ({len(ordered_files)} files)"]
        source_files = []
        for entry in ordered_files[:15]:
            file_path = getattr(entry, "file_path", "")
            tier = getattr(entry, "tier", "")
            reason = getattr(entry, "reason", "")
            rank = getattr(entry, "rank", "")
            tier_label = f" [{tier}]" if tier else ""
            reason_text = f" — {reason}" if reason else ""
            lines.append(f"{rank}. `{file_path}`{tier_label}{reason_text}")
            if file_path:
                source_files.append(file_path)

        if len(ordered_files) > 15:
            lines.append(f"… and {len(ordered_files) - 15} more files.")

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context="\n".join(lines),
            source_files=source_files[:10],
            metadata={"total_files": len(ordered_files)},
        )

    def _handle_impact_analysis(
        self, repo_name: str, question: str, ir: IntentResult
    ) -> RepositoryIntelligence:
        if not self._impact or not ir.entities:
            return RepositoryIntelligence(intent=ir.intent)

        seed = (
            ir.entities[0] if ir.entities else (ir.keywords[0] if ir.keywords else "")
        )
        if not seed:
            return RepositoryIntelligence(intent=ir.intent)

        try:
            impact = self._impact.analyze(repo_name, seed)
        except Exception as exc:
            logger.debug("Impact analysis failed for seed '%s': %s", seed, exc)
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": str(exc)},
            )

        if not impact:
            return RepositoryIntelligence(
                intent=ir.intent,
                metadata={"reason": "no_impact_data"},
            )

        risk_level = getattr(impact, "risk_level", "unknown")
        affected = getattr(impact, "affected_files", []) or []
        direct = getattr(impact, "direct_dependents", []) or []
        reverse = getattr(impact, "reverse_dependents", []) or []

        lines = [
            f"## Impact Analysis — seed: `{seed}`",
            f"- **Risk level:** {risk_level}",
            f"- **Total affected files:** {len(affected)}",
            f"- **Direct dependents:** {len(direct)}",
            f"- **Reverse dependents:** {len(reverse)}",
        ]
        if affected:
            lines.append("\n**Affected files (top 10):**")
            for f in affected[:10]:
                lines.append(f"  - `{f}`")

        return RepositoryIntelligence(
            intent=ir.intent,
            structured_context="\n".join(lines),
            source_files=list(affected[:10]),
            metadata={
                "risk_level": risk_level,
                "affected_count": len(affected),
                "seed": seed,
            },
        )
