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

    _FUNCTION_PATTERN = re.compile(r"\b([a-z_]\w*)\s*\(\)")

    _CLASS_SYMBOL_PATTERN = re.compile(
        r"\b([A-Z][a-zA-Z0-9_]*(?:Service|Detector|Resolver|Engine|Store|Pipeline|Context|Manager|Analyzer|Builder|Router|Factory|State|Machine|Graph)?)\b"
    )

    _COMMON_STOP_WORDS = {
        "Explain",
        "Describe",
        "Show",
        "What",
        "How",
        "Why",
        "Where",
        "Who",
        "When",
        "The",
        "Is",
        "Of",
        "To",
        "And",
        "In",
        "File",
        "Class",
        "Function",
        "Method",
        "Service",
        "Router",
        "Module",
        "Python",
        "TypeScript",
        "JavaScript",
        "GitHub",
        "API",
        "URL",
        "JSON",
        "HTML",
        "CSS",
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

        # 1. Explicit File Path match (e.g. backend/dependencies.py, backend/routers/chat.py, retrieval_pipeline.py)
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

        # 2. Method call match (e.g. RepositoryAnalyzer.analyze, Service.authenticate)
        method_matches = self._METHOD_PATTERN.findall(q_clean)
        if method_matches:
            cls_name, method_name = method_matches[0]
            if cls_name not in self._COMMON_STOP_WORDS:
                full_method = f"{cls_name}.{method_name}"
                return ExplicitEntityResult(
                    has_explicit_entity=True,
                    entity_type="METHOD",
                    entity_name=full_method,
                    target_file=None,
                    target_symbol=full_method,
                    confidence=0.98,
                )

        # 3. Explicit function with parentheses (e.g. validate_llm_providers())
        func_matches = self._FUNCTION_PATTERN.findall(q_clean)
        if func_matches:
            func_name = func_matches[0]
            if len(func_name) > 3 and func_name not in ("show", "describe", "explain"):
                return ExplicitEntityResult(
                    has_explicit_entity=True,
                    entity_type="FUNCTION",
                    entity_name=func_name,
                    target_file=None,
                    target_symbol=func_name,
                    confidence=0.97,
                )

        # 4. Explicit Class / Service / Component symbol match (e.g. ConversationContext, TopicSwitchDetector, GraphRAGService)
        class_matches = self._CLASS_SYMBOL_PATTERN.findall(q_clean)
        if class_matches:
            for symbol in class_matches:
                if symbol not in self._COMMON_STOP_WORDS and len(symbol) > 3:
                    entity_type = "SERVICE" if symbol.endswith("Service") else "CLASS"
                    return ExplicitEntityResult(
                        has_explicit_entity=True,
                        entity_type=entity_type,
                        entity_name=symbol,
                        target_file=None,
                        target_symbol=symbol,
                        confidence=0.95,
                    )

        # 5. Dotted module path match (e.g. backend.dependencies, services.chat)
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
