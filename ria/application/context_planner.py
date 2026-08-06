"""Context Planner application service.

Converts classified Intent + ContextRequest into a deterministic retrieval ContextPlan.
Implements :class:`~ria.ports.context.ContextPlannerPort`.
"""

from __future__ import annotations

import re
from typing import Set

from ria.domain.models.context_plan import ContextPlan
from ria.domain.models.context_request import ContextRequest, IntentClassification
from ria.ports.context import ContextPlannerPort

__all__ = ["ContextPlannerService"]


class ContextPlannerService(ContextPlannerPort):
    """Service for constructing deterministic ContextPlans."""

    def plan_context(
        self,
        request: ContextRequest,
        intent: IntentClassification,
    ) -> ContextPlan:
        """Construct a ContextPlan for retrieval."""
        text = request.query_text

        # Extract file paths (e.g. app.py, src/main.py)
        file_matches = re.findall(
            r"\b[\w/\\-]+\.(?:py|ts|js|java|go|rs|cpp|c|h)\b", text
        )
        target_files: Set[str] = set(file_matches)

        # Extract potential symbol names (CamelCase or snake_case identifiers)
        symbol_matches = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]{2,}\b", text)
        stop_words = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "how",
            "what",
            "find",
            "bug",
            "code",
            "explain",
        }
        target_symbols: Set[str] = {
            s
            for s in symbol_matches
            if s.lower() not in stop_words and not s.endswith((".py", ".ts", ".js"))
        }

        # Determine graph depth and flags based on intent
        graph_depth = 2
        inc_deps = True
        inc_refs = True

        if intent.intent_type == "trace_dependency":
            graph_depth = 4
        elif intent.intent_type == "architecture_review":
            graph_depth = 3
        elif intent.intent_type == "explain_code":
            graph_depth = 1

        return ContextPlan(
            intent=intent,
            target_symbols=tuple(sorted(target_symbols)),
            target_files=tuple(sorted(target_files)),
            graph_depth=graph_depth,
            include_dependencies=inc_deps,
            include_references=inc_refs,
        )
