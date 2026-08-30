"""Response Schema & Engineering Output Formatting — Phase 12.

Defines intent-aware dynamic answer schemas, direct answer-first contracts,
and strict anti-hallucination instructions for ARIA Repository Engineering Copilot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ResponseIntent(str, Enum):
    """Supported intent categories for dynamic schema generation."""

    ARCHITECTURE = "ARCHITECTURE"
    API = "API"
    API_FLOW = "API_FLOW"
    API_SURFACE = "API_SURFACE"
    FILE = "FILE"
    FILE_EXPLANATION = "FILE_EXPLANATION"
    SYMBOL = "SYMBOL"
    SYMBOL_EXPLANATION = "SYMBOL_EXPLANATION"
    DEPENDENCY = "DEPENDENCY"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    CALL_GRAPH = "CALL_GRAPH"
    DEBUGGING = "DEBUGGING"
    CHANGE_PLANNING = "CHANGE_PLANNING"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    READING_ORDER = "READING_ORDER"
    READING_PATH = "READING_PATH"
    HEALTH = "HEALTH"
    DEAD_CODE = "DEAD_CODE"
    SECURITY = "SECURITY"
    GIT_HISTORY = "GIT_HISTORY"
    PR_RISK = "PR_RISK"
    GENERAL_QA = "GENERAL_QA"


@dataclass(frozen=True)
class IntentSchemaDefinition:
    intent: str
    heading: str
    sections: List[str]
    description: str
    guidance: str


_SCHEMA_REGISTRY: dict[str, IntentSchemaDefinition] = {
    "ARCHITECTURE": IntentSchemaDefinition(
        intent="ARCHITECTURE",
        heading="## Response Format (Architecture & System Design)",
        sections=[
            "### Answer",
            "### Architecture Model",
            "### Major Components",
            "### Dependency Flow",
            "### Runtime Flow",
            "### Architectural Strengths",
            "### Risks / Coupling",
            "### Evidence",
            "### Next Investigation",
        ],
        description="Explains high-level system topology, layers, component boundaries, and runtime execution models.",
        guidance="Start with a direct 1-2 sentence architectural summary. Cite exact component boundaries and coupling risks.",
    ),
    "API": IntentSchemaDefinition(
        intent="API",
        heading="## Response Format (API & Request Flow)",
        sections=[
            "### Answer",
            "### Endpoint",
            "### Request Flow",
            "### Input Contract",
            "### Processing Path",
            "### Response",
            "### Failure Points",
            "### Relevant Files",
            "### Evidence",
            "### Next Investigation",
        ],
        description="Traces HTTP endpoints, request payloads, handler controllers, computational helpers, and response formats.",
        guidance="State the exact route, method, and handling sequence immediately. Identify payload validation and potential error states.",
    ),
    "FILE": IntentSchemaDefinition(
        intent="FILE",
        heading="## Response Format (File & Module Breakdown)",
        sections=[
            "### Answer",
            "### File Role",
            "### Responsibilities",
            "### Inputs",
            "### Outputs",
            "### Dependencies",
            "### Used By",
            "### Important Symbols",
            "### Why It Matters",
            "### Evidence",
            "### Next Investigation",
        ],
        description="Breaks down a specific file or module: purpose, functions, imports, callers, and system significance.",
        guidance="Immediately state what this file does in the repository architecture. List concrete functions and caller modules.",
    ),
    "DEPENDENCY": IntentSchemaDefinition(
        intent="DEPENDENCY",
        heading="## Response Format (Dependency & Coupling Analysis)",
        sections=[
            "### Answer",
            "### Dependency Role",
            "### Where Used",
            "### Dependency Chain",
            "### Centrality",
            "### Runtime Importance",
            "### Risks",
            "### Evidence",
            "### Next Investigation",
        ],
        description="Analyzes package or module dependencies, import cycles, fan-in/fan-out centrality, and upgrade risks.",
        guidance="Identify importing files, transitive dependencies, and potential coupling bottlenecks.",
    ),
    "DEBUGGING": IntentSchemaDefinition(
        intent="DEBUGGING",
        heading="## Response Format (Debugging & Root Cause)",
        sections=[
            "### Answer",
            "### Likely Root Cause",
            "### Execution Path",
            "### Failure Boundary",
            "### Supporting Evidence",
            "### Alternative Causes",
            "### Files To Inspect",
            "### Recommended Debugging Sequence",
        ],
        description="Traces runtime errors, exception boundaries, unhandled edge cases, and provides systematic debugging steps.",
        guidance="Hypothesize the root cause immediately based on available code. Provide concrete line numbers and files to inspect.",
    ),
    "CHANGE_PLANNING": IntentSchemaDefinition(
        intent="CHANGE_PLANNING",
        heading="## Response Format (Change Planning & Blast Radius)",
        sections=[
            "### Answer",
            "### Proposed Change",
            "### Directly Affected Files",
            "### Indirectly Affected Files",
            "### Dependency Impact",
            "### Call Impact",
            "### Blast Radius",
            "### Risk",
            "### Safe Implementation Order",
            "### Validation Plan",
        ],
        description="Evaluates modifying, refactoring, or introducing functionality, calculating ripple effects and safe step-by-step edit order.",
        guidance="Summarize the implementation plan directly. Distinguish direct edits from indirect consumers in the blast radius.",
    ),
    "READING_ORDER": IntentSchemaDefinition(
        intent="READING_ORDER",
        heading="## Response Format (Reading Path & Onboarding)",
        sections=[
            "### Answer",
            "### Entry Point",
            "### Recommended Sequence",
            "### Key Subsystems",
            "### Evidence",
            "### Next Investigation",
        ],
        description="Guides a developer on what to read first, in what sequence, and why.",
        guidance="Provide the exact starting file and ordered reading progression with concise rationale for each step.",
    ),
    "HEALTH": IntentSchemaDefinition(
        intent="HEALTH",
        heading="## Response Format (Repository Health & Quality Findings)",
        sections=[
            "### Answer",
            "### Findings Summary",
            "### High-Risk Areas",
            "### Structural Metrics",
            "### Evidence",
            "### Remediation Plan",
            "### Next Investigation",
        ],
        description="Summarizes health score, dead code, architectural cycles, test gaps, and maintenance risks.",
        guidance="Highlight actionable technical debt and concrete files requiring refactoring or test coverage.",
    ),
    "GENERAL_QA": IntentSchemaDefinition(
        intent="GENERAL_QA",
        heading="## Response Format",
        sections=[
            "### Answer",
            "### Explanation",
            "### Key Components",
            "### Evidence",
            "### Next Investigation",
        ],
        description="Default structured response format for general repository questions.",
        guidance="Answer the question directly in the first paragraph. Support claims with concrete file and symbol citations.",
    ),
}


class ResponseSchemaBuilder:
    """Builds dynamic response schemas and system instructions."""

    @staticmethod
    def normalize_intent(intent_name: Optional[str]) -> str:
        raw = (intent_name or "GENERAL_QA").strip().upper()
        if raw in ("API_FLOW", "API_SURFACE", "API"):
            return "API"
        if raw in ("ARCHITECTURE", "OVERVIEW"):
            return "ARCHITECTURE"
        if raw in (
            "FILE_EXPLANATION",
            "FILE",
            "SYMBOL",
            "SYMBOL_EXPLANATION",
            "CALL_GRAPH",
        ):
            return "FILE" if raw in ("FILE_EXPLANATION", "FILE") else "FILE"
        if raw in ("DEPENDENCY", "CIRCULAR_DEPENDENCY"):
            return "DEPENDENCY"
        if raw in ("DEBUGGING",):
            return "DEBUGGING"
        if raw in ("CHANGE_PLANNING", "IMPACT_ANALYSIS"):
            return "CHANGE_PLANNING"
        if raw in ("READING_ORDER", "READING_PATH"):
            return "READING_ORDER"
        if raw in ("HEALTH", "DEAD_CODE", "SECURITY", "GIT_HISTORY", "PR_RISK"):
            return "HEALTH"
        return "GENERAL_QA"

    @classmethod
    def get_schema_definition(
        cls, intent_name: Optional[str]
    ) -> IntentSchemaDefinition:
        key = cls.normalize_intent(intent_name)
        return _SCHEMA_REGISTRY.get(key, _SCHEMA_REGISTRY["GENERAL_QA"])

    @classmethod
    def build_format_prompt(cls, intent_name: Optional[str]) -> str:
        schema = cls.get_schema_definition(intent_name)
        sections_str = "\n".join(schema.sections)

        return (
            f"{schema.heading}\n"
            f"{schema.guidance}\n\n"
            f"Structure your response with these markdown sections (omit any section if no evidence exists for it):\n"
            f"{sections_str}\n\n"
            "ENGINEERING RULES:\n"
            "1. First Paragraph: Answer the user's question directly and immediately with repository facts. Avoid filler openings.\n"
            "2. Evidence Format: **File:** `path`, **Lines:** X–Y, **Role:** description. Never dump large raw code blocks; show at most 3–10 lines if excerpting.\n"
            "3. Grounding Levels: Distinguish [VERIFIED], [STRONGLY INFERRED], [INFERRED], and [UNKNOWN].\n"
            "4. Next Investigation: Conclude with a concrete next investigation into an unresolved file, symbol, or pipeline aspect."
        )

    @staticmethod
    def build_system_instruction(repo_name: str) -> str:
        return (
            f"You are ARIA — an AI-Powered Repository Engineering Copilot (Principal Engineer-level assistant) "
            f"specialising in the `{repo_name}` codebase.\n\n"
            "CORE PRINCIPLES:\n"
            "1. Grounded Answers: Answer ONLY using the repository intelligence context provided. Do NOT invent files, functions, endpoints, dependencies, workflows, architecture relationships, metrics, or behaviors.\n"
            "2. Directness: State repository facts directly in the first paragraph. Never use generic chatbot openings like 'Based on the available information' or 'This repository appears to' unless actual uncertainty exists.\n"
            "3. Honest Uncertainty: If the indexed evidence does not establish something, explicitly state that it is unknown or inferred: 'ARIA cannot establish this from the indexed repository evidence.' Then provide the closest supported structural interpretation.\n"
            "4. Traceability: Always prefer concrete facts: concrete file -> concrete symbol -> concrete relationship -> concrete behavior with line ranges where available.\n"
            "5. Concise Density: Prioritize technical density over verbosity. Never pad answers with generic software engineering prose."
        )
