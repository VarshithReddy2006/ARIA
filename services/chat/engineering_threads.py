"""Engineering Threads & Progressive Investigation Tracking — Phase 12.

Tracks active, resolved, and unresolved engineering threads across conversation turns.
Enables progressive technical exploration from architecture down to symbols and risk validation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InvestigationDepth(int, Enum):
    """Progressive exploration depth ladder."""

    SYSTEM_OVERVIEW = 1  # Purpose, high-level architecture
    SUBSYSTEM_FLOW = 2  # Pipeline, API request flow, data flow
    COMPONENT_MODULE = 3  # Specific module, file responsibility
    SYMBOL_LOGIC = 4  # Functions, classes, data transformations
    CALLER_DEPENDENCY = 5  # Call graph, consumers, upstream/downstream
    CHANGE_IMPACT = 6  # Blast radius, schema changes, risks
    SAFE_IMPLEMENTATION = 7  # Step-by-step refactoring, mitigation
    TEST_VALIDATION = 8  # Unit tests, fixtures, integration verification


class ThreadStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


@dataclass
class ConversationEntity:
    """A concrete entity identified and tracked in conversation."""

    name: str
    entity_type: str  # "file", "symbol", "endpoint", "artifact", "dependency"
    first_seen_turn: int = 1
    last_seen_turn: int = 1
    relevance_score: float = 1.0


@dataclass
class EngineeringThread:
    """An ongoing or resolved engineering investigation thread."""

    thread_id: str
    title: str
    entities: List[str] = field(default_factory=list)
    status: ThreadStatus = ThreadStatus.ACTIVE
    depth: InvestigationDepth = InvestigationDepth.SYSTEM_OVERVIEW
    resolved_aspects: List[str] = field(default_factory=list)
    unresolved_aspects: List[str] = field(default_factory=list)
    last_updated_turn: int = 1


@dataclass
class EngineeringRelationship:
    """A confirmed relationship between two entities."""

    source: str
    relation: str  # "imports", "calls", "loads_artifact", "routes_to", "depends_on"
    target: str
    confidence: str = "VERIFIED"  # "VERIFIED", "STRONGLY INFERRED", "INFERRED"
    evidence: str = ""


@dataclass
class EngineeringInvestigationState:
    """Persistent structured state of the engineering investigation."""

    repo_name: str
    current_turn: int
    current_depth: InvestigationDepth
    previous_depth: InvestigationDepth
    active_thread_id: str
    active_thread_title: str
    focus_entity: Optional[str]
    known_facts: Dict[str, List[str]] = field(default_factory=dict)
    confirmed_relationships: List[EngineeringRelationship] = field(default_factory=list)
    discovery_delta: List[str] = field(default_factory=list)
    unresolved_questions: List[str] = field(default_factory=list)
    engineering_risks: List[str] = field(default_factory=list)
    next_recommended_depth: InvestigationDepth = InvestigationDepth.SUBSYSTEM_FLOW


class EngineeringThreadTracker:
    """Maintains active, resolved, and unresolved engineering threads for a session."""

    def __init__(self, repo_name: str) -> None:
        self.repo_name = repo_name
        self.current_turn = 0
        self.active_threads: Dict[str, EngineeringThread] = {}
        self.discovered_entities: Dict[str, ConversationEntity] = {}
        self.current_focus_entity: Optional[str] = None
        self.current_depth: InvestigationDepth = InvestigationDepth.SYSTEM_OVERVIEW
        self.previous_depth: InvestigationDepth = InvestigationDepth.SYSTEM_OVERVIEW
        self.confirmed_relationships: List[EngineeringRelationship] = []
        self.identified_risks: List[str] = []
        self.latest_discovery_delta: List[str] = []

    def record_turn(
        self,
        question: str,
        answer: str,
        extracted_files: List[str],
        extracted_symbols: List[str],
        extracted_endpoints: List[str],
        intent_name: Optional[str] = None,
    ) -> EngineeringInvestigationState:
        """Update active threads and entity history after a question/answer turn."""
        self.current_turn += 1
        turn = self.current_turn
        self.previous_depth = self.current_depth

        # Calculate discovery delta (entities seen for the first time)
        turn_entities = extracted_files + extracted_symbols + extracted_endpoints
        for art in re.findall(
            r"[\w\-\./]+\.(?:pkl|onnx|h5|pt|joblib|weights|csv|yaml|json)",
            answer + " " + question,
            re.I,
        ):
            turn_entities.append(art)

        delta = [e for e in turn_entities if e not in self.discovered_entities]
        self.latest_discovery_delta = delta

        # Record all entities
        for f in extracted_files:
            self._register_entity(f, "file", turn)
        for s in extracted_symbols:
            self._register_entity(s, "symbol", turn)
        for ep in extracted_endpoints:
            self._register_entity(ep, "endpoint", turn)

        # Artifacts regex (.pkl, .onnx, .h5, .pt, .json, .csv, .yaml)
        for art in re.findall(
            r"[\w\-\./]+\.(?:pkl|onnx|h5|pt|joblib|weights|csv|yaml|json)",
            answer + " " + question,
            re.I,
        ):
            self._register_entity(art, "artifact", turn)

        # Derive depth based on question intent and contents
        self.current_depth = self._calculate_depth(question, intent_name, turn)

        # Determine/update active thread
        thread_id = self._determine_thread_id(question, answer, extracted_files)
        if thread_id not in self.active_threads:
            self.active_threads[thread_id] = EngineeringThread(
                thread_id=thread_id,
                title=self._format_thread_title(thread_id),
                entities=[],
                status=ThreadStatus.ACTIVE,
                depth=self.current_depth,
                resolved_aspects=[],
                unresolved_aspects=[],
                last_updated_turn=turn,
            )

        thread = self.active_threads[thread_id]
        thread.last_updated_turn = turn
        thread.depth = max(thread.depth, self.current_depth)
        for e in extracted_files + extracted_symbols + extracted_endpoints:
            if e not in thread.entities:
                thread.entities.append(e)

        # Extract relationships and risks from answer
        self._extract_relationships_and_risks(
            question, answer, extracted_files, extracted_symbols
        )

        # Update resolved vs unresolved aspects
        self._update_aspects(
            thread, question, answer, extracted_files, extracted_symbols
        )

        return self.get_investigation_state(thread_id)

    def _extract_relationships_and_risks(
        self,
        question: str,
        answer: str,
        files: List[str],
        symbols: List[str],
    ) -> None:
        a_lower = answer.lower()

        # Extract relationships between files
        if len(files) >= 2:
            rel = EngineeringRelationship(
                source=files[0],
                relation="interacts_with",
                target=files[1],
                confidence="VERIFIED",
                evidence=f"{files[0]} and {files[1]} referenced together",
            )
            if not any(
                r.source == rel.source and r.target == rel.target
                for r in self.confirmed_relationships
            ):
                self.confirmed_relationships.append(rel)

        # Artifact loader relationship
        for art in re.findall(r"[\w\-\./]+\.(?:pkl|onnx|h5|pt|joblib)", answer, re.I):
            loader_f = files[0] if files else "the codebase"
            rel = EngineeringRelationship(
                source=loader_f,
                relation="loads_artifact",
                target=art,
                confidence="VERIFIED",
                evidence=f"{loader_f} loads model artifact {art}",
            )
            if not any(r.target == art for r in self.confirmed_relationships):
                self.confirmed_relationships.append(rel)

        # Risks identification
        if any(
            w in a_lower
            for w in ["tightly coupled", "high coupling", "central dependency"]
        ):
            risk = "High architectural coupling around central module"
            if risk not in self.identified_risks:
                self.identified_risks.append(risk)
        if any(
            w in a_lower for w in ["unvalidated", "missing validation", "schema drift"]
        ):
            risk = "Potential schema drift or unvalidated input vectors"
            if risk not in self.identified_risks:
                self.identified_risks.append(risk)
        if any(
            w in a_lower for w in ["blast radius", "break callers", "breaking change"]
        ):
            risk = "Broad blast radius on function signature modification"
            if risk not in self.identified_risks:
                self.identified_risks.append(risk)

    def disambiguate_reference(
        self,
        reference: str,
        candidates: List[str],
    ) -> Dict[str, Any]:
        """Disambiguate natural language references or return explicit ambiguity."""
        ref_clean = reference.lower().strip()
        matching = [c for c in candidates if ref_clean in c.lower()]

        if len(matching) == 1:
            return {"ambiguous": False, "selected": matching[0], "candidates": matching}
        elif len(matching) > 1:
            return {
                "ambiguous": True,
                "selected": None,
                "candidates": matching,
                "message": f"Multiple entities match '{reference}': {', '.join(matching)}. Please specify which entity to inspect.",
            }

        # Fallback to current focus entity if valid
        if self.current_focus_entity and self.current_focus_entity in candidates:
            return {
                "ambiguous": False,
                "selected": self.current_focus_entity,
                "candidates": [self.current_focus_entity],
            }

        return {
            "ambiguous": False,
            "selected": candidates[0] if candidates else None,
            "candidates": candidates,
        }

    def get_investigation_state(
        self, active_thread_id: Optional[str] = None
    ) -> EngineeringInvestigationState:
        """Construct a complete EngineeringInvestigationState snapshot."""
        tid = active_thread_id or next(
            iter(self.active_threads), "general_investigation"
        )
        title = (
            self.active_threads[tid].title
            if tid in self.active_threads
            else "General Codebase Investigation"
        )

        next_depth_val = min(self.current_depth.value + 1, 8)
        next_depth = InvestigationDepth(next_depth_val)

        known_facts = {
            "files": [
                e.name
                for e in self.discovered_entities.values()
                if e.entity_type == "file"
            ],
            "symbols": [
                e.name
                for e in self.discovered_entities.values()
                if e.entity_type == "symbol"
            ],
            "endpoints": [
                e.name
                for e in self.discovered_entities.values()
                if e.entity_type == "endpoint"
            ],
            "artifacts": [
                e.name
                for e in self.discovered_entities.values()
                if e.entity_type == "artifact"
            ],
        }

        return EngineeringInvestigationState(
            repo_name=self.repo_name,
            current_turn=self.current_turn,
            current_depth=self.current_depth,
            previous_depth=self.previous_depth,
            active_thread_id=tid,
            active_thread_title=title,
            focus_entity=self.current_focus_entity,
            known_facts=known_facts,
            confirmed_relationships=list(self.confirmed_relationships),
            discovery_delta=list(self.latest_discovery_delta),
            unresolved_questions=self.get_unresolved_aspects(),
            engineering_risks=list(self.identified_risks),
            next_recommended_depth=next_depth,
        )

    def get_unresolved_aspects(self) -> List[str]:
        """Return highest-priority unresolved aspects across active threads."""
        unresolved: List[str] = []
        for thread in self.active_threads.values():
            if thread.status == ThreadStatus.ACTIVE:
                for aspect in thread.unresolved_aspects:
                    if aspect not in unresolved:
                        unresolved.append(aspect)
        return unresolved

    def get_recent_entities(self, limit: int = 5) -> List[ConversationEntity]:
        """Return most recently active entities sorted by turn and relevance."""
        entities = sorted(
            self.discovered_entities.values(),
            key=lambda e: (e.last_seen_turn, e.relevance_score),
            reverse=True,
        )
        return entities[:limit]

    def _register_entity(self, name: str, entity_type: str, turn: int) -> None:
        if not name or len(name) < 2:
            return
        if name in self.discovered_entities:
            ent = self.discovered_entities[name]
            ent.last_seen_turn = turn
            ent.relevance_score += 1.0
        else:
            self.discovered_entities[name] = ConversationEntity(
                name=name,
                entity_type=entity_type,
                first_seen_turn=turn,
                last_seen_turn=turn,
                relevance_score=1.0,
            )
        self.current_focus_entity = name

    def _calculate_depth(
        self, question: str, intent_name: Optional[str], turn: int
    ) -> InvestigationDepth:
        q = question.lower()
        intent = (intent_name or "").upper()

        if intent in ("TESTING",) or any(
            k in q for k in ["test", "pytest", "mock", "assert", "fixture", "verify"]
        ):
            return InvestigationDepth.TEST_VALIDATION

        if any(
            k in q
            for k in [
                "safe modify",
                "how to change",
                "refactor safely",
                "implement safely",
                "migration",
                "safest implementation",
            ]
        ):
            return InvestigationDepth.SAFE_IMPLEMENTATION

        if intent in ("CHANGE_PLANNING", "IMPACT_ANALYSIS") or any(
            k in q
            for k in [
                "what would break",
                "blast radius",
                "impact",
                "break if",
                "change that schema",
                "change its output",
            ]
        ):
            return InvestigationDepth.CHANGE_IMPACT

        if any(
            k in q
            for k in [
                "where is",
                "who calls",
                "callers",
                "depend on that output",
                "used by",
                "who depends",
            ]
        ):
            return InvestigationDepth.CALLER_DEPENDENCY

        if (
            intent in ("API_FLOW", "API")
            or any(
                k in q
                for k in [
                    "pipeline",
                    "flow",
                    "request",
                    "route",
                    "inference path",
                    "/predict",
                ]
            )
            or re.search(r"/\w+", q)
        ):
            return InvestigationDepth.SUBSYSTEM_FLOW

        if any(
            k in q
            for k in [
                "what does",
                "inside",
                "function",
                "how does",
                "transform",
                "generate_df",
            ]
        ):
            if (
                "file" in q
                or ".py" in q
                or ".js" in q
                or ".ts" in q
                or "entry point" in q
            ):
                return InvestigationDepth.COMPONENT_MODULE
            return InvestigationDepth.SYMBOL_LOGIC

        if intent in ("OVERVIEW", "ARCHITECTURE") or "repository do" in q:
            return InvestigationDepth.SYSTEM_OVERVIEW

        # Default progression by turn count if exploratory
        depth_val = min(turn, 8)
        return InvestigationDepth(depth_val)

    def _determine_thread_id(self, question: str, answer: str, files: List[str]) -> str:
        q = question.lower()
        if any(
            k in q for k in ["inference", "predict", "model", "feature", "phishing"]
        ):
            return "ml_inference_pipeline"
        if any(
            k in q for k in ["api", "route", "endpoint", "fastapi", "flask", "server"]
        ):
            return "api_request_routing"
        if any(
            k in q for k in ["health", "cycle", "dead code", "dependency", "circular"]
        ):
            return "architecture_health"
        if files:
            clean_file = re.sub(r"[^\w\-_]", "_", files[0].lower())
            return f"module_{clean_file}"
        return "general_codebase_investigation"

    def _format_thread_title(self, thread_id: str) -> str:
        return thread_id.replace("_", " ").title()

    def _update_aspects(
        self,
        thread: EngineeringThread,
        question: str,
        answer: str,
        files: List[str],
        symbols: List[str],
    ) -> None:
        q = question.lower()

        # ML inference thread aspects
        if thread.thread_id == "ml_inference_pipeline":
            if "predict" in q or "pipeline" in q:
                if "api_entry_point" not in thread.resolved_aspects:
                    thread.resolved_aspects.append("api_entry_point")
            if "feature" in q or "extract" in q:
                if "feature_extraction" not in thread.resolved_aspects:
                    thread.resolved_aspects.append("feature_extraction")
            if "call" in q or "where is" in q:
                if "caller_dependencies" not in thread.resolved_aspects:
                    thread.resolved_aspects.append("caller_dependencies")
            if "break" in q or "impact" in q:
                if "change_blast_radius" not in thread.resolved_aspects:
                    thread.resolved_aspects.append("change_blast_radius")

            # Seed potential unresolved aspects
            candidates = [
                (
                    "model_artifact_lifecycle",
                    "how the model artifact (.pkl/.onnx) is loaded, versioned, or trained",
                ),
                (
                    "feature_vector_schema",
                    "exact feature vector shape and validation in feature extraction",
                ),
                (
                    "caller_contract_propagation",
                    "upstream and downstream callers depending on transformation output",
                ),
                (
                    "failure_handling_and_fallback",
                    "exception handling when input is malformed or model missing",
                ),
                (
                    "unit_test_and_mock_coverage",
                    "test coverage and fixtures for inference verification",
                ),
            ]
            for key, desc in candidates:
                if (
                    key not in thread.resolved_aspects
                    and desc not in thread.unresolved_aspects
                ):
                    thread.unresolved_aspects.append(desc)

        # General file / module aspects
        elif files:
            main_file = files[0]
            if main_file not in thread.resolved_aspects:
                thread.resolved_aspects.append(main_file)
            unres = f"Caller dependencies and error edge cases in {main_file}"
            if unres not in thread.unresolved_aspects:
                thread.unresolved_aspects.append(unres)
