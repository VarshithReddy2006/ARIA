"""Follow-Up Synthesis Engine — Phase 12.

Generates repository-specific, entity-aware, non-generic follow-up questions
derived directly from the current question, assistant answer, retrieved code chunks,
call graph relationships, engineering threads, and conversation history.

Rejects generic boilerplate questions and ensures questions progressively deepen
the developer's investigation of the codebase.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set

from services.chat.engineering_threads import EngineeringThreadTracker
from services.chat.question_novelty import QuestionNoveltyScorer

logger = logging.getLogger(__name__)

# Regex for file paths
_FILE_RE = re.compile(
    r"\b([\w./\\-]+\.(py|ts|tsx|js|jsx|java|go|rs|rb|php|cs|cpp|c|h|yml|yaml|json|md|pkl|onnx|pt|bin))\b",
    re.I,
)

# Regex for symbols / functions / classes
_SYMBOL_RE = re.compile(r"\b`?([a-zA-Z_][a-zA-Z0-9_]{2,})\(\)?`?\b")

# Regex for endpoints
_ENDPOINT_RE = re.compile(r"(?:GET|POST|PUT|DELETE|PATCH)?\s*(/\w+(?:/[\w-]+)*)", re.I)


class FollowUpEngine:
    """Multi-stage follow-up synthesis and ranking engine."""

    def __init__(self) -> None:
        self._trackers: Dict[str, EngineeringThreadTracker] = {}

    def get_or_create_tracker(self, repo_name: str) -> EngineeringThreadTracker:
        if repo_name not in self._trackers:
            self._trackers[repo_name] = EngineeringThreadTracker(repo_name)
        return self._trackers[repo_name]

    def synthesize_follow_ups(
        self,
        repo_name: str,
        question: str,
        answer: Any,
        intent: str,
        code_chunks: Optional[List[Dict[str, Any]]] = None,
        source_files: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        structured_context: Optional[str] = None,
    ) -> List[str]:
        """Synthesize 2–3 ranked, entity-aware follow-up questions."""
        code_chunks = code_chunks or []
        source_files = source_files or []
        conversation_history = conversation_history or []

        q_str = (
            question[0] if isinstance(question, (tuple, list)) else str(question or "")
        )
        a_str = answer[0] if isinstance(answer, (tuple, list)) else str(answer or "")

        # 1. Extract concrete entities
        extracted_files = self._extract_files(q_str, a_str, code_chunks, source_files)
        extracted_symbols = self._extract_symbols(q_str, a_str, code_chunks)
        extracted_endpoints = self._extract_endpoints(q_str, a_str, code_chunks)

        # 2. Update thread tracker
        tracker = self.get_or_create_tracker(repo_name)
        tracker.record_turn(
            question=q_str,
            answer=a_str,
            extracted_files=extracted_files,
            extracted_symbols=extracted_symbols,
            extracted_endpoints=extracted_endpoints,
            intent_name=intent,
        )

        unresolved_aspects = tracker.get_unresolved_aspects()
        explored_entities = set(tracker.discovered_entities.keys())
        current_depth = int(tracker.current_depth)

        logger.info(
            "[LLM_FOLLOWUP] repo=%s depth=%d files=%s symbols=%s endpoints=%s unresolved=%d",
            repo_name,
            current_depth,
            extracted_files[:3],
            extracted_symbols[:3],
            extracted_endpoints[:2],
            len(unresolved_aspects),
        )

        # 3. Generate candidate questions across strategies
        candidates_raw: List[str] = []

        # Strategy A: Function & Transformation drilldown with containing file
        for sym in extracted_symbols[:4]:
            if sym.lower() in ("pass", "main", "none", "true", "false"):
                continue
            matching_files = [
                f
                for f in extracted_files
                if not f.endswith((".md", ".txt", ".json", ".yaml"))
            ]
            if matching_files:
                target_f = matching_files[0]
                candidates_raw.append(
                    f"What exact data transformations does `{sym}()` perform inside `{target_f}`?"
                )
                candidates_raw.append(
                    f"Which callers in the codebase depend on the return value of `{sym}()` in `{target_f}`?"
                )
            else:
                candidates_raw.append(
                    f"What exact data transformations does `{sym}()` perform?"
                )
                candidates_raw.append(
                    f"Which callers in the codebase depend on the return value of `{sym}()`?"
                )

        # Strategy B: Artifact Lifecycle & Validation
        for art in re.findall(
            r"[\w\-\./]+\.(?:pkl|onnx|h5|pt|joblib)", a_str + " " + q_str, re.I
        ):
            matching_files = [
                f
                for f in extracted_files
                if not f.endswith((".md", ".txt", ".json", ".yaml"))
            ]
            target_f = f" in `{matching_files[0]}`" if matching_files else ""
            candidates_raw.append(
                f"How is `{art}` loaded, cached, and validated{target_f} before inference execution?"
            )
            candidates_raw.append(
                f"Where in the repository is `{art}` trained or generated?"
            )

        # Strategy C: Caller & Dependency propagation
        if extracted_files:
            f0 = extracted_files[0]
            if len(extracted_files) >= 2:
                f1 = extracted_files[1]
                candidates_raw.append(
                    f"How do changes in `{f0}` propagate to `{f1}` during execution?"
                )
            else:
                candidates_raw.append(
                    f"Which upstream components call `{f0}` and how are errors handled?"
                )

        # Strategy D: Schema Change & Blast Radius
        for sym in extracted_symbols[:3]:
            matching_files = [
                f
                for f in extracted_files
                if not f.endswith((".md", ".txt", ".json", ".yaml"))
            ]
            target_f = f" in `{matching_files[0]}`" if matching_files else ""
            candidates_raw.append(
                f"What would break across callers if `{sym}()`{target_f} changed its schema or output contract?"
            )

        # Strategy E: Endpoint & Route Validation
        for ep in extracted_endpoints[:2]:
            matching_f = extracted_files[0] if extracted_files else "Backend/app.py"
            candidates_raw.append(
                f"What payload validation occurs on `{ep}` in `{matching_f}` before dispatching?"
            )

        # Strategy F: Safe Refactoring & Testing
        for sym in extracted_symbols[:2]:
            matching_files = [
                f
                for f in extracted_files
                if not f.endswith((".md", ".txt", ".json", ".yaml"))
            ]
            target_f = f" in `{matching_files[0]}`" if matching_files else ""
            candidates_raw.append(
                f"What unit tests and fixtures should be added to verify `{sym}()`{target_f}?"
            )

        # Strategy G: Unresolved Aspects from Threads
        for unres in unresolved_aspects[:3]:
            if "artifact" in unres or ".pkl" in unres:
                candidates_raw.append(
                    "How is the model artifact trained, versioned, or updated in the repository?"
                )
            elif "caller" in unres:
                candidates_raw.append(
                    "Which callers outside the primary flow invoke these transformation helpers?"
                )
            elif "test" in unres:
                candidates_raw.append(
                    "What regression tests exist for this component and where are fixtures defined?"
                )
            else:
                candidates_raw.append(f"How is {unres} handled in the implementation?")

        # Strategy H: Intent-specific fallbacks
        norm_intent = intent.upper()
        if norm_intent in ("API", "API_FLOW", "API_SURFACE") and extracted_endpoints:
            candidates_raw.append(
                f"How does error handling and response formatting work on `{extracted_endpoints[0]}`?"
            )
        elif norm_intent in ("DEPENDENCY", "CIRCULAR_DEPENDENCY") and extracted_files:
            candidates_raw.append(
                f"What is the inbound and outbound fan-in/fan-out coupling for `{extracted_files[0]}`?"
            )
        elif norm_intent in ("CHANGE_PLANNING", "IMPACT_ANALYSIS") and extracted_files:
            candidates_raw.append(
                f"What is the recommended step-by-step edit order for modifying `{extracted_files[0]}`?"
            )

        # 4. Score and filter candidates using QuestionNoveltyScorer
        scored_candidates = []
        for cand in candidates_raw:
            sc = QuestionNoveltyScorer.score_candidate(
                candidate_text=cand,
                current_question=q_str,
                conversation_history=conversation_history,
                explored_entities=explored_entities,
                unresolved_aspects=unresolved_aspects,
                current_depth=current_depth,
            )
            if sc.novelty_score > 0:
                scored_candidates.append(sc)

        # Sort by novelty score descending
        scored_candidates.sort(key=lambda c: c.novelty_score, reverse=True)

        # 5. Select 2–3 diverse, non-redundant questions
        selected: List[str] = []
        seen_stems: Set[str] = set()

        for c in scored_candidates:
            stem = " ".join(re.findall(r"\w+", c.prompt.lower())[:5])
            if stem in seen_stems:
                continue
            seen_stems.add(stem)
            selected.append(c.prompt)
            if len(selected) >= 3:
                break

        # Fallback if no candidate passed
        if len(selected) < 2 and extracted_files:
            f0 = extracted_files[0]
            selected.append(f"Which callers in the codebase depend directly on `{f0}`?")
            if len(extracted_symbols) > 0:
                selected.append(
                    f"What exact behavior is defined in `{extracted_symbols[0]}()`?"
                )

        return selected[:3]

    def _extract_files(
        self,
        question: str,
        answer: str,
        code_chunks: List[Dict[str, Any]],
        source_files: List[str],
    ) -> List[str]:
        files: List[str] = []
        for f in source_files:
            if f and f not in files:
                files.append(f)
        for chunk in code_chunks:
            fp = chunk.get("metadata", {}).get("file_path") or chunk.get("file_path")
            if fp and fp not in files:
                files.append(fp)
        for text in (question, answer):
            for match in _FILE_RE.findall(text):
                f_path = match[0] if isinstance(match, tuple) else match
                f_clean = f_path.strip().strip("`").strip("'").strip('"')
                if f_clean and f_clean not in files and not f_clean.startswith("http"):
                    files.append(f_clean)
        return files

    def _extract_symbols(
        self,
        question: str,
        answer: str,
        code_chunks: List[Dict[str, Any]],
    ) -> List[str]:
        symbols: List[str] = []
        for chunk in code_chunks:
            meta = chunk.get("metadata", {})
            matched = meta.get("matched_symbols") or meta.get("symbol_name")
            if matched:
                if isinstance(matched, list):
                    for s in matched:
                        if s and s not in symbols:
                            symbols.append(s)
                elif isinstance(matched, str) and matched not in symbols:
                    symbols.append(matched)

        for text in (answer, question):
            for m in re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]{2,})\(\)`", text):
                if m not in symbols:
                    symbols.append(m)
            for m in re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]{3,})`", text):
                if m not in symbols and not m.endswith(
                    (".py", ".js", ".ts", ".md", ".json")
                ):
                    symbols.append(m)
            for m in _SYMBOL_RE.findall(text):
                if m not in symbols and not m.endswith(
                    (".py", ".js", ".ts", ".md", ".json")
                ):
                    symbols.append(m)

        _ignore = {
            "def",
            "class",
            "return",
            "import",
            "from",
            "async",
            "await",
            "self",
            "none",
            "true",
            "false",
            "str",
            "int",
            "list",
            "dict",
        }
        return [s for s in symbols if s.lower() not in _ignore]

    def _extract_endpoints(
        self,
        question: str,
        answer: str,
        code_chunks: List[Dict[str, Any]],
    ) -> List[str]:
        endpoints: List[str] = []
        for text in (question, answer):
            for m in _ENDPOINT_RE.findall(text):
                ep = m.strip()
                if (
                    ep
                    and ep not in endpoints
                    and not ep.startswith(("//", "/Users", "/home", "/etc"))
                ):
                    endpoints.append(ep)
        return endpoints
