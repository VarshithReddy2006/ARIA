"""Conversation Memory Store — Phase 2 & Milestone Conversation-Aware Retrieval.

Lightweight in-process session memory tracking:
  - Immutable ConversationContext per session
  - Pronoun/reference resolution ("it", "that class", "this file")
  - Topic confidence, navigation graph, canonical resolved query memory
  - Repository session isolation (keyed by repo_name::session_id)
  - TTL-based expiry and bounded memory queues

Design decisions:
  - NO long-term vector memory — intentionally lightweight.
  - Sessions keyed by (repo_name, session_id).
  - Memory bounds: max 10 questions, max 10 answers, max 10 files, max 20 symbols.
  - Thread-safe for concurrent FastAPI requests.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from services.chat.conversation_context import ConversationContext

logger = logging.getLogger(__name__)

# Session TTL: 30 minutes of inactivity
_SESSION_TTL_SECONDS = 1800

# Maximum turns to keep in memory (older turns are pruned)
_MAX_TURNS = 20
_MAX_ENTITIES = 20
_MAX_FILES = 10


@dataclass
class ConversationTurn:
    """A single question-answer pair in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConversationSession:
    """Per-session state tracked across turns.

    Attributes:
        session_id: Unique identifier for this session.
        repo_name: Repository this session is about.
        turns: Chronological list of conversation turns.
        context: Immutable ConversationContext instance.
        last_entities: Recently mentioned code entities.
        last_files: Recently mentioned file paths.
        last_intent: The IntentType of the last classified turn.
        last_active: Unix timestamp of the last activity.
    """

    session_id: str
    repo_name: str
    turns: List[ConversationTurn] = field(default_factory=list)
    context: Optional[ConversationContext] = None
    last_entities: List[str] = field(default_factory=list)
    last_files: List[str] = field(default_factory=list)
    last_intent: Optional[str] = None
    last_active: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.context is None:
            self.context = ConversationContext.create(self.repo_name)

    def get_context(self) -> ConversationContext:
        if self.context is None:
            self.context = ConversationContext.create(self.repo_name)
        return self.context

    def set_context(self, new_context: ConversationContext) -> None:
        self.context = new_context
        # Sync legacy last_entities and last_files for backward compatibility
        self.last_entities = list(new_context.recently_discussed_symbols)
        self.last_files = list(new_context.recently_discussed_files)

    def add_turn(self, role: str, content: str) -> None:
        """Append a turn and update last_active, pruning oldest if needed."""
        self.turns.append(ConversationTurn(role=role, content=content))
        self.last_active = time.time()
        if len(self.turns) > _MAX_TURNS:
            self.turns = self.turns[-_MAX_TURNS:]

    def update_context(
        self,
        entities: List[str],
        files: List[str],
        intent: Optional[str] = None,
    ) -> None:
        """Update tracked entities, files, and last intent after a turn."""
        for e in reversed(entities):
            if e and e not in self.last_entities:
                self.last_entities.insert(0, e)
        self.last_entities = self.last_entities[:_MAX_ENTITIES]

        for f in reversed(files):
            if f and f not in self.last_files:
                self.last_files.insert(0, f)
        self.last_files = self.last_files[:_MAX_FILES]

        if intent:
            self.last_intent = intent
        self.last_active = time.time()

        # Sync into ConversationContext
        if self.context:
            self.context = self.context.with_turn(
                question="",
                answer="",
                resolved_query="",
                files_mentioned=tuple(files),
                symbols_mentioned=tuple(entities),
            )

    def resolve_pronouns(self, question: str) -> str:
        """Expand known pronouns/references in the question using tracked context."""
        if not question:
            return question

        target = None
        if self.last_entities:
            target = self.last_entities[0]
        elif self.last_files:
            target = self.last_files[0]
        else:
            ctx = self.get_context()
            target = ctx.current_file or (
                ctx.recently_discussed_symbols[0]
                if ctx.recently_discussed_symbols
                else None
            )

        if not target:
            return question

        resolved = question
        patterns = [
            (r"\bthat function\b", target),
            (r"\bthis function\b", target),
            (r"\bthis endpoint\b", target),
            (r"\bthat endpoint\b", target),
            (r"\bthis file\b", target),
            (r"\bthat file\b", target),
            (r"\bits callers\b", f"callers of `{target}`"),
            (r"\bwho calls it\b", f"who calls `{target}`"),
            (r"\bwhat calls it\b", f"what calls `{target}`"),
            (r"\bwhat depends on it\??", f"what depends on `{target}`?"),
            (
                r"\bwhat happens if (?:I|we) change it\??",
                f"what happens if we change `{target}`?",
            ),
            (
                r"\bhow (?:would|do) (?:I|we) test (?:that|it)\??",
                f"how to test `{target}`?",
            ),
            (r"\bhow to safely modify it\??", f"how to safely modify `{target}`?"),
        ]

        for pat, repl in patterns:
            if re.search(pat, resolved, re.I):
                resolved = re.sub(pat, repl, resolved, count=1, flags=re.I)

        # Standalone pronoun replacements (" it ", " that ")
        if target and target.lower() not in resolved.lower():
            for p in [" it ", " it?", " it.", " that?", " that."]:
                if p in f" {resolved.lower()} ":
                    resolved = re.sub(
                        re.escape(p.strip()),
                        f"`{target}`",
                        resolved,
                        count=1,
                        flags=re.I,
                    )
                    break

        return resolved

    def get_history_for_llm(self) -> List[Dict]:
        """Return turns formatted for LLM provider history."""
        return [{"role": t.role, "content": t.content} for t in self.turns]

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_active) > _SESSION_TTL_SECONDS


class ConversationMemoryStore:
    """Thread-safe store for all active conversation sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.Lock()

    def _session_key(self, repo_name: str, session_id: str) -> str:
        return f"{repo_name}::{session_id}"

    def get_or_create(
        self,
        repo_name: str,
        session_id: Optional[str] = None,
    ) -> ConversationSession:
        resolved_session_id = (
            session_id.strip()
            if session_id and session_id.strip()
            else uuid.uuid4().hex
        )
        key = self._session_key(repo_name, resolved_session_id)
        with self._lock:
            self._evict_expired()
            if key not in self._sessions:
                self._sessions[key] = ConversationSession(
                    session_id=resolved_session_id,
                    repo_name=repo_name,
                )
                logger.debug("ConversationMemory: new session key=%s", key)
            return self._sessions[key]

    def clear_session(self, repo_name: str, session_id: Optional[str] = None) -> None:
        if not session_id or not session_id.strip():
            return
        key = self._session_key(repo_name, session_id.strip())
        with self._lock:
            self._sessions.pop(key, None)

    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def _evict_expired(self) -> None:
        expired = [k for k, s in self._sessions.items() if s.is_expired]
        for k in expired:
            del self._sessions[k]
        if expired:
            logger.debug(
                "ConversationMemory: evicted %d expired session(s)", len(expired)
            )


# Module-level singleton
conversation_memory = ConversationMemoryStore()
