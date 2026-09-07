"""Context Builder — Phase 7.

Assembles the final LLM prompt from all intelligence layers, enforcing
a dynamic token budget and structured priority ordering.

Priority order for prompt slots:
  1. System instruction (fixed — not counted in budget)
  2. Architecture context (from ArchContextService)
  3. Structured intelligence (from IntentRouter)
  4. Supporting code chunks (from vector retrieval)
  5. Documentation chunks (README, docs)
  6. Config chunks (pyproject.toml etc.)

Token budget: 3000–5000 tokens target (configurable).
Each "token" is approximated at 4 characters (standard rule of thumb for code).

Output format follows Phase 11 structured answer template injected into
the system instruction so the LLM always produces structured replies.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token budget constants
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 4  # approximation
_TARGET_MIN_TOKENS = 3_000
_TARGET_MAX_TOKENS = 5_000
_TARGET_MAX_CHARS = _TARGET_MAX_TOKENS * _CHARS_PER_TOKEN  # 20_000 chars
_TARGET_MIN_CHARS = _TARGET_MIN_TOKENS * _CHARS_PER_TOKEN  # 12_000 chars

# Maximum characters for a single chunk to prevent one large file dominating
_MAX_CHUNK_CHARS = 2_000

# System instruction character budget (not counted against context budget)
_SYSTEM_CHARS_EXCLUDED = True


@dataclass
class BuiltContext:
    """Result of context assembly.

    Attributes:
        system_instruction: System instruction for the LLM.
        prompt:             Full assembled prompt (context + question).
        estimated_tokens:   Approximate token count.
        source_files:       All files referenced in the context.
        slot_breakdown:     Per-slot character counts for observability.
    """

    system_instruction: str
    prompt: str
    estimated_tokens: int
    source_files: List[str] = field(default_factory=list)
    slot_breakdown: Dict[str, int] = field(default_factory=dict)


class ContextBuilder:
    """Assembles the LLM prompt from prioritised intelligence slots.

    Usage::

        builder = ContextBuilder()
        ctx = builder.build(
            repo_name="owner/repo",
            question="How does UserService work?",
            arch_context_block="## Architecture ...",
            structured_intelligence="## Symbol Lookup ...",
            code_chunks=[{"content": "...", "metadata": {...}}, ...],
            conversation_history=[{"role": "user", "content": "..."}, ...],
        )
        answer = await provider.generate(
            prompt=ctx.prompt,
            system_instruction=ctx.system_instruction,
            history=ctx.conversation_history,
        )
    """

    def __init__(
        self,
        max_chars: int = _TARGET_MAX_CHARS,
        min_chars: int = _TARGET_MIN_CHARS,
        max_chunk_chars: int = _MAX_CHUNK_CHARS,
        max_files: int = 8,
        max_chunks: int = 10,
        max_chunks_per_file: int = 3,
    ) -> None:
        self.max_chars = max_chars
        self.min_chars = min_chars
        self.max_chunk_chars = max_chunk_chars
        self.max_files = max_files
        self.max_chunks = max_chunks
        self.max_chunks_per_file = max_chunks_per_file

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        repo_name: str,
        question: str,
        arch_context_block: str = "",
        structured_intelligence: str = "",
        code_chunks: Optional[List[Dict[str, Any]]] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        intent_name: str = "GENERAL_QA",
        deterministic_file_path: Optional[str] = None,
        matched_symbol: Optional[str] = None,
        symbol_start_line: Optional[int] = None,
        symbol_end_line: Optional[int] = None,
        symbol_coverage: Optional[int] = None,
        symbol_methods: Optional[List[str]] = None,
    ) -> BuiltContext:
        """Assemble the full context prompt.

        Args:
            repo_name:               Repository identifier.
            question:                The (resolved) user question.
            arch_context_block:      Text from ArchContextService.
            structured_intelligence: Text from IntentRouter.
            code_chunks:             Retrieved + reranked code chunks.
            conversation_history:    Prior turns (for history-aware building).
            intent_name:             Detected intent for format tuning.
            deterministic_file_path: Optional path of matched deterministic file.
            matched_symbol:          Optional name of matched symbol.
            symbol_start_line:       Optional start line of symbol span.
            symbol_end_line:         Optional end line of symbol span.
            symbol_coverage:         Optional coverage percentage of symbol.
            symbol_methods:          Optional list of verified declared method names.

        Returns:
            BuiltContext with assembled prompt and metadata.
        """
        raw_chunks = code_chunks or []

        # ── Step 0: Deduplicate and budget-constrain incoming code chunks
        if deterministic_file_path:
            code_chunks = self._filter_deterministic_chunks(raw_chunks)
        else:
            code_chunks = self._filter_and_budget_chunks(
                raw_chunks, structured_intelligence
            )

        slots: Dict[str, str] = {}
        breakdown: Dict[str, int] = {}

        # ── Slot 1: Architecture context (highest priority after structure)
        if arch_context_block and arch_context_block.strip():
            slots["architecture"] = arch_context_block.strip()

        # ── Slot 2: Structured intelligence from IntentRouter
        if structured_intelligence and structured_intelligence.strip():
            slots["structured_intelligence"] = structured_intelligence.strip()

        # ── Slot 3: Code chunks (split by type/tier or formatted deterministically)
        if deterministic_file_path:
            # Deterministic Retrieval Active
            # Extract metadata directly from chunk metadata without disk reads or AST re-parsing
            language = "unknown"
            if code_chunks:
                language = code_chunks[0].get("metadata", {}).get("language", "unknown")
            if language == "unknown":
                ext = os.path.splitext(deterministic_file_path)[1].lower()
                ext_map = {
                    ".py": "python",
                    ".ts": "typescript",
                    ".tsx": "tsx",
                    ".js": "javascript",
                    ".jsx": "jsx",
                    ".go": "go",
                    ".rs": "rust",
                    ".java": "java",
                    ".cpp": "cpp",
                    ".c": "c",
                    ".cs": "csharp",
                    ".rb": "ruby",
                    ".php": "php",
                    ".swift": "swift",
                    ".kt": "kotlin",
                    ".json": "json",
                    ".yaml": "yaml",
                    ".yml": "yaml",
                    ".toml": "toml",
                    ".md": "markdown",
                }
                language = ext_map.get(ext, "unknown")

            # Extract symbols from chunk metadata already populated during retrieval
            symbols: List[str] = []
            seen_syms = set()
            for ch in code_chunks:
                ch_meta = ch.get("metadata", {})
                sym_str = ch_meta.get("matched_symbols", "")
                if sym_str:
                    for s in sym_str.split(","):
                        s_clean = s.strip()
                        if s_clean and s_clean not in seen_syms:
                            seen_syms.add(s_clean)
                            symbols.append(s_clean)
                for s in ch_meta.get("symbols", []):
                    s_name = s.get("name") if isinstance(s, dict) else str(s)
                    if s_name and s_name not in seen_syms:
                        seen_syms.add(s_name)
                        symbols.append(s_name)

            # Extract imports from chunk metadata if available
            imports: List[str] = []
            if code_chunks:
                imports = code_chunks[0].get("metadata", {}).get("imports", []) or []

            # Build deterministic context block
            det_parts = [
                "### Deterministic File Information",
                f"- **File Path:** {deterministic_file_path}",
                f"- **Language:** {language}",
                f"- **Repository Root:** {repo_name}",
            ]

            if (
                matched_symbol
                and symbol_start_line is not None
                and symbol_end_line is not None
            ):
                cov = symbol_coverage if symbol_coverage is not None else 100
                total_sym_lines = max(1, symbol_end_line - symbol_start_line + 1)
                if cov >= 100:
                    det_parts.append(
                        f"\n[FULL_SYMBOL]\nfile={deterministic_file_path}\nsymbol={matched_symbol}\nlines={symbol_start_line}-{symbol_end_line}\ncoverage=100%"
                    )
                else:
                    det_parts.append(
                        f"\n[PARTIAL_SYMBOL]\nfile={deterministic_file_path}\nsymbol={matched_symbol}\nlines={symbol_start_line}-{symbol_end_line}\ntotal_symbol_lines={total_sym_lines}\ncoverage={cov}%"
                    )
                if symbol_methods:
                    det_parts.append(
                        f"- **Verified Declared Methods:** {', '.join(symbol_methods)}"
                    )
            else:
                det_parts.append(f"\n[FULL_FILE]\nfile={deterministic_file_path}")

            if imports:
                det_parts.append("- **Imports:**")
                det_parts.extend(f"  - `{imp}`" for imp in imports)

            if symbols:
                det_parts.append("- **Symbol Table:**")
                det_parts.extend(f"  - `{sym}`" for sym in symbols)

            det_parts.append("\n### Chunk Sequence")
            for chunk in code_chunks:
                meta = chunk.get("metadata", {})
                chunk_id = meta.get("chunk_id", "unknown")
                start_line = meta.get("start_line", 0)
                end_line = meta.get("end_line", 0)
                line_range = (
                    f" (lines {start_line}-{end_line})"
                    if start_line and end_line
                    else ""
                )
                content = chunk.get("content", "")
                det_parts.append(
                    f"--- Chunk {chunk_id}{line_range} ---\n```\n{content}\n```"
                )

            det_block = "\n".join(det_parts)
            slots["requested_file"] = det_block
        else:
            requested_slot, related_slot, code_slot, doc_slot, cfg_slot = (
                self._split_chunks_by_tier(code_chunks)
            )
            if requested_slot:
                slots["requested_file"] = requested_slot
            if related_slot:
                slots["related_files"] = related_slot
            if code_slot:
                slots["code"] = code_slot
            if doc_slot:
                slots["docs"] = doc_slot
            if cfg_slot:
                slots["config"] = cfg_slot

        # ── Budget enforcement: trim from lowest priority upward
        slots = self._enforce_budget(slots)

        # ── Assemble final prompt
        prompt_parts: List[str] = []

        if "architecture" in slots:
            prompt_parts.append(slots["architecture"])
            breakdown["architecture"] = len(slots["architecture"])

        if "structured_intelligence" in slots:
            prompt_parts.append(
                "## Repository Intelligence\n" + slots["structured_intelligence"]
            )
            breakdown["structured_intelligence"] = len(slots["structured_intelligence"])

        context_parts: List[str] = []
        if "requested_file" in slots:
            context_parts.append(slots["requested_file"])
            breakdown["requested_file"] = len(slots["requested_file"])
        if "related_files" in slots:
            context_parts.append(slots["related_files"])
            breakdown["related_files"] = len(slots["related_files"])
        if "code" in slots:
            context_parts.append(slots["code"])
            breakdown["code"] = len(slots["code"])
        if "docs" in slots:
            context_parts.append(slots["docs"])
            breakdown["docs"] = len(slots["docs"])
        if "config" in slots:
            context_parts.append(slots["config"])
            breakdown["config"] = len(slots["config"])

        if context_parts:
            code_section = "\n\n".join(context_parts)
            prompt_parts.append(
                f"## Repository Code Context — `{repo_name}`\n"
                f"{'=' * 50}\n"
                f"{code_section}\n"
                f"{'=' * 50}"
            )

        prompt_parts.append(f"## Question\n{question}")

        # ── Dynamic Intent-Aware Response Format
        prompt_parts.append(self._get_response_format_for_intent(intent_name))

        prompt = "\n\n".join(prompt_parts)
        estimated_tokens = len(prompt) // _CHARS_PER_TOKEN

        # ── Collect all source files mentioned
        source_files = self._collect_source_files(code_chunks)

        logger.debug(
            "ContextBuilder: slots=%s estimated_tokens=%d intent=%s",
            list(breakdown.keys()),
            estimated_tokens,
            intent_name,
        )

        return BuiltContext(
            system_instruction=self._build_system_instruction(repo_name),
            prompt=prompt,
            estimated_tokens=estimated_tokens,
            source_files=source_files,
            slot_breakdown=breakdown,
        )

    def _filter_deterministic_chunks(
        self,
        chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Deduplicate and preserve sequence of deterministic chunks up to character budget."""
        if not chunks:
            return []
        deduped: List[Dict[str, Any]] = []
        seen_keys = set()
        total_chars = 0
        for ch in chunks:
            meta = ch.get("metadata", {})
            file_path = meta.get("file_path", "")
            chunk_id = meta.get("chunk_id", "")
            start_line = meta.get("start_line", 0)
            end_line = meta.get("end_line", 0)
            content = ch.get("content", "").strip()
            if not content:
                continue
            dedup_key = (
                (file_path, start_line, end_line)
                if (file_path and start_line)
                else (chunk_id or content[:100])
            )
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            if total_chars + len(content) > self.max_chars:
                break
            total_chars += len(content)
            deduped.append(ch)
        return deduped

    def _filter_and_budget_chunks(
        self,
        chunks: List[Dict[str, Any]],
        structured_intelligence: str = "",
    ) -> List[Dict[str, Any]]:
        """Deduplicate and enforce file/chunk budgets on raw candidate chunks.

        Rules:
          1. Deduplicate identical chunks (by file_path + start_line + end_line or content hash).
          2. Check for duplicate content already fully detailed in structured_intelligence.
          3. Limit chunks per file to max_chunks_per_file (default 3).
          4. Limit total unique files to max_files (default 8).
          5. Limit total chunks to max_chunks (default 10).
        """
        if not chunks:
            return []

        deduped: List[Dict[str, Any]] = []
        seen_keys = set()
        file_chunk_counts: Dict[str, int] = {}
        unique_files: set = set()

        struct_lower = (
            structured_intelligence.lower() if structured_intelligence else ""
        )

        for ch in chunks:
            meta = ch.get("metadata", {})
            file_path = meta.get("file_path", "")
            chunk_id = meta.get("chunk_id", "")
            start_line = meta.get("start_line", 0)
            end_line = meta.get("end_line", 0)
            content = ch.get("content", "").strip()

            if not content:
                continue

            # Dedup key
            dedup_key = (
                (file_path, start_line, end_line)
                if (file_path and start_line)
                else (chunk_id or content[:100])
            )
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            # Check if identical snippet is already in structured_intelligence
            if struct_lower and len(content) < 300 and content.lower() in struct_lower:
                continue

            # Check file limits
            if file_path not in unique_files:
                if len(unique_files) >= self.max_files:
                    continue
                unique_files.add(file_path)

            # Check per-file chunk limit
            cur_file_chunks = file_chunk_counts.get(file_path, 0)
            if cur_file_chunks >= self.max_chunks_per_file:
                continue

            # Check total chunk limit
            if len(deduped) >= self.max_chunks:
                break

            file_chunk_counts[file_path] = cur_file_chunks + 1
            deduped.append(ch)

        return deduped

    def _get_response_format_for_intent(self, intent_name: str) -> str:
        """Derive intent-tailored dynamic answer schema."""
        from services.chat.response_schema import ResponseSchemaBuilder

        return ResponseSchemaBuilder.build_format_prompt(intent_name)

    def _build_system_instruction(self, repo_name: str) -> str:
        from services.chat.response_schema import ResponseSchemaBuilder

        return ResponseSchemaBuilder.build_system_instruction(repo_name)

    def _split_chunks_by_tier(
        self, chunks: List[Dict[str, Any]]
    ) -> tuple[str, str, str, str, str]:
        """Split code chunks into requested/related/code/docs/config text blocks."""
        from .retrieval import _get_tier_weight

        requested_blocks: List[str] = []
        related_blocks: List[str] = []
        code_blocks: List[str] = []
        doc_blocks: List[str] = []
        cfg_blocks: List[str] = []

        for chunk in chunks:
            meta = chunk.get("metadata", {})
            file_path = meta.get("file_path", "unknown")
            content = chunk.get("content", "").strip()
            if not content:
                continue

            weight = _get_tier_weight(file_path)
            if weight == 0.0:
                # Lockfile / excluded — never include in any slot
                continue

            # Truncate oversized chunks
            if len(content) > self.max_chunk_chars:
                content = content[: self.max_chunk_chars] + "\n... [truncated]"

            score = chunk.get("_rerank_score", 0.0)
            score_label = f" (score: {score:.3f})" if score else ""

            # Citation fields
            chunk_id = meta.get("chunk_id", "unknown")
            start_line = meta.get("start_line", 0)
            end_line = meta.get("end_line", 0)
            line_label = (
                f", lines: {start_line}-{end_line}" if start_line and end_line else ""
            )

            why_this_file = meta.get("why_this_file", "")
            why_label = f"\nWhy this file: {why_this_file}" if why_this_file else ""

            matched_symbols = meta.get("matched_symbols", "")
            symbol_label = (
                f"\nSymbols defined here: {matched_symbols}" if matched_symbols else ""
            )

            block = (
                f"--- File: `{file_path}` (chunk: {chunk_id}{line_label}){score_label}{why_label}{symbol_label} ---\n"
                f"```\n{content}\n```"
            )

            # Categorize the chunk
            why_this_file_lower = why_this_file.lower()
            if (
                "matched exact path" in why_this_file_lower
                or "matched exact filename" in why_this_file_lower
            ):
                requested_blocks.append(block)
            elif (
                "contains requested symbol" in why_this_file_lower
                or "referenced by architecture graph" in why_this_file_lower
            ):
                related_blocks.append(block)
            else:
                if weight >= 1.0:
                    code_blocks.append(block)
                elif weight >= 0.5:
                    doc_blocks.append(block)
                else:
                    cfg_blocks.append(block)

        return (
            "\n\n".join(requested_blocks),
            "\n\n".join(related_blocks),
            "\n\n".join(code_blocks),
            "\n\n".join(doc_blocks),
            "\n\n".join(cfg_blocks),
        )

    def _enforce_budget(self, slots: Dict[str, str]) -> Dict[str, str]:
        """Trim slots to stay within max_chars, removing from lowest priority."""
        priority_order = [
            "architecture",
            "structured_intelligence",
            "requested_file",
            "related_files",
            "code",
            "docs",
            "config",
        ]

        total = sum(len(v) for v in slots.values())
        if total <= self.max_chars:
            return slots

        # Trim from lowest priority first
        for key in reversed(priority_order):
            if total <= self.max_chars:
                break
            if key in slots:
                excess = total - self.max_chars
                current = slots[key]
                if len(current) <= excess:
                    # Remove entire slot
                    total -= len(current)
                    del slots[key]
                    logger.debug("ContextBuilder: removed slot '%s' (budget)", key)
                else:
                    # Truncate
                    slots[key] = (
                        current[: len(current) - excess]
                        + "\n... [context trimmed for token budget]"
                    )
                    total = sum(len(v) for v in slots.values())
                    logger.debug("ContextBuilder: trimmed slot '%s' (budget)", key)

        return slots

    def _collect_source_files(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """Deduplicated list of file paths from chunks."""
        seen: Dict[str, None] = {}
        for chunk in chunks:
            fp = chunk.get("metadata", {}).get("file_path", "")
            if fp:
                seen[fp] = None
        return list(seen.keys())
