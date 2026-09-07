"""Impact Analysis Service — Evidence-Backed Repository Intelligence.

Predicts which repository files, symbols, callers, API routes, and tests are affected
by a proposed change (issue text, refactor request, feature prompt) by combining:
  1. Exact Symbol Resolution        — extracts identifier tokens and queries SymbolIndex
  2. Call Graph Traversal           — determines direct and transitive callers with line locations
  3. Module Dependency Traversal    — walks forward/backward import edges
  4. API Surface Cross-Referencing  — identifies exposed public/internal routes and exported interfaces
  5. Test Impact Discovery          — traces test files calling or importing affected code
  6. Architecture Boundary Audit    — identifies cross-subsystem transitions
  7. Blast Radius & Deterministic Risk — scores XS/S/M/L/XL and low/medium/high/extreme
  8. Structured Evidence Model      — emits FACT, INFERENCE, PREDICTION, RECOMMENDATION items
  9. Dependency Implementation Plan — topological order of modification steps

Zero LLM hallucination: all structural links, line references, and caller relations
are deterministically computed from indexed repository facts.
"""

from __future__ import annotations

import ast
from collections import defaultdict
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

from models.phase2 import (
    ApiExposureInfo,
    CallerInfo,
    ConfidenceTier,
    DependencyPath,
    EvidenceItem,
    EvidenceKind,
    EvidenceStrength,
    ImpactAnalysis,
    ImpactedFileDetail,
    TestImpactItem,
)
from services.architecture_service import ArchitectureService
from services.graph_service import GraphService
from services.symbol_service import SymbolService
from services.call_graph_service import CallGraphService
from services.api_surface_service import APISurfaceService
from services.impact_debugger import ImpactDebugger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blast radius categories
# ---------------------------------------------------------------------------
# XS = 1–2 files, S = 3–5 files, M = 6–12 files, L = 13–25 files, XL = >25 files
_MAX_TRAVERSAL_DEPTH = 4
_MAX_PATHS = 5

# Component detection: directory/filename → component label
_COMPONENT_MAP: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"auth|oauth|login|token|jwt|session", re.I), "Authentication"),
    (re.compile(r"api|route|endpoint|controller|view", re.I), "API Layer"),
    (
        re.compile(r"db|database|model|migration|schema|orm|sql|chroma|sqlite", re.I),
        "Database",
    ),
    (
        re.compile(r"front|ui|component|page|template|html|css|tsx|jsx", re.I),
        "Frontend",
    ),
    (re.compile(r"service|retriev|embed|chunk|github|mcp", re.I), "Services"),
    (re.compile(r"model|schema|pydantic|dataclass", re.I), "Models"),
    (re.compile(r"agent|evaluat|explainer|analyzer|mapper", re.I), "Agents"),
    (re.compile(r"memory|cache|store|chroma", re.I), "Memory"),
    (re.compile(r"test|spec|fixture|mock", re.I), "Tests"),
]


class ImpactAnalysisService:
    """Predicts change impact combining exact symbol resolution, call graphs, API surface, and import graphs."""

    def __init__(
        self,
        architecture_service: Optional[ArchitectureService] = None,
        graph_service: Optional[GraphService] = None,
        symbol_service: Optional[SymbolService] = None,
        call_graph_service: Optional[CallGraphService] = None,
        api_surface_service: Optional[APISurfaceService] = None,
    ) -> None:
        self.architecture_service = architecture_service or ArchitectureService()
        self.graph_service = graph_service or GraphService()
        self.symbol_service = symbol_service or SymbolService()
        self.call_graph_service = call_graph_service or CallGraphService()
        self.api_surface_service = api_surface_service or APISurfaceService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_change(
        self,
        repo_name: str,
        issue_text: str,
        operating_mode: str = "BALANCED",
    ) -> ImpactAnalysis:
        """Predict which files, symbols, callers, routes, and tests are affected by a change.

        Args:
            repo_name:   Repository identifier (owner/repo).
            issue_text:  Natural language change request or issue description.

        Returns:
            An evidence-backed ImpactAnalysis model.
        """
        # 1. Load dependency graph and architecture summary
        graph = self.graph_service.load_graph(repo_name)
        if graph is None:
            raise ValueError(
                f"No dependency graph found for '{repo_name}'. "
                "Please analyze the repository first."
            )

        if graph.number_of_nodes() == 0:
            return ImpactAnalysis(
                repo=repo_name,
                issue_text=issue_text,
                directly_affected_files=[],
                indirectly_affected_files=[],
                affected_components=[],
                risk_level="low",
                estimated_file_count=0,
                dependency_paths=[],
                confidence=0,
                blast_radius_category="XS",
                affected_symbols=[],
                direct_callers=[],
                transitive_callers=[],
                api_exposure=None,
                affected_tests=[],
                architecture_boundaries=[],
                evidence_items=[],
                implementation_order=[],
            )

        summary = self.architecture_service.get_summary(repo_name)
        core_set: Set[str] = set(summary.core_modules if summary else [])
        coupling_set: Set[str] = set(summary.high_coupling_modules if summary else [])
        entry_set: Set[str] = set(summary.entry_points if summary else [])

        evidence_items: List[EvidenceItem] = []
        affected_symbols_names: List[str] = []
        seed_files: Set[str] = set()

        # 2. Extract keywords, candidate identifiers, and explicit file context
        keywords = self._extract_keywords(issue_text)
        identifiers = self._extract_identifiers(issue_text)
        file_context = self._extract_file_context(issue_text)
        logger.info(
            "Impact analysis for %s | keywords=%s | identifiers=%s | file_ctx=%s",
            repo_name,
            keywords,
            identifiers,
            file_context,
        )

        # 3. Exact symbol resolution via SymbolService supporting qualified lookups
        resolved_symbols = self._resolve_symbols(
            repo_name,
            identifiers,
            file_context=file_context,
            evidence_items=evidence_items,
        )
        if resolved_symbols:
            for sym in resolved_symbols:
                s_name = getattr(sym, "name", str(sym))
                affected_symbols_names.append(s_name)
                s_file = getattr(sym, "file_path", "")
                if s_file:
                    seed_files.add(s_file)
                evidence_items.append(
                    EvidenceItem(
                        kind=EvidenceKind.FACT,
                        statement=f"Target symbol '{s_name}' ({getattr(sym, 'type', 'symbol')}) defined in repository.",
                        source_reference=f"{s_file}:{getattr(sym, 'line_number', 1)}",
                        confidence=100,
                    )
                )
        elif identifiers:
            evidence_items.append(
                EvidenceItem(
                    kind=EvidenceKind.INFERENCE,
                    statement=f"No exact symbol match found in symbol index for tokens: {', '.join(identifiers[:4])}; falling back to semantic file and path matching.",
                    source_reference=None,
                    confidence=80,
                )
            )

        # 4. Find path-matched seed files if needed
        if file_context and file_context in graph:
            seed_files.add(file_context)

        path_seeds = self._match_files_to_keywords(graph, keywords, issue_text)
        seed_files.update(path_seeds)
        seed_list = sorted(seed_files)

        if not seed_list:
            seed_list = [
                fp
                for fp in graph.nodes()
                if os.path.basename(fp)
                in {"main.py", "api.py", "app.py", "__main__.py"}
            ][:3]

        for s in seed_list:
            evidence_items.append(
                EvidenceItem(
                    kind=EvidenceKind.FACT,
                    statement=f"Seed module identified as directly relevant to change request: '{s}'.",
                    source_reference=s,
                    confidence=95,
                )
            )

        # 5. Call Graph resolution: direct and transitive callers with exact paths
        direct_callers, transitive_callers = self._resolve_callers(
            repo_name=repo_name,
            seed_files=seed_list,
            resolved_symbols=resolved_symbols,
            evidence_items=evidence_items,
        )

        # 6. API surface cross-referencing
        api_exposure = self._resolve_api_exposure(
            repo_name=repo_name,
            seed_files=seed_list,
            affected_symbols=affected_symbols_names,
            direct_callers=direct_callers,
            evidence_items=evidence_items,
        )

        # 7. Test impact discovery (ranked by evidence strength)
        affected_tests = self._resolve_test_impact(
            repo_name=repo_name,
            graph=graph,
            seed_files=seed_list,
            affected_symbols=affected_symbols_names,
            resolved_symbols=resolved_symbols,
            direct_callers=direct_callers,
            transitive_callers=transitive_callers,
            api_exposure=api_exposure,
            evidence_items=evidence_items,
        )

        # 8. Symbol-Aware Dependency Analysis & Confidence Tier Classification
        target_symbol_names = affected_symbols_names or identifiers
        high_conf_files: Set[str] = set()
        med_conf_files: Set[str] = set()
        low_conf_files: Set[str] = set()
        file_details: Dict[str, ImpactedFileDetail] = {}

        # 8a. Seed files (Level 1: Exact Symbol Definition / Explicit Target)
        for s in seed_list:
            high_conf_files.add(s)
            file_details[s] = ImpactDebugger.create_detail(
                file_path=s,
                confidence_tier=ConfidenceTier.HIGH,
                evidence_strength=EvidenceStrength.LEVEL_1_EXACT_SYMBOL,
                reason=f"Defines or implements target symbol(s): {', '.join(target_symbol_names[:3]) or 'root component'}.",
                propagation_path=[s],
                target_symbols=target_symbol_names,
                verifications={"is_seed": True, "has_symbol_def": True},
            )

        # 8b. Direct Callers (Level 2: Exact Call Edge)
        for c in direct_callers:
            high_conf_files.add(c.file_path)
            file_details[c.file_path] = ImpactDebugger.create_detail(
                file_path=c.file_path,
                confidence_tier=ConfidenceTier.HIGH,
                evidence_strength=EvidenceStrength.LEVEL_2_EXACT_CALL,
                reason=f"Direct caller '{c.caller_name}' calls target symbol at line {c.line_number or 'unknown'}.",
                propagation_path=c.propagation_path
                or [s for s in seed_list] + [c.caller_id],
                target_symbols=[c.caller_name],
                verifications={"is_direct_caller": True, "call_depth": 1},
            )

        # 8c. Symbol-Aware Importers (Level 3: Symbol Dependency vs Level 6: Module Dependency)
        for seed in seed_list:
            if seed in graph:
                for pred in graph.predecessors(seed):
                    if pred in high_conf_files:
                        continue
                    if self._file_references_symbol(
                        repo_name, pred, target_symbol_names
                    ):
                        high_conf_files.add(pred)
                        file_details[pred] = ImpactDebugger.create_detail(
                            file_path=pred,
                            confidence_tier=ConfidenceTier.HIGH,
                            evidence_strength=EvidenceStrength.LEVEL_3_SYMBOL_DEPENDENCY,
                            reason=f"Directly imports '{seed}' and references target symbol '{target_symbol_names[0] if target_symbol_names else ''}'.",
                            propagation_path=[seed, pred],
                            target_symbols=target_symbol_names,
                            verifications={
                                "is_direct_import": True,
                                "references_symbol": True,
                            },
                        )
                    else:
                        if not self._is_test_file(pred):
                            med_conf_files.add(pred)
                        else:
                            low_conf_files.add(pred)
                        file_details[pred] = ImpactDebugger.create_detail(
                            file_path=pred,
                            confidence_tier=ConfidenceTier.MEDIUM
                            if not self._is_test_file(pred)
                            else ConfidenceTier.LOW,
                            evidence_strength=EvidenceStrength.LEVEL_6_MODULE_DEPENDENCY,
                            reason=f"Directly imports module '{seed}', but does not explicitly reference changed symbol.",
                            propagation_path=[seed, pred],
                            target_symbols=[],
                            verifications={
                                "is_direct_import": True,
                                "references_symbol": False,
                            },
                        )

                # Direct dependencies imported by seed file (callees / downstream modules)
                for succ in graph.successors(seed):
                    if succ not in high_conf_files and succ not in med_conf_files:
                        if not self._is_test_file(succ):
                            med_conf_files.add(succ)
                        else:
                            low_conf_files.add(succ)
                        file_details[succ] = ImpactDebugger.create_detail(
                            file_path=succ,
                            confidence_tier=ConfidenceTier.MEDIUM
                            if not self._is_test_file(succ)
                            else ConfidenceTier.LOW,
                            evidence_strength=EvidenceStrength.LEVEL_6_MODULE_DEPENDENCY,
                            reason=f"Direct dependency imported by modified module '{seed}'.",
                            propagation_path=[seed, succ],
                            target_symbols=[],
                            verifications={"is_direct_dependency": True},
                        )

        # 8d. Transitive Callers (depth 2 = Medium, depth 3 = Low)
        for tc in transitive_callers:
            if tc.file_path not in high_conf_files:
                tier = ConfidenceTier.MEDIUM if tc.depth == 2 else ConfidenceTier.LOW
                if tier == ConfidenceTier.MEDIUM:
                    med_conf_files.add(tc.file_path)
                else:
                    low_conf_files.add(tc.file_path)
                file_details[tc.file_path] = ImpactDebugger.create_detail(
                    file_path=tc.file_path,
                    confidence_tier=tier,
                    evidence_strength=EvidenceStrength.LEVEL_2_EXACT_CALL,
                    reason=f"Transitive caller '{tc.caller_name}' reached at call depth {tc.depth}.",
                    propagation_path=tc.propagation_path,
                    target_symbols=[tc.caller_name],
                    verifications={
                        "is_transitive_caller": True,
                        "call_depth": tc.depth,
                    },
                )

        # 8e. Direct API Routes (Level 4: API Contract)
        for route in api_exposure.public_routes if api_exposure else []:
            match = re.search(r"\(([^:]+):(\d+)\)", route)
            if match:
                r_file = match.group(1)
                if r_file not in high_conf_files and r_file in graph:
                    high_conf_files.add(r_file)
                    med_conf_files.discard(r_file)
                    file_details[r_file] = ImpactDebugger.create_detail(
                        file_path=r_file,
                        confidence_tier=ConfidenceTier.HIGH,
                        evidence_strength=EvidenceStrength.LEVEL_4_API_CONTRACT,
                        reason=f"Hosts exposed public API route: {route}.",
                        propagation_path=[s for s in seed_list] + [r_file],
                        target_symbols=target_symbol_names,
                        verifications={"is_public_api_route": True},
                    )

        # 8f. Affected Tests (Ranked by Evidence Strength)
        for t in affected_tests:
            t_file = t.test_file
            ev_strength = getattr(
                EvidenceStrength,
                t.evidence_strength,
                EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP,
            )
            conf_tier = getattr(ConfidenceTier, t.confidence_tier, ConfidenceTier.HIGH)
            file_details[t_file] = ImpactDebugger.create_detail(
                file_path=t_file,
                confidence_tier=conf_tier,
                evidence_strength=ev_strength,
                reason=t.reason,
                propagation_path=t.propagation_path
                or ([s for s in seed_list] + [t_file]),
                target_symbols=target_symbol_names,
                verifications={
                    "is_test": True,
                    "impact_type": t.impact_type,
                    "evidence_paths": t.evidence_paths,
                },
            )

        # 8g. Transitive BFS predecessors (2 hops away) without symbol usage -> LOW CONFIDENCE
        for seed in seed_list:
            bfs_hops = self._bfs(graph, seed, direction="reverse", depth=2)
            for hop_file in bfs_hops:
                if (
                    hop_file not in high_conf_files
                    and hop_file not in med_conf_files
                    and hop_file not in low_conf_files
                ):
                    low_conf_files.add(hop_file)
                    file_details[hop_file] = ImpactDebugger.create_detail(
                        file_path=hop_file,
                        confidence_tier=ConfidenceTier.LOW,
                        evidence_strength=EvidenceStrength.LEVEL_6_MODULE_DEPENDENCY,
                        reason=f"Transitive import dependency on '{seed}' without verified symbol usage.",
                        propagation_path=[seed, hop_file],
                        target_symbols=[],
                        verifications={"is_transitive_import": True},
                    )

        # Clean tiered sets (Separating production code files from tests)
        final_high = sorted(
            list(f for f in high_conf_files if not self._is_test_file(f))
        )
        final_med = sorted(
            list(
                f
                for f in (med_conf_files - high_conf_files)
                if not self._is_test_file(f)
            )
        )
        final_low = sorted(
            list(
                f
                for f in (low_conf_files - high_conf_files - med_conf_files)
                if not self._is_test_file(f)
            )
        )

        # Directly affected: High-confidence production core
        directly_affected = final_high
        # Indirectly affected: Medium-confidence production dependents
        indirectly_affected = final_med
        all_affected = directly_affected + indirectly_affected

        # 9. Architecture boundaries crossed
        affected_components = self._detect_components(all_affected)
        boundaries = self._detect_boundaries(graph, seed_list, all_affected)
        for b in boundaries:
            evidence_items.append(
                EvidenceItem(
                    kind=EvidenceKind.INFERENCE,
                    statement=f"Change propagation crosses architectural layer boundary: {b}.",
                    source_reference=None,
                    confidence=85,
                )
            )

        # 10. Dependency paths for primary seeds
        dep_paths = self._build_dependency_paths(
            graph, seed_list, set(indirectly_affected), max_paths=_MAX_PATHS
        )

        # 11. Deterministic Blast Radius & Risk scoring (driven by verified impact)
        # Decouple test impact from production runtime blast radius (Phase 14)
        prod_affected = [f for f in all_affected if not self._is_test_file(f)]
        total_affected = len(prod_affected)
        blast_category = self._classify_blast_radius(total_affected)
        risk_level, confidence = self._compute_risk_deterministic(
            total_affected=total_affected,
            direct_callers_count=len(
                [c for c in direct_callers if not self._is_test_file(c.file_path)]
            ),
            public_routes_count=len(api_exposure.public_routes) if api_exposure else 0,
            boundaries_count=len(boundaries),
            all_affected=prod_affected,
            core_set=core_set,
            coupling_set=coupling_set,
            entry_set=entry_set,
            total_graph_nodes=graph.number_of_nodes(),
        )

        evidence_items.append(
            EvidenceItem(
                kind=EvidenceKind.PREDICTION,
                statement=(
                    f"Predicted blast radius: {blast_category} ({risk_level.upper()} risk). "
                    f"Impacts {len(final_high)} high-confidence files, {len(final_med)} medium-confidence files, "
                    f"and {len(final_low)} exploratory candidates with {len(direct_callers)} direct callers."
                ),
                source_reference=None,
                confidence=confidence,
            )
        )

        # 12. Implementation order (dependency-ordered)
        implementation_order = self._generate_implementation_order(
            seed_files=seed_list,
            directly_affected=directly_affected,
            indirectly_affected=indirectly_affected,
            direct_callers=direct_callers,
            api_exposure=api_exposure,
            affected_tests=affected_tests,
            evidence_items=evidence_items,
        )

        tiered_files = {
            "high": final_high,
            "medium": final_med,
            "low": final_low,
        }
        details_list = [file_details[fp] for fp in sorted(file_details.keys())]
        verified_cnt = len(final_high) + sum(
            1 for t in affected_tests if t.confidence_tier == "HIGH"
        )
        likely_cnt = len(final_med) + sum(
            1 for t in affected_tests if t.confidence_tier == "MEDIUM"
        )
        cand_cnt = len(final_low) + sum(
            1 for t in affected_tests if t.confidence_tier == "LOW"
        )

        if operating_mode.upper() == "SAFE":
            effective_directly = final_high
            effective_indirectly = []
        elif operating_mode.upper() == "EXPLORATORY":
            effective_directly = final_high
            effective_indirectly = final_med + final_low
        else:
            effective_directly = final_high
            effective_indirectly = final_med

        return ImpactAnalysis(
            repo=repo_name,
            issue_text=issue_text,
            directly_affected_files=effective_directly,
            indirectly_affected_files=effective_indirectly,
            affected_components=affected_components,
            risk_level=risk_level,
            estimated_file_count=len(effective_directly + effective_indirectly),
            dependency_paths=dep_paths,
            confidence=confidence,
            blast_radius_category=blast_category,
            affected_symbols=affected_symbols_names,
            direct_callers=direct_callers,
            transitive_callers=transitive_callers,
            api_exposure=api_exposure,
            affected_tests=affected_tests,
            architecture_boundaries=boundaries,
            evidence_items=evidence_items,
            implementation_order=implementation_order,
            high_confidence_files=final_high,
            medium_confidence_files=final_med,
            low_confidence_files=final_low,
            tiered_files=tiered_files,
            impacted_file_details=details_list,
            verified_impact_count=verified_cnt,
            likely_impact_count=likely_cnt,
            candidate_count=cand_cnt,
            operating_mode=operating_mode.upper(),
        )

    # ------------------------------------------------------------------
    # Exact Symbol Resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_identifiers(text: str) -> List[str]:
        """Extract explicit identifiers (qualified names, functions, classes, methods)."""
        tokens: Set[str] = set()

        # 1. Matches dotted qualified names e.g. Session.send, HTTPAdapter.cert_verify
        dotted = re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b", text
        )
        for d in dotted:
            if not d.endswith((".py", ".ts", ".tsx", ".js", ".json", ".md")):
                tokens.add(d)

        # 2. Matches calls e.g. foo() or Bar.baz()
        calls = re.findall(
            r"([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\(", text
        )
        for c in calls:
            tokens.add(c)
            tokens.add(c.split(".")[-1])

        # 3. Matches CamelCase identifiers or snake_case identifiers with underscore
        words = re.findall(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", text)
        for w in words:
            if "_" in w and len(w) >= 3:
                tokens.add(w)
            elif (
                any(ch.isupper() for ch in w)
                and any(ch.islower() for ch in w)
                and len(w) >= 3
            ):
                tokens.add(w)

        # Stop words & common imperative verbs filter (case-insensitive)
        _IDENT_STOP = {
            "add",
            "added",
            "adding",
            "modify",
            "modified",
            "modifying",
            "update",
            "updated",
            "updating",
            "change",
            "changed",
            "changing",
            "fix",
            "fixed",
            "fixing",
            "remove",
            "removed",
            "removing",
            "delete",
            "deleted",
            "deleting",
            "implement",
            "implemented",
            "implementing",
            "refactor",
            "refactored",
            "refactoring",
            "support",
            "supported",
            "supporting",
            "create",
            "created",
            "creating",
            "ensure",
            "ensured",
            "ensuring",
            "allow",
            "allowed",
            "allowing",
            "enable",
            "enabled",
            "enabling",
            "true",
            "false",
            "none",
            "http",
            "rest",
            "json",
            "get",
            "post",
            "put",
            "patch",
            "jwt",
            "oauth",
            "python",
            "javascript",
            "typescript",
            "html",
            "css",
            "api",
            "url",
            "uri",
            "task",
            "issue",
            "method",
            "class",
            "function",
            "variable",
            "parameter",
            "return",
            "model",
        }
        filtered = [
            t
            for t in tokens
            if t.lower() not in _IDENT_STOP
            and not t.endswith((".py", ".ts", ".tsx", ".js", ".json", ".md"))
        ]
        return sorted(filtered, key=lambda x: ("." in x, len(x)), reverse=True)[:15]

    @staticmethod
    def _extract_file_context(text: str) -> Optional[str]:
        """Extract explicit file paths mentioned in issue text e.g. 'in fastapi/security/oauth2.py'."""
        paths = re.findall(r"([a-zA-Z0-9_./-]+\.(?:py|ts|tsx|js|jsx))", text)
        return paths[0] if paths else None

    def _resolve_symbols(
        self,
        repo_name: str,
        identifiers: List[str],
        file_context: Optional[str] = None,
        evidence_items: Optional[List[EvidenceItem]] = None,
    ) -> List[Any]:
        """Query SymbolService for matches supporting qualified names and ambiguity."""
        if not self.symbol_service or not identifiers:
            return []

        if not hasattr(self, "_symbol_query_cache"):
            self._symbol_query_cache = {}
        cache_key = (repo_name, tuple(identifiers), file_context)
        if cache_key in self._symbol_query_cache:
            return self._symbol_query_cache[cache_key]

        resolved = []
        seen_sym_keys: Set[str] = set()

        for ident in identifiers:
            matches = []
            if hasattr(self.symbol_service, "find_matching_symbols"):
                matches = self.symbol_service.find_matching_symbols(
                    repo_name, ident, file_context=file_context
                )

            if not matches and hasattr(self.symbol_service, "get_definition"):
                simple_name = ident.split(".")[-1]
                single = self.symbol_service.get_definition(repo_name, simple_name)
                if single:
                    matches = [single]

            if not matches:
                continue

            # Check if multiple candidate definitions exist across distinct files
            distinct_files = {s.file_path for s in matches}
            if len(distinct_files) > 1 and not file_context:
                if evidence_items is not None:
                    locs = ", ".join(
                        [f"{s.file_path}:{s.line_number}" for s in matches[:4]]
                    )
                    evidence_items.append(
                        EvidenceItem(
                            kind=EvidenceKind.INFERENCE,
                            statement=f"AMBIGUOUS SYMBOL: multiple definitions for '{ident}' in [{locs}]; contextual qualification recommended.",
                            source_reference=matches[0].file_path,
                            confidence=60,
                        )
                    )
                for s in matches[:3]:
                    key = f"{s.file_path}::{s.name}"
                    if key not in seen_sym_keys:
                        seen_sym_keys.add(key)
                        resolved.append(s)
            else:
                for s in matches:
                    key = f"{s.file_path}::{s.name}"
                    if key not in seen_sym_keys:
                        seen_sym_keys.add(key)
                        resolved.append(s)

        self._symbol_query_cache[cache_key] = resolved
        return resolved

    def _file_references_symbol(
        self, repo_name: str, file_path: str, symbols: List[str]
    ) -> bool:
        """Check whether a repository file mentions or references any of the symbols."""
        if not symbols:
            return False
        clean_symbols = [s.split(".")[-1] for s in symbols if s]
        if not clean_symbols:
            return False

        if not hasattr(self, "_file_content_cache"):
            self._file_content_cache = {}

        safe_name = repo_name.replace("/", "_")
        cache_key = (safe_name, file_path)
        content = self._file_content_cache.get(cache_key)

        if content is None:
            for base in ["data/cloned_repos", "."]:
                cand = os.path.join(base, safe_name, file_path)
                if not os.path.exists(cand):
                    cand = os.path.join(
                        base, safe_name.replace("VarshithReddy2006_", ""), file_path
                    )
                if os.path.exists(cand) and os.path.isfile(cand):
                    try:
                        with open(cand, "r", encoding="utf-8", errors="ignore") as fp:
                            content = fp.read()
                        self._file_content_cache[cache_key] = content
                        break
                    except Exception:
                        pass

        if content is not None:
            return any(
                re.search(rf"\b{re.escape(sym)}\b", content) for sym in clean_symbols
            )
        return False

    # ------------------------------------------------------------------
    # Call Graph Resolution
    # ------------------------------------------------------------------

    def _resolve_callers(
        self,
        repo_name: str,
        seed_files: List[str],
        resolved_symbols: List[Any],
        evidence_items: List[EvidenceItem],
    ) -> Tuple[List[CallerInfo], List[CallerInfo]]:
        """Query call graph to find direct callers and transitive callers with exact paths."""
        direct_callers: List[CallerInfo] = []
        transitive_callers: List[CallerInfo] = []
        if not self.call_graph_service:
            return direct_callers, transitive_callers

        cg = self.call_graph_service.load_graph(repo_name)
        if cg is None or cg.number_of_nodes() == 0:
            return direct_callers, transitive_callers

        def _clean_path(fp: str) -> str:
            if "data/cloned_repos/" in fp:
                parts = fp.split("data/cloned_repos/", 1)[1].split("/", 1)
                if len(parts) > 1:
                    return parts[1]
            return fp

        # Prioritize specific function/method target nodes over broad class nodes
        has_fn = any(
            getattr(s, "type", "") in ("function", "method") for s in resolved_symbols
        )
        active_symbols = (
            [
                s
                for s in resolved_symbols
                if getattr(s, "type", "") in ("function", "method")
            ]
            if has_fn
            else resolved_symbols
        )

        # Find target node IDs in call graph corresponding strictly to resolved symbols
        target_nodes: Set[str] = set()
        for sym in active_symbols:
            s_name = getattr(sym, "name", str(sym))
            clean_s = s_name.split(".")[-1]
            s_file = getattr(sym, "file_path", "")
            clean_f = s_file.replace("\\", "/").split("/")[-1] if s_file else ""

            matched = False
            for n in cg.nodes():
                qual = n.split("::")[-1]
                node_type = cg.nodes.get(n, {}).get("symbol_type")
                if has_fn and node_type == "class":
                    continue
                if qual == s_name or qual == clean_s or qual.endswith(f".{clean_s}"):
                    if not clean_f or clean_f in n:
                        target_nodes.add(n)
                        matched = True

            if not matched:
                for n in cg.nodes():
                    qual = n.split("::")[-1]
                    node_type = cg.nodes.get(n, {}).get("symbol_type")
                    if has_fn and node_type == "class":
                        continue
                    if (
                        qual == s_name
                        or qual == clean_s
                        or qual.endswith(f".{clean_s}")
                    ):
                        target_nodes.add(n)

        visited_callers: Set[str] = set(target_nodes)
        seen_direct: Set[str] = set()
        seen_transitive: Set[str] = set()
        call_paths: Dict[str, List[str]] = {t: [t] for t in target_nodes}

        # Step 1: Direct callers (depth 1)
        depth1_nodes: Set[str] = set()
        for t_node in target_nodes:
            target_name = t_node.split("::")[-1]
            try:
                callers = list(cg.predecessors(t_node))
            except Exception:
                callers = []

            for c_node in callers:
                if c_node not in visited_callers:
                    visited_callers.add(c_node)
                    depth1_nodes.add(c_node)
                    c_file, c_qual = (
                        c_node.split("::", 1) if "::" in c_node else (c_node, c_node)
                    )
                    c_file = _clean_path(c_file)
                    node_attrs = cg.nodes.get(c_node, {})
                    line = node_attrs.get("line_number")
                    path = call_paths.get(t_node, [t_node]) + [c_node]
                    call_paths[c_node] = path

                    edge_data = cg.get_edge_data(c_node, t_node) or {}
                    rel = edge_data.get("relationship", "DIRECT_CALL")
                    rec_expr = edge_data.get("receiver_expr")
                    rec_type = edge_data.get("receiver_type")
                    conf = edge_data.get("confidence_tier", "HIGH")

                    if c_node not in seen_direct:
                        seen_direct.add(c_node)
                        info = CallerInfo(
                            caller_id=c_node,
                            caller_name=c_qual,
                            file_path=c_file,
                            line_number=line,
                            is_direct=True,
                            depth=1,
                            propagation_path=path,
                            relationship=rel,
                            receiver_expr=rec_expr,
                            receiver_type=rec_type,
                            confidence_tier=conf,
                        )
                        direct_callers.append(info)
                        line_ref = f"{c_file}:{line}" if line else c_file
                        evidence_items.append(
                            EvidenceItem(
                                kind=EvidenceKind.FACT
                                if conf == "HIGH"
                                else EvidenceKind.INFERENCE,
                                statement=f"Direct caller '{c_qual}' calls '{target_name}' via {rel} at {line_ref}.",
                                source_reference=line_ref,
                                confidence=100 if conf == "HIGH" else 80,
                            )
                        )

        # Step 2: Transitive callers (depth 2, 3, 4)
        current_layer = depth1_nodes
        for d in range(2, 5):
            next_layer: Set[str] = set()
            for curr in current_layer:
                try:
                    p_callers = list(cg.predecessors(curr))
                except Exception:
                    p_callers = []
                for p_node in p_callers:
                    if p_node not in visited_callers:
                        visited_callers.add(p_node)
                        next_layer.add(p_node)
                        p_file, p_qual = (
                            p_node.split("::", 1)
                            if "::" in p_node
                            else (p_node, p_node)
                        )
                        p_file = _clean_path(p_file)
                        node_attrs = cg.nodes.get(p_node, {})
                        line = node_attrs.get("line_number")
                        path = call_paths.get(curr, [curr]) + [p_node]
                        call_paths[p_node] = path

                        edge_data = cg.get_edge_data(p_node, curr) or {}
                        rel = edge_data.get("relationship", "DIRECT_CALL")
                        rec_expr = edge_data.get("receiver_expr")
                        rec_type = edge_data.get("receiver_type")
                        conf = edge_data.get("confidence_tier", "MEDIUM")

                        if p_node not in seen_transitive and p_node not in seen_direct:
                            seen_transitive.add(p_node)
                            info = CallerInfo(
                                caller_id=p_node,
                                caller_name=p_qual,
                                file_path=p_file,
                                line_number=line,
                                is_direct=False,
                                depth=d,
                                propagation_path=path,
                                relationship=rel,
                                receiver_expr=rec_expr,
                                receiver_type=rec_type,
                                confidence_tier=conf,
                            )
                            transitive_callers.append(info)
                            line_ref = f"{p_file}:{line}" if line else p_file
                            evidence_items.append(
                                EvidenceItem(
                                    kind=EvidenceKind.INFERENCE,
                                    statement=f"Transitive caller '{p_qual}' in {p_file} ({d} hops away) reaches target via {rel}.",
                                    source_reference=line_ref,
                                    confidence=max(90 - (d * 10), 70),
                                )
                            )
            current_layer = next_layer
            if not current_layer:
                break

        return direct_callers, transitive_callers

    # ------------------------------------------------------------------
    # API Surface Resolution
    # ------------------------------------------------------------------

    def _resolve_api_exposure(
        self,
        repo_name: str,
        seed_files: List[str],
        affected_symbols: List[str],
        direct_callers: List[CallerInfo],
        evidence_items: List[EvidenceItem],
    ) -> ApiExposureInfo:
        """Query APISurfaceService to determine exposed public routes and exported symbols."""
        if not self.api_surface_service:
            return ApiExposureInfo()

        if not hasattr(self, "_api_surface_cache"):
            self._api_surface_cache = {}
        surface = self._api_surface_cache.get(repo_name)
        if surface is None:
            surface = self.api_surface_service.load(repo_name)
            if surface is not None:
                self._api_surface_cache[repo_name] = surface

        if surface is None:
            return ApiExposureInfo()

        public_routes: List[str] = []
        internal_routes: List[str] = []
        exported_symbols: List[str] = []
        deprecated_interfaces: List[str] = []

        caller_names = {c.caller_name for c in direct_callers}
        caller_ids = {c.caller_id for c in direct_callers}
        clean_symbols = [s.split(".")[-1] for s in affected_symbols if s]

        if not hasattr(surface, "_api_index"):
            from collections import defaultdict

            route_syms = []
            syms_by_name = defaultdict(list)
            syms_by_file = defaultdict(list)
            for s in surface.symbols:
                if (s.api_kind.value == "route") or ("route" in s.name.lower()):
                    route_syms.append(s)
                syms_by_name[s.name].append(s)
                syms_by_file[s.file_path].append(s)
            surface._api_index = (route_syms, syms_by_name, syms_by_file)

        route_syms, syms_by_name, syms_by_file = surface._api_index

        seen_sym_ids = set()
        candidate_syms = []
        for s in route_syms:
            s_key = f"{s.file_path}::{s.qualified}"
            if s_key not in seen_sym_ids:
                seen_sym_ids.add(s_key)
                candidate_syms.append(s)
        for s_name in clean_symbols:
            for s in syms_by_name.get(s_name, []):
                s_key = f"{s.file_path}::{s.qualified}"
                if s_key not in seen_sym_ids:
                    seen_sym_ids.add(s_key)
                    candidate_syms.append(s)
        for sf in seed_files:
            for s in syms_by_file.get(sf, []):
                s_key = f"{s.file_path}::{s.qualified}"
                if s_key not in seen_sym_ids:
                    seen_sym_ids.add(s_key)
                    candidate_syms.append(s)
        for c in direct_callers:
            for s in syms_by_name.get(c.caller_name, []):
                s_key = f"{s.file_path}::{s.qualified}"
                if s_key not in seen_sym_ids:
                    seen_sym_ids.add(s_key)
                    candidate_syms.append(s)

        for sym in candidate_syms:
            is_route = (sym.api_kind.value == "route") or ("route" in sym.name.lower())

            # Direct relation: route handler calls or is the affected symbol
            is_direct_route = (
                sym.name in clean_symbols
                or sym.qualified in affected_symbols
                or sym.name in caller_names
                or any(sym.name in cid for cid in caller_ids)
            )

            # Transitive relation: route handler in a seed file
            is_seed_route = sym.file_path in seed_files and is_route

            if is_direct_route or is_seed_route:
                route_desc = (
                    " ".join(sym.decorators)
                    if sym.decorators
                    else sym.api_kind.value.upper()
                )
                route_str = (
                    f"{route_desc} {sym.qualified} ({sym.file_path}:{sym.line_number})"
                )
                if is_route:
                    if sym.visibility.value == "public":
                        public_routes.append(route_str)
                        evidence_items.append(
                            EvidenceItem(
                                kind=EvidenceKind.FACT
                                if is_direct_route
                                else EvidenceKind.INFERENCE,
                                statement=f"{'Directly' if is_direct_route else 'Transitively'} exposed public API route: {route_str}.",
                                source_reference=f"{sym.file_path}:{sym.line_number}",
                                confidence=100 if is_direct_route else 85,
                            )
                        )
                    else:
                        internal_routes.append(route_str)
                elif sym.visibility.value == "public":
                    exported_symbols.append(
                        f"{sym.name} ({sym.file_path}:{sym.line_number})"
                    )

                if sym.status.value == "deprecated":
                    deprecated_interfaces.append(f"{sym.name} ({sym.file_path})")

        return ApiExposureInfo(
            public_routes=sorted(set(public_routes))[:10],
            internal_routes=sorted(set(internal_routes))[:10],
            exported_symbols=sorted(set(exported_symbols))[:15],
            deprecated_interfaces=sorted(set(deprecated_interfaces))[:5],
        )

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Test Impact Resolution (Precision Engine v3)
    # ------------------------------------------------------------------

    @staticmethod
    def _is_test_file(fp: str) -> bool:
        """Check whether a path corresponds to a test file."""
        norm = fp.lower().replace("\\", "/")
        return (
            norm.startswith("tests/")
            or "/tests/" in norm
            or norm.startswith("test/")
            or "/test/" in norm
            or os.path.basename(norm).startswith("test_")
            or os.path.basename(norm).endswith("_test.py")
            or os.path.basename(norm).endswith(".test.ts")
            or os.path.basename(norm).endswith(".test.js")
        )

    def _resolve_repo_file_path(self, repo_name: str, file_path: str) -> Optional[str]:
        """Resolve the filesystem path of a file in the repository."""
        safe_name = repo_name.replace("/", "_")
        for base in ["data/cloned_repos", "."]:
            cand = os.path.join(base, safe_name, file_path)
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
            cand = os.path.join(
                base, safe_name.replace("VarshithReddy2006_", ""), file_path
            )
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
            cand = os.path.join(base, file_path)
            if os.path.exists(cand) and os.path.isfile(cand):
                return cand
        return None

    def _inspect_test_file_ast(
        self,
        repo_name: str,
        test_file: str,
        seed_files: List[str],
        target_symbols: List[str],
        api_routes: List[str],
    ) -> List[Dict[str, Any]]:
        """Inspect a test file's AST for direct calls, imports, aliases, and API routes."""
        evidence: List[Dict[str, Any]] = []
        p = self._resolve_repo_file_path(repo_name, test_file)
        if not p or not os.path.exists(p):
            return evidence

        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
        except Exception:
            return evidence

        targets = []
        for s in target_symbols:
            if "." in s:
                parts = s.split(".")
                targets.append((parts[-2], parts[-1]))
            else:
                targets.append((None, s))

        seed_mods = set()
        seed_packages = set()
        for sf in seed_files:
            mod = sf.replace("/", ".").replace("\\", ".")
            if mod.endswith(".py"):
                mod = mod[:-3]
            seed_mods.add(mod)
            if "." in mod:
                seed_packages.add(mod.rsplit(".", 1)[0])

        # Fast pre-filtering: skip test files that do not contain any candidate tokens
        candidate_tokens = set()
        for sf in seed_files:
            b = os.path.basename(sf)
            if b.endswith(".py"):
                candidate_tokens.add(b[:-3])
            mod_part = sf.replace("/", ".").replace("\\", ".")
            if mod_part.endswith(".py"):
                mod_part = mod_part[:-3]
            for part in mod_part.split("."):
                if len(part) >= 3:
                    candidate_tokens.add(part)
        for _, s in targets:
            if s:
                candidate_tokens.add(s)
        for r in api_routes:
            candidate_tokens.add(r)

        if candidate_tokens and not any(tok in content for tok in candidate_tokens):
            return evidence

        if p.endswith(".py"):
            if not hasattr(self, "_ast_cache"):
                self._ast_cache = {}
            mtime = os.path.getmtime(p)
            cached = self._ast_cache.get(p)
            if cached and cached[0] == mtime:
                tree = cached[1]
            else:
                try:
                    tree = ast.parse(content, filename=p)
                    self._ast_cache[p] = (mtime, tree)
                except Exception:
                    tree = None

            if tree:
                aliases: Dict[str, Tuple[Optional[str], str]] = {}

                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        mod = node.module or ""
                        is_seed_mod = mod in seed_mods
                        is_seed_pkg = mod in seed_packages

                        for n in node.names:
                            if is_seed_mod or is_seed_pkg:
                                for parent, sym in targets:
                                    if n.name == sym or (parent and n.name == parent):
                                        as_name = n.asname or n.name
                                        aliases[as_name] = (parent, sym)
                                        evidence.append(
                                            {
                                                "level": EvidenceStrength.LEVEL_2_EXACT_CALL.value,
                                                "tier": "HIGH",
                                                "score": 0.95,
                                                "line": node.lineno,
                                                "source_ref": f"{test_file}:{node.lineno}",
                                                "reason": f"Directly imports target symbol '{n.name}' from {mod} at line {node.lineno}.",
                                            }
                                        )

                                if not any(n.name == s for _, s in targets):
                                    import re

                                    snake_name = re.sub(
                                        r"(?<!^)(?=[A-Z])", "_", n.name
                                    ).lower()
                                    is_primary = any(
                                        sf.endswith(f"/{n.name.lower()}.py")
                                        or sf.endswith(f"/{n.name.lower()}_service.py")
                                        or sf.endswith(f"/{snake_name}.py")
                                        or sf.endswith(f"/{snake_name}_service.py")
                                        for sf in seed_files
                                    )
                                    evidence.append(
                                        {
                                            "level": EvidenceStrength.LEVEL_2_EXACT_CALL.value
                                            if is_primary
                                            else EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value,
                                            "tier": "HIGH" if is_primary else "MEDIUM",
                                            "score": 0.90 if is_primary else 0.75,
                                            "line": node.lineno,
                                            "source_ref": f"{test_file}:{node.lineno}",
                                            "reason": f"Imports {'primary' if is_primary else 'related'} symbol '{n.name}' from changed module/package {mod} at line {node.lineno}.",
                                        }
                                    )

                    elif isinstance(node, ast.Import):
                        for n in node.names:
                            if n.name in seed_mods or n.name in seed_packages:
                                as_name = n.asname or n.name
                                evidence.append(
                                    {
                                        "level": EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value,
                                        "tier": "MEDIUM",
                                        "score": 0.70,
                                        "line": node.lineno,
                                        "source_ref": f"{test_file}:{node.lineno}",
                                        "reason": f"Imports changed module '{n.name}' at line {node.lineno}.",
                                    }
                                )

                    elif isinstance(node, ast.Call):
                        call_repr = ""
                        if isinstance(node.func, ast.Name):
                            call_repr = node.func.id
                        elif isinstance(node.func, ast.Attribute):
                            try:
                                call_repr = ast.unparse(node.func)
                            except Exception:
                                call_repr = getattr(node.func, "attr", "")

                        for parent, sym in targets:
                            matched = False
                            if parent:
                                if call_repr.endswith(f".{sym}"):
                                    prefix = call_repr.rsplit(".", 1)[0].split(".")[-1]
                                    if (
                                        prefix.lower() == parent.lower()
                                        or prefix in aliases
                                        or (
                                            prefix in ("s", "self")
                                            and (
                                                is_seed_mod
                                                or is_seed_pkg
                                                or parent in aliases
                                            )
                                        )
                                    ):
                                        matched = True
                            else:
                                if call_repr == sym or call_repr in aliases:
                                    matched = True
                                elif call_repr.endswith(f".{sym}"):
                                    prefix = call_repr.rsplit(".", 1)[0].split(".")[-1]
                                    if (
                                        prefix in aliases
                                        or prefix in seed_mods
                                        or prefix in seed_packages
                                    ):
                                        matched = True

                            if matched:
                                evidence.append(
                                    {
                                        "level": EvidenceStrength.LEVEL_1_EXACT_SYMBOL.value,
                                        "tier": "HIGH",
                                        "score": 1.00,
                                        "line": node.lineno,
                                        "source_ref": f"{test_file}:{node.lineno}",
                                        "reason": f"Directly calls target symbol '{call_repr}' at line {node.lineno}.",
                                    }
                                )

                        if isinstance(node.func, ast.Attribute) and node.func.attr in (
                            "get",
                            "post",
                            "put",
                            "delete",
                            "patch",
                        ):
                            if (
                                node.args
                                and isinstance(node.args[0], ast.Constant)
                                and isinstance(node.args[0].value, str)
                            ):
                                url = node.args[0].value
                                for r in api_routes:
                                    clean_r = r.split()[0] if " " in r else r
                                    if clean_r == url or (
                                        len(clean_r) > 2 and url.startswith(clean_r)
                                    ):
                                        evidence.append(
                                            {
                                                "level": EvidenceStrength.LEVEL_4_API_CONTRACT.value,
                                                "tier": "HIGH",
                                                "score": 0.85,
                                                "line": node.lineno,
                                                "source_ref": f"{test_file}:{node.lineno}",
                                                "reason": f"Invokes affected API route '{url}' at line {node.lineno}.",
                                            }
                                        )

        return evidence

    def _resolve_test_impact(
        self,
        repo_name: str,
        graph: nx.DiGraph,
        seed_files: List[str],
        affected_symbols: List[str],
        resolved_symbols: List[Any],
        direct_callers: List[CallerInfo],
        transitive_callers: List[CallerInfo],
        api_exposure: Optional[ApiExposureInfo],
        evidence_items: List[EvidenceItem],
    ) -> List[TestImpactItem]:
        """Identify test files affected by structural connections, ranked by evidence strength."""
        cand_tests: Set[str] = set()
        for node in graph.nodes():
            if self._is_test_file(node) and not node.startswith(
                ("data/", ".venv/", "node_modules/", "frontend/dist/")
            ):
                cand_tests.add(node)

        for c in direct_callers:
            if self._is_test_file(c.file_path) and not c.file_path.startswith(
                ("data/", ".venv/", "node_modules/", "frontend/dist/")
            ):
                cand_tests.add(c.file_path)
        for tc in transitive_callers:
            if self._is_test_file(tc.file_path) and not tc.file_path.startswith(
                ("data/", ".venv/", "node_modules/", "frontend/dist/")
            ):
                cand_tests.add(tc.file_path)

        api_routes = [
            r.split()[0] for r in (api_exposure.public_routes if api_exposure else [])
        ]
        target_symbol_names: List[str] = []
        for s in resolved_symbols:
            p_class = getattr(s, "parent_class", None)
            s_name = getattr(s, "name", str(s))
            if p_class:
                target_symbol_names.append(f"{p_class}.{s_name}")
            else:
                target_symbol_names.append(s_name)
        if not target_symbol_names:
            target_symbol_names = affected_symbols

        file_evidence: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        file_propagation: Dict[str, List[str]] = {}

        # 1. Direct callers in call graph
        for c in direct_callers:
            if self._is_test_file(c.file_path):
                file_evidence[c.file_path].append(
                    {
                        "level": EvidenceStrength.LEVEL_1_EXACT_SYMBOL.value,
                        "tier": "HIGH",
                        "score": 1.00,
                        "source_ref": f"{c.file_path}:{c.line_number}"
                        if c.line_number
                        else c.file_path,
                        "reason": f"Directly calls changed code from '{c.caller_name}' at line {c.line_number or 'unknown'}.",
                    }
                )
                file_propagation[c.file_path] = c.propagation_path or (
                    [s for s in seed_files] + [c.file_path]
                )

        # 2. Transitive callers (helper chains)
        for tc in transitive_callers:
            if self._is_test_file(tc.file_path) and tc.depth <= 2:
                file_evidence[tc.file_path].append(
                    {
                        "level": EvidenceStrength.LEVEL_3_SYMBOL_DEPENDENCY.value,
                        "tier": "MEDIUM",
                        "score": 0.80,
                        "source_ref": f"{tc.file_path}:{tc.line_number}"
                        if tc.line_number
                        else tc.file_path,
                        "reason": f"Calls helper that reaches target via '{tc.caller_name}' ({tc.depth} hops away).",
                    }
                )
                if tc.file_path not in file_propagation:
                    file_propagation[tc.file_path] = tc.propagation_path or (
                        [s for s in seed_files] + [tc.file_path]
                    )

        # 3. Dedicated test file name match
        clean_syms = [s.split(".")[-1] for s in target_symbol_names if s]
        for sym in clean_syms:
            if len(sym) >= 4:
                sym_norm = sym.lower().replace("_", "")
                for cand in cand_tests:
                    base = (
                        os.path.splitext(os.path.basename(cand))[0]
                        .lower()
                        .replace("_", "")
                    )
                    if (
                        sym_norm == base
                        or base == f"test{sym_norm}"
                        or base.startswith(f"test{sym_norm}")
                    ):
                        file_evidence[cand].append(
                            {
                                "level": EvidenceStrength.LEVEL_1_EXACT_SYMBOL.value,
                                "tier": "HIGH",
                                "score": 0.95,
                                "source_ref": cand,
                                "reason": f"Dedicated test file specifically targeting symbol '{sym}'.",
                            }
                        )
                        if cand not in file_propagation:
                            file_propagation[cand] = [s for s in seed_files] + [cand]

        # 4. AST-based inspection (imports, calls, aliases, API routes)
        # Uses snapshot-aware in-memory TestImpactIndex to avoid repeated disk reads & AST parses
        try:
            from services.test_impact_index import TestImpactIndex

            test_index = TestImpactIndex.get_index(repo_name)
            test_index.path_resolver = lambda fp: self._resolve_repo_file_path(
                repo_name, fp
            )
            test_index.ensure_indexed(list(cand_tests))
            matched_tests = test_index.find_candidate_test_files(
                seed_files=seed_files,
                target_symbols=target_symbol_names,
                api_routes=api_routes,
            )
            for cand in matched_tests:
                ast_evs = test_index.inspect_test_facts(
                    test_file=cand,
                    seed_files=seed_files,
                    target_symbols=target_symbol_names,
                    api_routes=api_routes,
                )
                for ae in ast_evs:
                    file_evidence[cand].append(ae)
                    if cand not in file_propagation:
                        file_propagation[cand] = [s for s in seed_files] + [cand]
        except Exception as e:
            logger.warning(
                "TestImpactIndex failed, falling back to on-demand inspection: %s", e
            )
            for cand in cand_tests:
                ast_evs = self._inspect_test_file_ast(
                    repo_name=repo_name,
                    test_file=cand,
                    seed_files=seed_files,
                    target_symbols=target_symbol_names,
                    api_routes=api_routes,
                )
                for ae in ast_evs:
                    file_evidence[cand].append(ae)
                    if cand not in file_propagation:
                        file_propagation[cand] = [s for s in seed_files] + [cand]

        # 5. Direct module import from graph
        for seed in seed_files:
            if seed in graph:
                for pred in graph.predecessors(seed):
                    if self._is_test_file(pred):
                        file_evidence[pred].append(
                            {
                                "level": EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value,
                                "tier": "MEDIUM",
                                "score": 0.70,
                                "source_ref": pred,
                                "reason": f"Directly imports changed module '{seed}'.",
                            }
                        )
                        if pred not in file_propagation:
                            file_propagation[pred] = [seed, pred]

        # 6. Bounded heuristic candidate tests (module base name match, max 3)
        heuristic_count = 0
        for seed in seed_files:
            base = os.path.splitext(os.path.basename(seed))[0].lower().replace("_", "")
            if len(base) >= 4:
                for cand in cand_tests:
                    if cand not in file_evidence and heuristic_count < 3:
                        c_base = os.path.basename(cand).lower().replace("_", "")
                        if base in c_base:
                            file_evidence[cand].append(
                                {
                                    "level": EvidenceStrength.LEVEL_7_HEURISTIC.value,
                                    "tier": "LOW",
                                    "score": 0.25,
                                    "source_ref": cand,
                                    "reason": f"Test file name matches target module base '{base}'.",
                                }
                            )
                            file_propagation[cand] = [cand]
                            heuristic_count += 1

        # Deduplication & Evidence Aggregation
        test_items: List[TestImpactItem] = []
        for tf, ev_list in file_evidence.items():
            if not ev_list:
                continue

            # Pick strongest evidence
            best_score = max(e.get("score", 0.0) for e in ev_list)
            is_high = any(e.get("tier") == "HIGH" for e in ev_list)
            is_med = any(e.get("tier") == "MEDIUM" for e in ev_list)

            tier = "HIGH" if is_high else ("MEDIUM" if is_med else "LOW")
            impact_type = (
                "DIRECT TEST IMPACT"
                if is_high
                else ("LIKELY TEST IMPACT" if is_med else "HEURISTIC TEST CANDIDATE")
            )

            primary_ev = next(e for e in ev_list if e.get("score", 0.0) == best_score)
            reasons = list(dict.fromkeys(e.get("reason", "") for e in ev_list))
            combined_reason = "; ".join(reasons[:2])

            source_ref = next(
                (e.get("source_ref") for e in ev_list if e.get("source_ref")), tf
            )
            prop_path = file_propagation.get(tf, [s for s in seed_files] + [tf])

            test_item = TestImpactItem(
                test_file=tf,
                impact_type=impact_type,
                reason=combined_reason,
                confidence_tier=tier,
                evidence_strength=primary_ev.get(
                    "level", EvidenceStrength.LEVEL_5_TEST_RELATIONSHIP.value
                ),
                propagation_path=prop_path,
                source_reference=source_ref,
                evidence_paths=ev_list,
            )
            test_items.append(test_item)

            if is_high:
                evidence_items.append(
                    EvidenceItem(
                        kind=EvidenceKind.FACT,
                        statement=f"Direct test impact in '{tf}': {combined_reason}",
                        source_reference=source_ref,
                        confidence=100,
                    )
                )
            elif is_med:
                evidence_items.append(
                    EvidenceItem(
                        kind=EvidenceKind.INFERENCE,
                        statement=f"Likely test impact in '{tf}': {combined_reason}",
                        source_reference=source_ref,
                        confidence=80,
                    )
                )

        test_items.sort(
            key=lambda x: (
                0
                if x.confidence_tier == "HIGH"
                else (1 if x.confidence_tier == "MEDIUM" else 2),
                x.test_file,
            )
        )
        return test_items

    # ------------------------------------------------------------------
    # Architecture Boundaries
    # ------------------------------------------------------------------

    def _detect_boundaries(
        self,
        graph: nx.DiGraph,
        seed_files: List[str],
        all_affected: List[str],
    ) -> List[str]:
        """Detect cross-component boundaries between seed files and dependents."""
        transitions: Set[str] = set()
        seed_comps = {s: self._detect_components([s]) for s in seed_files}

        for node in all_affected:
            if node in seed_files:
                continue
            node_comps = self._detect_components([node])
            for seed in seed_files:
                if graph.has_edge(node, seed):
                    from_c = node_comps[0] if node_comps else "Unknown"
                    to_c = seed_comps[seed][0] if seed_comps[seed] else "Unknown"
                    if from_c != to_c:
                        transitions.add(f"{to_c} -> {from_c}")

        return sorted(transitions)

    # ------------------------------------------------------------------
    # Blast Radius & Deterministic Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_blast_radius(total_affected_files: int) -> str:
        """Classify blast radius into standard size buckets: XS, S, M, L, XL."""
        if total_affected_files <= 2:
            return "XS"
        elif total_affected_files <= 5:
            return "S"
        elif total_affected_files <= 12:
            return "M"
        elif total_affected_files <= 25:
            return "L"
        else:
            return "XL"

    @staticmethod
    def _compute_risk_deterministic(
        total_affected: int,
        direct_callers_count: int,
        public_routes_count: int,
        boundaries_count: int,
        all_affected: List[str],
        core_set: Set[str],
        coupling_set: Set[str],
        entry_set: Set[str],
        total_graph_nodes: int,
    ) -> Tuple[str, int]:
        """Compute risk level using deterministic, documented structural weights.

        Weights:
          - File count: >=15 -> +4, >=6 -> +2, >=3 -> +1
          - Direct callers: >=8 -> +3, >=3 -> +2, >=1 -> +1
          - Public routes exposed: >=4 -> +4, >=1 -> +2
          - Boundaries crossed: >=2 -> +2, >=1 -> +1
          - Core module hits: +2 each
          - Entry point hits: +2 each
        """
        score = 0

        # File volume
        if total_affected >= 15:
            score += 4
        elif total_affected >= 6:
            score += 2
        elif total_affected >= 3:
            score += 1

        # Callers
        if direct_callers_count >= 8:
            score += 3
        elif direct_callers_count >= 3:
            score += 2
        elif direct_callers_count >= 1:
            score += 1

        # Public routes
        if public_routes_count >= 4:
            score += 4
        elif public_routes_count >= 1:
            score += 2

        # Architecture transitions
        if boundaries_count >= 2:
            score += 2
        elif boundaries_count >= 1:
            score += 1

        # Centrality hits
        core_hits = sum(1 for f in all_affected if f in core_set)
        score += core_hits * 2

        coupling_hits = sum(1 for f in all_affected if f in coupling_set)
        score += min(coupling_hits, 3)

        if any(f in entry_set for f in all_affected):
            score += 2

        if score >= 10:
            risk_level = "extreme"
        elif score >= 6:
            risk_level = "high"
        elif score >= 3:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Confidence: higher when graph is populated and callers are traced
        base_confidence = 65
        bonus = min(total_affected * 2, 20) + min(direct_callers_count * 2, 10)
        confidence = min(base_confidence + bonus, 95) if total_graph_nodes > 0 else 20

        return risk_level, confidence

    # ------------------------------------------------------------------
    # Implementation Order Generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_implementation_order(
        seed_files: List[str],
        directly_affected: List[str],
        indirectly_affected: List[str],
        direct_callers: List[CallerInfo],
        api_exposure: Optional[ApiExposureInfo],
        affected_tests: List[TestImpactItem],
        evidence_items: List[EvidenceItem],
    ) -> List[str]:
        """Generate a dependency-ordered sequence of changes."""
        steps: List[str] = []

        # Step 1: Base definitions in seed files
        if seed_files:
            steps.append(
                f"1. Core Implementation: Modify target symbol / definition in {', '.join(seed_files[:2])}."
            )

        # Step 2: Internal dependencies
        internal_deps = [
            f
            for f in directly_affected
            if f not in seed_files and "test" not in f.lower()
        ][:3]
        if internal_deps:
            steps.append(
                f"2. Internal Subsystems: Update dependent services in {', '.join(internal_deps)}."
            )

        # Step 3: Direct callers
        if direct_callers:
            caller_summary = ", ".join(
                f"'{c.caller_name}' in {c.file_path}" for c in direct_callers[:3]
            )
            steps.append(f"3. Caller Updates: Adapt call sites in {caller_summary}.")

        # Step 4: Public API routes
        if api_exposure and api_exposure.public_routes:
            steps.append(
                f"4. API Contract: Validate and adjust exposed endpoints ({len(api_exposure.public_routes)} public routes)."
            )

        # Step 5: Test suites
        if affected_tests:
            test_files = [t.test_file for t in affected_tests[:3]]
            steps.append(
                f"5. Test Verification: Run and update regression tests in {', '.join(test_files)}."
            )

        if not steps:
            steps = [
                "1. Inspect target files.",
                "2. Update implementation.",
                "3. Run test suite.",
            ]

        evidence_items.append(
            EvidenceItem(
                kind=EvidenceKind.RECOMMENDATION,
                statement=f"Follow dependency-ordered implementation plan starting from base definitions ({len(steps)} phases).",
                source_reference=None,
                confidence=95,
            )
        )
        return steps

    # ------------------------------------------------------------------
    # Keyword extraction & File matching (preserved from existing implementation)
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_keywords(text: str) -> List[str]:
        """Extract meaningful keywords from the issue text."""
        _STOP = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "to",
            "of",
            "and",
            "or",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "this",
            "that",
            "it",
            "its",
            "we",
            "our",
            "add",
            "fix",
            "bug",
            "issue",
            "feature",
            "update",
            "change",
            "when",
            "how",
            "what",
            "which",
            "where",
            "who",
            "can",
            "will",
            "should",
            "need",
            "needs",
            "want",
            "wants",
            "make",
            "use",
            "into",
            "also",
            "just",
            "not",
            "have",
            "has",
            "but",
            "so",
        }
        raw = re.sub(r"[^a-zA-Z0-9_\-/]", " ", text.lower())
        tokens = [t for t in raw.split() if len(t) >= 4 and t not in _STOP]
        seen: Set[str] = set()
        result = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                result.append(t)
        return sorted(result, key=len, reverse=True)[:20]

    def _match_files_to_keywords(
        self,
        graph: nx.DiGraph,
        keywords: List[str],
        full_text: str,
    ) -> List[str]:
        """Match graph nodes (file paths) against issue keywords."""
        all_files = list(graph.nodes())
        scored: Dict[str, int] = {}

        for fp in all_files:
            fp_norm = fp.lower().replace("\\", "/").replace("_", "-").replace(".", "-")
            base = os.path.splitext(os.path.basename(fp))[0].lower().replace("_", "-")
            score = 0
            for kw in keywords:
                kw_norm = kw.replace("_", "-").replace(".", "-")
                if kw_norm in fp_norm:
                    score += len(kw)
                elif len(base) >= 4 and base in kw_norm:
                    score += len(base)
            if score > 0:
                scored[fp] = score

        for kw in keywords:
            for fp in all_files:
                parts = fp.replace("\\", "/").split("/")
                if any(kw in p.lower() for p in parts):
                    scored[fp] = scored.get(fp, 0) + len(kw) // 2

        sorted_files = sorted(scored.items(), key=lambda x: x[1], reverse=True)
        seeds = [fp for fp, _ in sorted_files[:10]]
        return seeds

    # ------------------------------------------------------------------
    # Graph traversal & Path building
    # ------------------------------------------------------------------

    @staticmethod
    def _bfs(
        graph: nx.DiGraph,
        start: str,
        direction: str,
        depth: int,
    ) -> Set[str]:
        if start not in graph:
            return set()

        visited: Set[str] = set()
        queue = [(start, 0)]

        while queue:
            node, d = queue.pop(0)
            if d >= depth:
                continue
            if direction == "forward":
                neighbours = list(graph.successors(node))
            else:
                neighbours = list(graph.predecessors(node))

            for nb in neighbours:
                if nb not in visited and nb != start:
                    visited.add(nb)
                    queue.append((nb, d + 1))

        return visited

    def _build_dependency_paths(
        self,
        graph: nx.DiGraph,
        seeds: List[str],
        reverse_affected: Set[str],
        max_paths: int,
    ) -> List[DependencyPath]:
        paths: List[DependencyPath] = []
        for seed in seeds[:max_paths]:
            for target in list(reverse_affected)[:max_paths]:
                try:
                    chain = nx.shortest_path(graph, source=target, target=seed)
                    if len(chain) >= 2:
                        paths.append(DependencyPath(path=chain))
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
                if len(paths) >= max_paths:
                    break
            if len(paths) >= max_paths:
                break

        seen_chains: Set[str] = set()
        unique: List[DependencyPath] = []
        for dp in paths:
            key = "->".join(dp.path)
            if key not in seen_chains:
                seen_chains.add(key)
                unique.append(dp)

        return unique[:max_paths]

    @staticmethod
    def _detect_components(file_paths: List[str]) -> List[str]:
        found: Set[str] = set()
        for fp in file_paths:
            text = fp.lower()
            for pattern, label in _COMPONENT_MAP:
                if pattern.search(text):
                    found.add(label)
        return sorted(found)
