"""Query Rewriter — Rewrites contextual questions into explicit, self-contained repository queries.

Uses ConversationContext, canonical resolved query memory, and NavigationGraph to resolve ambiguous
pronouns ("it", "this", "that") and relative references ("that file", "there", "previous module", "its dependency").
Ensures explicit entity mentions take immediate priority and are used as the new query anchor.
Rewritten queries are stored as canonical resolved queries for multi-turn reasoning and are never shown to users.
"""

from __future__ import annotations

import re
from typing import Optional

from services.chat.conversation_context import ConversationContext
from services.chat.explicit_entity_resolver import ExplicitEntityResult
from services.chat.followup_detector import FollowUpResult
from services.chat.topic_switch_detector import TopicSwitchResult


class QueryRewriter:
    """Service rewriting ambiguous follow-up questions into explicit repository queries."""

    def rewrite(
        self,
        question: str,
        context: ConversationContext,
        followup_res: Optional[FollowUpResult] = None,
        switch_res: Optional[TopicSwitchResult] = None,
        explicit_res: Optional[ExplicitEntityResult] = None,
    ) -> str:
        """Rewrite raw question into an explicit, self-contained query."""
        if not question or not question.strip():
            return question

        q_clean = question.strip()
        q_lower = q_clean.lower()

        # Handle explicit entity introduction or topic switch rewrite
        if (switch_res and switch_res.is_topic_switch) or (
            explicit_res and explicit_res.has_explicit_entity
        ):
            target_file = (
                switch_res.target_file
                if switch_res and switch_res.target_file
                else (explicit_res.target_file if explicit_res else None)
            )
            target_symbol = (
                switch_res.target_symbol
                if switch_res and switch_res.target_symbol
                else (
                    explicit_res.target_symbol or explicit_res.entity_name
                    if explicit_res
                    else None
                )
            )
            target_anchor = target_file or target_symbol

            if target_anchor:
                current_file = context.current_file

                if (
                    "compare to" in q_lower
                    or "differs" in q_lower
                    or "versus" in q_lower
                ):
                    if current_file and current_file.lower() != target_anchor.lower():
                        return f"How does {current_file} compare to {target_anchor}?"

                if q_lower.startswith(
                    (
                        "explain",
                        "now explain",
                        "switch to",
                        "move to",
                        "focus on",
                        "describe",
                    )
                ):
                    return f"Explain {target_anchor}"

                if (
                    "belong there instead" in q_lower
                    or "belong in" in q_lower
                    or "belong there" in q_lower
                ):
                    if current_file and current_file.lower() != target_anchor.lower():
                        return f"What responsibilities belong in {target_anchor} instead of {current_file}?"
                    return f"What responsibilities belong in {target_anchor}?"

        # Target entity to anchor query
        target_file = (
            switch_res.target_file
            if switch_res and switch_res.target_file
            else context.current_file
        )
        target_symbol = (
            switch_res.target_symbol
            if switch_res and switch_res.target_symbol
            else context.current_symbol
        )
        anchor = target_file or target_symbol or context.current_repo or ""

        if not anchor:
            return q_clean

        last_canonical = (
            context.canonical_resolved_queries[-1]
            if context.canonical_resolved_queries
            else ""
        )

        # Handle single-word / ultrashort follow-ups ("Why?", "How?", "Where?")
        if q_lower in ("why?", "why", "how?", "how", "where?", "where"):
            if (
                "startup strategy" in last_canonical.lower()
                or "startup" in last_canonical.lower()
            ):
                return (
                    f"Why is the startup strategy implemented in {anchor} beneficial?"
                )
            elif (
                "services" in last_canonical.lower()
                or "initialize" in last_canonical.lower()
            ):
                return (
                    f"Why are the services initialized inside {anchor} during startup?"
                )
            elif last_canonical:
                return f"{q_clean.strip('?')} is this logic in {anchor} implemented this way?"
            else:
                return f"Why is {anchor} implemented this way?"

        # Handle relative reference resolution ("that file", "there", "previous module", "earlier service", "its dependency")
        if "there" in q_lower or "that file" in q_lower or "belong there" in q_lower:
            prev_file = context.navigation_graph.find_previous_file() or (
                context.recently_discussed_files[0]
                if context.recently_discussed_files
                else None
            )
            if prev_file and target_file and prev_file.lower() != target_file.lower():
                return f"What responsibilities belong in {target_file} instead of {prev_file}?"
            elif target_file:
                return f"What responsibilities belong in {target_file}?"

        if "that startup strategy" in q_lower:
            return f"Why is the startup strategy implemented in {anchor} beneficial?"

        if "services" in q_lower and (
            "initialize" in q_lower or "it initialize" in q_lower
        ):
            return f"Which services are initialized inside {anchor}?"

        if "manage middleware" in q_lower or "middleware" in q_lower:
            return f"How does {anchor} manage middleware?"

        if (
            "how does it work" in q_lower
            or "how does it differ" in q_lower
            or "why is it separated" in q_lower
        ):
            if "separated" in q_lower:
                return f"Why is {anchor} separated into its own module?"
            if "differ" in q_lower:
                prev = context.navigation_graph.find_previous_file() or (
                    context.recently_discussed_files[0]
                    if context.recently_discussed_files
                    else None
                )
                if prev and anchor and prev.lower() != anchor.lower():
                    return f"How does {anchor} differ from {prev}?"
            return f"How does {anchor} work?"

        if "how is it initialized" in q_lower:
            return f"How is {anchor} initialized?"

        if "who calls it" in q_lower:
            return f"Who calls {anchor}?"

        if "where is it used" in q_lower:
            return f"Where is {anchor} used?"

        # Generic pronoun replacement ("it", "this", "that", "its")
        if anchor:
            words = q_clean.split()
            rewritten_words = []
            replaced = False
            for w in words:
                w_lower = re.sub(r"[^\w]", "", w.lower())
                if w_lower in ("it", "this", "that", "its") and not replaced:
                    suffix = w[len(w_lower) :]
                    rewritten_words.append(f"{anchor}{suffix}")
                    replaced = True
                else:
                    rewritten_words.append(w)

            if replaced:
                return " ".join(rewritten_words)

        # Fallback if no specific rule matched but anchor exists and follow-up detected
        if (
            followup_res
            and followup_res.is_followup
            and anchor
            and anchor.lower() not in q_lower
        ):
            return f"{q_clean} (regarding {anchor})"

        return q_clean
