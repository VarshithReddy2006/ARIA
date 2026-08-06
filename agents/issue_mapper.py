"""Issue Mapping Agent module.

Responsible for taking GitHub issues, identifying files relevant to those issues,
and generating step-by-step implementation plans to solve/resolve them.

MVP mode: maximum 2 LLM calls per request.
  Call 1 — parse_and_rank:  parse issue + rerank retrieved files in one prompt.
  Call 2 — generate_plan:   produce implementation plan grounded in chunk content.
  Evaluator disabled — confidence derived from retrieval distance scores.

AI provider: DeepSeek V4 Flash via NVIDIA NIM (ProviderFactory).
"""

import asyncio
import json
import hashlib
import logging
import os
from typing import List, Dict, Any, Optional

from services.embedding_service import EmbeddingService
from services.arch_context_service import ArchContextService
from services.issue_retrieval_service import IssueRetrievalService
from services.llm import ProviderFactory, BaseLLMProvider
from memory.chroma_store import ChromaStore

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join("data", "issue_cache.json")


def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to load issue cache: %s", exc)
    return {}


def save_cache(cache: dict) -> None:
    # Bound cache size to prevent unbounded memory/disk growth
    while len(cache) > 500:
        first_key = next(iter(cache))
        cache.pop(first_key, None)
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)
    except Exception as exc:
        logger.warning("Failed to save issue cache: %s", exc)


ISSUE_CACHE = load_cache()


def _distance_confidence(chunks: List[dict]) -> int:
    """Derive a 0-100 confidence score from retrieval distance scores.

    Lower Chroma L2 distance → higher similarity → higher confidence.
    Returns an integer in [40, 95].
    """
    if not chunks:
        return 40
    distances = [c.get("distance", 1.0) for c in chunks]
    avg_dist = sum(distances) / len(distances)
    # Convert distance to similarity: sim = 1 / (1 + dist), scale to 40-95
    similarity = 1.0 / (1.0 + avg_dist)
    return int(40 + similarity * 55)


def _run_async(coro):
    """Run a coroutine from synchronous code, handling both running and idle loops."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class IssueMapper:
    """Agent that maps GitHub issues to relevant codebase files and creates implementation plans.

    MVP mode uses exactly 2 LLM calls:
      1. parse_and_rank  — issue parsing + file relevance ranking (merged)
      2. generate_plan   — grounded implementation plan
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        chroma_store: Optional[ChromaStore] = None,
        client: Any = None,  # ignored — legacy Gemini arg
        arch_context_service: Optional[ArchContextService] = None,
        issue_retrieval_service: Optional[IssueRetrievalService] = None,
        provider: Optional[BaseLLMProvider] = None,
    ) -> None:
        self._provider = provider or ProviderFactory.get_provider()
        self.embedding_service = embedding_service or EmbeddingService()

        from core.config import settings

        self.chroma_store = chroma_store or ChromaStore(
            persist_directory=settings.chroma_db_path
        )
        self.arch_context_service = arch_context_service or ArchContextService()
        self.issue_retrieval_service = issue_retrieval_service or IssueRetrievalService(
            embedding_service=self.embedding_service,
            chroma_store=self.chroma_store,
        )

    # ------------------------------------------------------------------
    # LLM Call 1: parse issue + rank files in a single prompt
    # ------------------------------------------------------------------

    async def _parse_and_rank_async(
        self,
        issue_text: str,
        chunks: List[dict],
    ) -> dict:
        """Single LLM call: extract issue metadata AND rank retrieved files.

        Returns:
            {
                "summary": str,
                "issue_type": "bug"|"feature"|"refactor",
                "keywords": [...],
                "affected_domains": [...],
                "files": [{"path": str, "score": float}, ...]
            }
        """
        # Build candidate block — 800 chars per chunk for meaningful context
        candidate_lines = []
        for idx, c in enumerate(chunks):
            meta = c.get("metadata", {})
            path = meta.get("file_path", "unknown")
            content = c.get("content", "")
            candidate_lines.append(f"[{idx}] {path}\n{content[:800]}")
        candidates_str = (
            "\n\n---\n\n".join(candidate_lines) if candidate_lines else "No candidates."
        )

        system_instr = (
            "You are an expert software engineer. You will receive a GitHub issue and a set of "
            "retrieved codebase snippets. Perform two tasks in one response:\n"
            "TASK 1 — Parse the issue: extract a summary, type, keywords, and affected domains.\n"
            "TASK 2 — Rank the retrieved snippets: identify up to 10 unique file paths most "
            "relevant to solving the issue. Assign each a relevance score 0.0-1.0.\n"
            "Base file ranking ONLY on the provided snippets — do not invent file paths.\n"
            "Return a single JSON object matching this schema exactly:\n"
            "{\n"
            '  "summary": "concise one-line description of the issue",\n'
            '  "issue_type": "bug",\n'
            '  "keywords": ["keyword1", "keyword2"],\n'
            '  "affected_domains": ["auth", "frontend"],\n'
            '  "files": [\n'
            '    {"path": "exact/path/from/snippets", "score": 0.95}\n'
            "  ]\n"
            "}"
        )
        prompt = (
            f"GitHub Issue:\n{issue_text}\n\n"
            f"Retrieved codebase snippets:\n"
            f"================================\n"
            f"{candidates_str}\n"
            f"================================\n\n"
            "Return the JSON response now."
        )

        raw = await self._provider.generate(
            prompt=prompt,
            system_instruction=system_instr,
            response_mime_type="application/json",
        )
        data = json.loads(raw)
        data.setdefault("summary", issue_text.split("\n")[0][:120])
        data.setdefault("issue_type", "bug")
        data.setdefault("keywords", [])
        data.setdefault("affected_domains", [])
        data.setdefault("files", [])
        return data

    # ------------------------------------------------------------------
    # LLM Call 2: generate grounded implementation plan
    # ------------------------------------------------------------------

    async def _generate_plan_async(
        self,
        issue_text: str,
        summary: str,
        relevant_files: List[str],
        arch_block: str,
        chunks: List[dict],
    ) -> dict:
        """Single LLM call: generate a step-by-step implementation plan.

        Grounded by injecting retrieved chunk content into the prompt.
        """
        arch_section = f"\n{arch_block}\n" if arch_block else ""

        # Build deduped context block — 600 chars per unique file
        seen_paths: set = set()
        context_lines = []
        for c in chunks:
            meta = c.get("metadata", {})
            path = meta.get("file_path", "")
            content = c.get("content", "")
            if path and path not in seen_paths:
                seen_paths.add(path)
                context_lines.append(f"--- {path} ---\n{content[:600]}")

        context_block = (
            (
                "\nRetrieved codebase context:\n"
                "=======================================================\n"
                + "\n\n".join(context_lines)
                + "\n=======================================================\n"
            )
            if context_lines
            else ""
        )

        file_paths_str = (
            ", ".join(relevant_files) if relevant_files else "none identified"
        )

        system_instr = (
            "You are a Repo Intelligence Agent. Generate a detailed, repository-specific "
            "implementation plan for the given GitHub issue.\n"
            "Rules:\n"
            "- Use ONLY files and logic present in the retrieved codebase context.\n"
            "- Do NOT invent files, functions, or modules not present in the context.\n"
            "- Identify affected components from: "
            "['Authentication', 'API Layer', 'Database', 'Frontend', 'Services', 'Models'].\n"
            "- Estimate complexity as 'low', 'medium', or 'high'.\n"
            "Return a JSON object matching this schema exactly:\n"
            "{\n"
            '  "affected_components": ["Services"],\n'
            '  "complexity": "medium",\n'
            '  "steps": [\n'
            "    {\n"
            '      "step_number": 1,\n'
            '      "description": "Detailed, specific description referencing actual code",\n'
            '      "files_to_modify": ["exact/file/path"]\n'
            "    }\n"
            "  ],\n"
            '  "risk_areas": ["describe risks"],\n'
            '  "dependencies": []\n'
            "}"
        )

        prompt = (
            f"{arch_section}"
            f"GitHub Issue:\n{issue_text}\n\n"
            f"Issue Summary: {summary}\n"
            f"Most Relevant Files: {file_paths_str}\n"
            f"{context_block}\n"
            "Generate the implementation plan strictly based on the retrieved context above."
        )

        raw = await self._provider.generate(
            prompt=prompt,
            system_instruction=system_instr,
            response_mime_type="application/json",
        )
        return json.loads(raw)

    # ------------------------------------------------------------------
    # Distance-score fallback for file ranking (no LLM call)
    # ------------------------------------------------------------------

    @staticmethod
    def _rank_by_distance(chunks: List[dict], top_n: int = 10) -> List[dict]:
        """Rank files by retrieval distance when LLM ranking is unavailable."""
        file_scores: Dict[str, float] = {}
        for chunk in chunks:
            meta = chunk.get("metadata", {})
            path = meta.get("file_path", "")
            dist = chunk.get("distance", 1.0)
            score = 1.0 / (1.0 + dist)
            if path:
                file_scores[path] = max(file_scores.get(path, 0.0), score)
        sorted_files = sorted(file_scores.items(), key=lambda x: x[1], reverse=True)[
            :top_n
        ]
        return [{"path": p, "score": round(s, 3)} for p, s in sorted_files]

    @staticmethod
    def _infer_components_from_paths(file_paths: List[str]) -> List[str]:
        """Infer affected_components from file paths using keyword heuristics.

        Maps path segments to the standard component vocabulary without an LLM call.
        """
        _RULES: List[tuple] = [
            (
                {
                    "auth",
                    "login",
                    "signup",
                    "oauth",
                    "token",
                    "password",
                    "session",
                    "jwt",
                },
                "Authentication",
            ),
            (
                {
                    "controller",
                    "router",
                    "route",
                    "endpoint",
                    "api",
                    "handler",
                    "middleware",
                },
                "API Layer",
            ),
            (
                {
                    "model",
                    "schema",
                    "entity",
                    "migration",
                    "prisma",
                    "sequelize",
                    "mongoose",
                },
                "Models",
            ),
            (
                {
                    "service",
                    "repository",
                    "dao",
                    "store",
                    "manager",
                    "util",
                    "helper",
                    "lib",
                },
                "Services",
            ),
            (
                {
                    "database",
                    "db",
                    "sqlite",
                    "postgres",
                    "mysql",
                    "mongo",
                    "redis",
                    "chroma",
                },
                "Database",
            ),
            (
                {
                    "frontend",
                    "component",
                    "page",
                    "view",
                    "ui",
                    "react",
                    "jsx",
                    "tsx",
                    "css",
                    "style",
                    "layout",
                    "hook",
                    "store",
                    "context",
                },
                "Frontend",
            ),
        ]
        found: set = set()
        for path in file_paths:
            lower = path.lower().replace("\\", "/")
            segments = set(lower.replace(".", "/").split("/"))
            for keywords, component in _RULES:
                if segments & keywords:
                    found.add(component)
        return sorted(found) or ["Services"]

    @staticmethod
    def _build_fallback_steps(
        relevant_files: List[str],
        chunks: List[dict],
        issue_summary: str,
    ) -> List[Dict[str, Any]]:
        """Build retrieval-grounded fallback steps without an LLM call.

        For each of the top-5 relevant files, pull the most relevant chunk
        content snippet and write a targeted step description from it.
        """
        # Index chunks by file path for fast lookup
        chunk_by_path: Dict[str, str] = {}
        for c in chunks:
            path = c.get("metadata", {}).get("file_path", "")
            content = c.get("content", "").strip()
            if path and path not in chunk_by_path and content:
                # Take first 300 chars — enough to name functions/classes
                chunk_by_path[path] = content[:300]

        steps = []
        for i, file_path in enumerate(relevant_files[:5]):
            snippet = chunk_by_path.get(file_path, "")
            # Extract first meaningful line (function/class/export declaration)
            hint = ""
            for line in snippet.splitlines():
                stripped = line.strip()
                if stripped and any(
                    kw in stripped
                    for kw in (
                        "function",
                        "const ",
                        "class ",
                        "def ",
                        "export",
                        "async ",
                        "router.",
                        "app.",
                        "module.",
                        "describe(",
                    )
                ):
                    hint = stripped[:120]
                    break

            if hint:
                description = (
                    f"In `{file_path}`, locate `{hint}` and apply the fix for: {issue_summary}. "
                    f"Ensure the change handles edge cases such as special characters and "
                    f"validates input before processing."
                )
            else:
                description = (
                    f"Review `{file_path}` for logic related to: {issue_summary}. "
                    f"Apply targeted fix and add input validation for edge cases."
                )

            steps.append(
                {
                    "step_number": i + 1,
                    "description": description,
                    "files_to_modify": [file_path],
                }
            )

        if not steps:
            steps = [
                {
                    "step_number": 1,
                    "description": f"Investigate and resolve: {issue_summary}",
                    "files_to_modify": [],
                }
            ]
        return steps

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def map_issue(self, repo_name: str, issue_title: str, issue_body: str) -> dict:
        """Process a GitHub issue — exactly 2 LLM calls.

        Pipeline:
          [embedding retrieval — no LLM]
          LLM Call 1: parse issue + rank files
          LLM Call 2: generate grounded implementation plan
          [confidence from distance scores — no LLM]
        """
        issue_text = f"{issue_title}\n{issue_body}".strip()

        # ── Retrieval (no LLM) ────────────────────────────────────────
        try:
            chunks = self.issue_retrieval_service.retrieve_issue_context(
                repo_name=repo_name, issue_text=issue_text, limit=20
            )
        except Exception as exc:
            logger.error("Retrieval failed: %s", exc)
            chunks = []

        logger.info(
            "[IssueMapper] Retrieved %d chunks for '%s'", len(chunks), issue_title
        )

        # ── LLM Call 1: parse + rank ──────────────────────────────────
        issue_hash = hashlib.sha256(issue_text.strip().encode()).hexdigest()
        cache_key = f"{repo_name}:v2:{issue_hash}"

        global ISSUE_CACHE
        parsed_and_ranked = ISSUE_CACHE.get(cache_key)

        if parsed_and_ranked:
            logger.info("[IssueMapper] Cache hit for parse+rank.")
        else:
            try:
                parsed_and_ranked = _run_async(
                    self._parse_and_rank_async(issue_text, chunks)
                )
                ISSUE_CACHE[cache_key] = parsed_and_ranked
                save_cache(ISSUE_CACHE)
                logger.info("[IssueMapper] LLM Call 1 complete (parse+rank).")
            except Exception as exc:
                logger.error("LLM Call 1 (parse+rank) failed: %s", exc)
                # Fallback: derive everything from retrieval without LLM
                parsed_and_ranked = {
                    "summary": issue_text.split("\n")[0][:120],
                    "issue_type": "bug",
                    "keywords": [],
                    "affected_domains": self._infer_components_from_paths(
                        [c.get("metadata", {}).get("file_path", "") for c in chunks]
                    ),
                    "files": self._rank_by_distance(chunks),
                }

        scored_files = [f for f in parsed_and_ranked.get("files", []) if f.get("path")]
        # If LLM returned no files, fall back to distance ranking
        if not scored_files:
            scored_files = self._rank_by_distance(chunks)

        relevant_files = [f["path"] for f in scored_files]

        # ── Architecture context (no LLM) ─────────────────────────────
        arch_ctx = self.arch_context_service.get_context(repo_name)
        arch_block = arch_ctx.to_prompt_block()

        # ── LLM Call 2: generate plan ─────────────────────────────────
        try:
            plan_data = _run_async(
                self._generate_plan_async(
                    issue_text,
                    parsed_and_ranked.get("summary", ""),
                    relevant_files,
                    arch_block,
                    chunks,
                )
            )
            logger.info("[IssueMapper] LLM Call 2 complete (plan).")
        except Exception as exc:
            logger.error("LLM Call 2 (plan generation) failed: %s", exc)
            summary = parsed_and_ranked.get("summary", issue_title)
            inferred_components = self._infer_components_from_paths(relevant_files)
            plan_data = {
                "affected_components": inferred_components,
                "complexity": "medium",
                "steps": self._build_fallback_steps(relevant_files, chunks, summary),
                "risk_areas": [
                    "Plan generated from retrieval context — verify before applying"
                ],
                "dependencies": [],
            }

        # ── Confidence from retrieval distance (no LLM) ───────────────
        confidence = _distance_confidence(chunks)
        verified = len(chunks) > 0 and bool(relevant_files)

        sources = sorted(
            {
                c.get("metadata", {}).get("file_path", "")
                for c in chunks
                if c.get("metadata", {}).get("file_path")
            }
        )

        return {
            "issue_summary": parsed_and_ranked.get("summary", ""),
            "issue_type": parsed_and_ranked.get("issue_type", "bug"),
            "relevant_files": relevant_files,
            "affected_components": plan_data.get("affected_components", ["Services"]),
            "implementation_plan": plan_data.get("steps", []),
            "complexity": plan_data.get("complexity", "medium"),
            "confidence": confidence,
            "verified": verified,
            "sources": sources,
        }

    # ------------------------------------------------------------------
    # Legacy public methods — kept for any external callers
    # ------------------------------------------------------------------

    def parse_issue(self, repo_name: str, issue_text: str) -> dict:
        """Legacy single-issue parse (no file ranking). Wraps _parse_and_rank_async."""
        try:
            chunks = self.issue_retrieval_service.retrieve_issue_context(
                repo_name=repo_name, issue_text=issue_text, limit=5
            )
            result = _run_async(self._parse_and_rank_async(issue_text, chunks))
            return result
        except Exception as exc:
            logger.error("parse_issue failed: %s", exc)
            return {
                "summary": issue_text.split("\n")[0][:100],
                "issue_type": "feature",
                "keywords": [],
                "affected_domains": [],
                "files": [],
            }

    def identify_relevant_files(
        self,
        repo_name: str,
        issue_text: str,
        keywords: List[str],
        chunks: Optional[List[dict]] = None,
    ) -> List[dict]:
        """Legacy file ranking. Returns distance-ranked files from provided or fresh chunks."""
        if chunks is None:
            try:
                chunks = self.issue_retrieval_service.retrieve_issue_context(
                    repo_name=repo_name, issue_text=issue_text, limit=20
                )
            except Exception as exc:
                logger.error("Retrieval failed: %s", exc)
                return []
        return self._rank_by_distance(chunks)
