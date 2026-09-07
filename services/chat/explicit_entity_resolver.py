"""Explicit Entity Resolver — Standalone component extracting explicit repository entities.

Analyzes raw questions before follow-up detection to extract explicitly referenced:
  - File paths (e.g. backend/dependencies.py, backend/routers/chat.py)
  - Dotted modules (e.g. backend.dependencies, services.chat)
  - Classes & Interfaces (e.g. ConversationContext, TopicSwitchDetector, GraphRAGService)
  - Functions & Methods (e.g. validate_llm_providers, RepositoryAnalyzer.analyze)
  - Services, Routers, Packages

Guarantees that explicit repository entity mentions take immediate priority over previous conversation context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class ExplicitEntityResult:
    """Immutable result of explicit entity resolution."""

    has_explicit_entity: bool
    entity_type: str  # "FILE", "MODULE", "CLASS", "FUNCTION", "METHOD", "SYMBOL", "ROUTER", "SERVICE", "NONE"
    entity_name: str
    target_file: Optional[str]
    target_symbol: Optional[str]
    confidence: float


class ExplicitEntityResolver:
    """Service detecting explicit repository entities in raw user questions."""

    _FILE_PATH_PATTERN = re.compile(
        r"\b([a-zA-Z0-9_\-\./\\]+\.(?:py|ts|tsx|js|jsx|java|go|rs|md|toml|json|yml))\b",
        re.I,
    )

    _MODULE_PATTERN = re.compile(
        r"\b([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)\b"
    )

    _METHOD_PATTERN = re.compile(r"\b([A-Z]\w*)\.([a-z_]\w*)(?:\s*\(\))?")

    _FUNCTION_PATTERN = re.compile(r"\b([a-zA-Z_]\w*)\s*\(\)")

    # Explicit backticked code tokens (e.g. `ProviderManager`, `handle`, `get_provider`)
    _CODE_SPAN_PATTERN = re.compile(r"`([a-zA-Z0-9_\-\./\\]+)`")

    # Strict PascalCase/CamelCase (at least one lowercase followed by uppercase transition)
    # OR word ending in an architectural suffix with at least 2 prefix characters
    _PASCAL_CASE_PATTERN = re.compile(r"\b([A-Z][a-z0-9]+(?:[A-Z0-9][a-zA-Z0-9]*)+)\b")
    _ARCH_SUFFIX_PATTERN = re.compile(
        r"\b([A-Z][a-zA-Z0-9]{2,}(?:Service|Detector|Resolver|Engine|Store|Pipeline|Context|Manager|Analyzer|Builder|Router|Factory|StateMachine|Graph|Repository|Client|Controller|Adapter|Middleware|Provider))\b"
    )

    # Snake-case code identifiers with underscores (e.g. get_provider, validate_llm_providers)
    _SNAKE_CASE_PATTERN = re.compile(r"\b([a-z0-9]+_[a-z0-9_]+)\b")

    _COMMON_STOP_WORDS = {
        # Conversational & Question words
        "explain",
        "describe",
        "show",
        "what",
        "how",
        "why",
        "where",
        "who",
        "when",
        "which",
        "the",
        "is",
        "are",
        "was",
        "were",
        "of",
        "to",
        "and",
        "in",
        "on",
        "at",
        "for",
        "with",
        "about",
        "from",
        "file",
        "class",
        "function",
        "method",
        "service",
        "router",
        "module",
        "package",
        "code",
        "repo",
        "repository",
        "can",
        "could",
        "would",
        "should",
        "does",
        "do",
        "did",
        "please",
        "find",
        "look",
        "see",
        "check",
        # Common English verbs / nouns that may appear capitalized at start of sentence
        "handle",
        "handles",
        "handling",
        "handler",
        "handled",
        "process",
        "processes",
        "processing",
        "processed",
        "route",
        "routes",
        "routing",
        "router",
        "routed",
        "build",
        "builds",
        "building",
        "builder",
        "built",
        "execute",
        "executes",
        "executing",
        "executed",
        "execution",
        "dispatch",
        "dispatches",
        "dispatching",
        "dispatched",
        "run",
        "runs",
        "running",
        "manage",
        "manages",
        "managing",
        "manager",
        "managed",
        "support",
        "supports",
        "supporting",
        "supported",
        "work",
        "works",
        "working",
        "worked",
        "use",
        "uses",
        "using",
        "used",
        "get",
        "gets",
        "getting",
        "set",
        "sets",
        "setting",
        "call",
        "calls",
        "calling",
        "called",
        "send",
        "sends",
        "sending",
        "sent",
        "test",
        "tests",
        "testing",
        "tested",
        "failover",
        "failure",
        "failures",
        "fail",
        "fails",
        "failed",
        "error",
        "errors",
        "exception",
        "exceptions",
        "prompt",
        "context",
        "provider",
        "providers",
        "model",
        "models",
        # Tech terms & Acronyms
        "aria",
        "llm",
        "nim",
        "ai",
        "api",
        "url",
        "uri",
        "json",
        "html",
        "css",
        "rest",
        "http",
        "https",
        "sse",
        "sql",
        "ui",
        "ux",
        "qa",
        "ci",
        "cd",
        "prd",
        "sdd",
        "dag",
        "python",
        "typescript",
        "javascript",
        "github",
        "docker",
        "qdrant",
        "chroma",
        "chromadb",
        "fastapi",
        "pydantic",
        "google",
        "deepseek",
        "gemini",
        "openai",
        "anthropic",
        "nvidia",
    }

    def resolve(self, question: str) -> ExplicitEntityResult:
        """Inspect raw question and return explicit entity result if present."""
        if not question or not question.strip():
            return ExplicitEntityResult(
                has_explicit_entity=False,
                entity_type="NONE",
                entity_name="",
                target_file=None,
                target_symbol=None,
                confidence=0.0,
            )

        q_clean = question.strip()

        # 1. Backticked code spans take highest priority (e.g. `services/chat/provider_manager.py`, `ProviderManager`, `handle`)
        code_spans = self._CODE_SPAN_PATTERN.findall(q_clean)
        _BACKTICK_IGNORE = {
            "the",
            "a",
            "an",
            "is",
            "of",
            "to",
            "and",
            "in",
            "it",
            "this",
            "that",
        }
        if code_spans:
            for span in code_spans:
                span_clean = span.strip()
                if not span_clean:
                    continue
                if "/" in span_clean or "\\" in span_clean or "." in span_clean:
                    file_path = span_clean.replace("\\", "/")
                    entity_type = "ROUTER" if "router" in file_path.lower() else "FILE"
                    return ExplicitEntityResult(
                        has_explicit_entity=True,
                        entity_type=entity_type,
                        entity_name=file_path,
                        target_file=file_path,
                        target_symbol=None,
                        confidence=0.99,
                    )
                if span_clean.lower() not in _BACKTICK_IGNORE:
                    return ExplicitEntityResult(
                        has_explicit_entity=True,
                        entity_type="SYMBOL",
                        entity_name=span_clean,
                        target_file=None,
                        target_symbol=span_clean,
                        confidence=0.98,
                    )

        # 2. Explicit File Path match (e.g. backend/dependencies.py, backend/routers/chat.py, retrieval_pipeline.py)
        file_matches = self._FILE_PATH_PATTERN.findall(q_clean)
        if file_matches:
            file_path = file_matches[0].replace("\\", "/")
            entity_type = "ROUTER" if "router" in file_path.lower() else "FILE"
            return ExplicitEntityResult(
                has_explicit_entity=True,
                entity_type=entity_type,
                entity_name=file_path,
                target_file=file_path,
                target_symbol=None,
                confidence=0.99,
            )

        # 3. Method call match (e.g. RepositoryAnalyzer.analyze, Service.authenticate)
        method_matches = self._METHOD_PATTERN.findall(q_clean)
        if method_matches:
            cls_name, method_name = method_matches[0]
            if cls_name.lower() not in self._COMMON_STOP_WORDS:
                full_method = f"{cls_name}.{method_name}"
                return ExplicitEntityResult(
                    has_explicit_entity=True,
                    entity_type="METHOD",
                    entity_name=full_method,
                    target_file=None,
                    target_symbol=full_method,
                    confidence=0.98,
                )

        # 4. Explicit function with parentheses (e.g. validate_llm_providers(), get_provider())
        func_matches = self._FUNCTION_PATTERN.findall(q_clean)
        if func_matches:
            func_name = func_matches[0]
            if len(func_name) > 3 and func_name.lower() not in {
                "show",
                "describe",
                "explain",
            }:
                return ExplicitEntityResult(
                    has_explicit_entity=True,
                    entity_type="FUNCTION",
                    entity_name=func_name,
                    target_file=None,
                    target_symbol=func_name,
                    confidence=0.97,
                )

        # 5. Explicit PascalCase / CamelCase / Suffix-matching Class / Service symbol
        # Check both PascalCase and Architecture Suffix patterns
        candidate_classes = set(self._PASCAL_CASE_PATTERN.findall(q_clean)) | set(
            self._ARCH_SUFFIX_PATTERN.findall(q_clean)
        )
        for symbol in candidate_classes:
            if symbol.lower() not in self._COMMON_STOP_WORDS and len(symbol) > 3:
                entity_type = "SERVICE" if symbol.endswith("Service") else "CLASS"
                return ExplicitEntityResult(
                    has_explicit_entity=True,
                    entity_type=entity_type,
                    entity_name=symbol,
                    target_file=None,
                    target_symbol=symbol,
                    confidence=0.95,
                )

        # 6. Snake_case function/identifier (e.g. get_provider, intelligent_retrieve)
        # Require presence of an underscore and non-stopword status
        snake_matches = self._SNAKE_CASE_PATTERN.findall(q_clean)
        if snake_matches:
            for snake_sym in snake_matches:
                if (
                    snake_sym.lower() not in self._COMMON_STOP_WORDS
                    and len(snake_sym) > 3
                ):
                    return ExplicitEntityResult(
                        has_explicit_entity=True,
                        entity_type="FUNCTION",
                        entity_name=snake_sym,
                        target_file=None,
                        target_symbol=snake_sym,
                        confidence=0.94,
                    )

        # 7. Dotted module path match (e.g. backend.dependencies, services.chat)
        module_matches = self._MODULE_PATTERN.findall(q_clean)
        if module_matches:
            for mod in module_matches:
                parts = mod.split(".")
                if len(parts) >= 2 and all(p.islower() for p in parts):
                    derived_file = "/".join(parts) + ".py"
                    return ExplicitEntityResult(
                        has_explicit_entity=True,
                        entity_type="MODULE",
                        entity_name=mod,
                        target_file=derived_file,
                        target_symbol=None,
                        confidence=0.94,
                    )

        return ExplicitEntityResult(
            has_explicit_entity=False,
            entity_type="NONE",
            entity_name="",
            target_file=None,
            target_symbol=None,
            confidence=0.0,
        )
