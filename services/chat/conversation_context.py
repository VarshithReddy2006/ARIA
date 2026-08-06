"""Conversation Context — Immutable session-scoped state.

Tracks repository context, active topic confidence, navigation graph, canonical resolved query memory,
and bounded discussion history across turns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

from services.chat.conversation_settings import ConversationSettings
from services.chat.navigation_graph import NavigationGraph


def _module_from_file_path(file_path: str) -> Optional[str]:
    """Derive dotted module name from relative file path."""
    if not file_path:
        return None
    clean = file_path.replace("\\", "/").strip("/")
    if clean.endswith(".py"):
        clean = clean[:-3]
    parts = clean.split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Immutable aggregate holding session conversation state."""

    current_repo: Optional[str] = None
    current_file: Optional[str] = None
    current_symbol: Optional[str] = None
    current_class: Optional[str] = None
    current_function: Optional[str] = None
    current_module: Optional[str] = None
    topic_confidence: float = 0.98
    navigation_graph: NavigationGraph = field(default_factory=NavigationGraph)
    recently_discussed_files: Tuple[str, ...] = ()
    recently_discussed_symbols: Tuple[str, ...] = ()
    previous_questions: Tuple[str, ...] = ()
    previous_answers: Tuple[str, ...] = ()
    canonical_resolved_queries: Tuple[str, ...] = ()

    @classmethod
    def create(
        cls, repo_name: str, settings: Optional[ConversationSettings] = None
    ) -> ConversationContext:
        s = settings or ConversationSettings.default()
        return cls(
            current_repo=repo_name,
            topic_confidence=s.topic_initial_confidence,
        )

    def with_same_topic_boost(
        self, settings: Optional[ConversationSettings] = None
    ) -> ConversationContext:
        """Increase topic confidence toward 1.0 when follow-up stays on same topic."""
        new_conf = min(1.0, self.topic_confidence + 0.05)
        return self._copy_with(topic_confidence=new_conf)

    def with_related_decay(
        self, settings: Optional[ConversationSettings] = None
    ) -> ConversationContext:
        """Apply small decay when topic is related."""
        s = settings or ConversationSettings.default()
        new_conf = self.topic_confidence * (1.0 - s.topic_decay_rate * 0.5)
        return self._copy_with(topic_confidence=max(0.0, new_conf))

    def with_unrelated_decay(
        self, settings: Optional[ConversationSettings] = None
    ) -> ConversationContext:
        """Apply larger decay when query is unrelated."""
        s = settings or ConversationSettings.default()
        new_conf = self.topic_confidence * (1.0 - s.topic_decay_rate)
        return self._copy_with(topic_confidence=max(0.0, new_conf))

    def with_topic_switch(
        self,
        new_file: Optional[str] = None,
        new_symbol: Optional[str] = None,
        new_class: Optional[str] = None,
        new_function: Optional[str] = None,
        new_module: Optional[str] = None,
        settings: Optional[ConversationSettings] = None,
    ) -> ConversationContext:
        """Execute an explicit topic switch, resetting confidence and updating navigation history."""
        s = settings or ConversationSettings.default()

        # Build new recently discussed files
        recent_files = list(self.recently_discussed_files)
        if self.current_file and self.current_file not in recent_files:
            recent_files.insert(0, self.current_file)
        if new_file and new_file in recent_files:
            recent_files.remove(new_file)
        recent_files = recent_files[: s.max_recent_files]

        # Build new recently discussed symbols
        recent_symbols = list(self.recently_discussed_symbols)
        if self.current_symbol and self.current_symbol not in recent_symbols:
            recent_symbols.insert(0, self.current_symbol)
        if new_symbol and new_symbol in recent_symbols:
            recent_symbols.remove(new_symbol)
        recent_symbols = recent_symbols[: s.max_recent_symbols]

        # Update navigation graph
        target_entity = new_file or new_symbol or self.current_file or "unknown"
        nav = self.navigation_graph.add_step(
            to_entity=target_entity, transition_type="TOPIC_SWITCH"
        )

        derived_module = new_module or (
            _module_from_file_path(new_file) if new_file else None
        )

        return self._copy_with(
            current_file=new_file if new_file is not None else self.current_file,
            current_symbol=new_symbol
            if new_symbol is not None
            else self.current_symbol,
            current_class=new_class,
            current_function=new_function,
            current_module=derived_module
            if derived_module is not None
            else self.current_module,
            topic_confidence=s.topic_switch_confidence,
            navigation_graph=nav,
            recently_discussed_files=tuple(recent_files),
            recently_discussed_symbols=tuple(recent_symbols),
        )

    def with_turn(
        self,
        question: str,
        answer: str,
        resolved_query: str,
        files_mentioned: Optional[Tuple[str, ...]] = None,
        symbols_mentioned: Optional[Tuple[str, ...]] = None,
        settings: Optional[ConversationSettings] = None,
    ) -> ConversationContext:
        """Update context with completed turn details and bound memory queues."""
        s = settings or ConversationSettings.default()

        # Bounded questions & answers
        prev_q = (list(self.previous_questions) + [question])[-s.max_history :]
        prev_a = (list(self.previous_answers) + [answer])[-s.max_history :]
        prev_rq = (list(self.canonical_resolved_queries) + [resolved_query])[
            -s.max_history :
        ]

        # Update files
        recent_files = list(self.recently_discussed_files)
        if files_mentioned:
            for f in reversed(files_mentioned):
                if f and f not in recent_files:
                    recent_files.insert(0, f)
        recent_files = recent_files[: s.max_recent_files]

        # Update symbols
        recent_syms = list(self.recently_discussed_symbols)
        if symbols_mentioned:
            for sym in reversed(symbols_mentioned):
                if sym and sym not in recent_syms:
                    recent_syms.insert(0, sym)
        recent_syms = recent_syms[: s.max_recent_symbols]

        # Active file / module update if first turn set
        cur_file = self.current_file
        cur_mod = self.current_module
        nav = self.navigation_graph
        if not cur_file and files_mentioned and len(files_mentioned) > 0:
            cur_file = files_mentioned[0]
            cur_mod = _module_from_file_path(cur_file)
            nav = nav.add_step(to_entity=cur_file, transition_type="INITIAL")

        return self._copy_with(
            current_file=cur_file,
            current_module=cur_mod,
            navigation_graph=nav,
            recently_discussed_files=tuple(recent_files),
            recently_discussed_symbols=tuple(recent_syms),
            previous_questions=tuple(prev_q),
            previous_answers=tuple(prev_a),
            canonical_resolved_queries=tuple(prev_rq),
        )

    def _copy_with(self, **kwargs) -> ConversationContext:
        """Return a new ConversationContext instance with modified fields."""
        fields = {
            "current_repo": self.current_repo,
            "current_file": self.current_file,
            "current_symbol": self.current_symbol,
            "current_class": self.current_class,
            "current_function": self.current_function,
            "current_module": self.current_module,
            "topic_confidence": self.topic_confidence,
            "navigation_graph": self.navigation_graph,
            "recently_discussed_files": self.recently_discussed_files,
            "recently_discussed_symbols": self.recently_discussed_symbols,
            "previous_questions": self.previous_questions,
            "previous_answers": self.previous_answers,
            "canonical_resolved_queries": self.canonical_resolved_queries,
        }
        fields.update(kwargs)
        return ConversationContext(**fields)
