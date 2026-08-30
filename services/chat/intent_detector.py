"""Intent Detector — Phase 3.

Classifies user questions into structured engineering intents so the IntentRouter
and ContextBuilder can dynamically tailor repository intelligence and response schemas.

Design:
  - IntentDetector is an abstract interface (pluggable by design).
  - RuleBasedIntentDetector is the production implementation.
  - Zero LLM calls — pure regex/keyword matching for latency-free classification.
  - IntentResult carries the detected intent, confidence, extracted entities,
    and metadata to assist the router and follow-up engine.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent enumeration
# ---------------------------------------------------------------------------


class Intent(str, Enum):
    """Supported intent types for repository chat questions."""

    API_FLOW = "API_FLOW"
    API_SURFACE = "API_SURFACE"
    ARCHITECTURE = "ARCHITECTURE"
    FILE_EXPLANATION = "FILE_EXPLANATION"
    SYMBOL = "SYMBOL"
    SYMBOL_EXPLANATION = "SYMBOL_EXPLANATION"
    DEPENDENCY = "DEPENDENCY"
    CIRCULAR_DEPENDENCY = "CIRCULAR_DEPENDENCY"
    CALL_GRAPH = "CALL_GRAPH"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    CHANGE_PLANNING = "CHANGE_PLANNING"
    DEBUGGING = "DEBUGGING"
    READING_ORDER = "READING_ORDER"
    HEALTH = "HEALTH"
    DEAD_CODE = "DEAD_CODE"
    SECURITY = "SECURITY"
    GIT_HISTORY = "GIT_HISTORY"
    PR_RISK = "PR_RISK"
    GENERAL_QA = "GENERAL_QA"
    UNKNOWN = "UNKNOWN"


@dataclass
class IntentResult:
    """Result of intent classification.

    Attributes:
        intent:     Detected intent category.
        confidence: 0.0–1.0 confidence in the classification.
        entities:   Extracted code entities (class names, function names, etc.)
                    mentioned in the question — used for pronoun injection.
        keywords:   The specific keywords that triggered this classification.
        file_paths: Concrete file paths mentioned in the question.
        endpoints:  HTTP endpoints mentioned in the question.
    """

    intent: Intent
    confidence: float = 1.0
    entities: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    file_paths: List[str] = field(default_factory=list)
    endpoints: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"IntentResult(intent={self.intent.value}, "
            f"confidence={self.confidence:.2f}, "
            f"entities={self.entities}, "
            f"files={self.file_paths}, "
            f"keywords={self.keywords})"
        )


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class IntentDetector(ABC):
    """Abstract interface for intent classifiers.

    Concrete implementations can be rule-based, ML-based, or LLM-based.
    The IntentRouter always calls detect() and never cares about implementation.
    """

    @abstractmethod
    def detect(self, question: str) -> IntentResult:
        """Classify the user question into an intent."""


# ---------------------------------------------------------------------------
# Rule-based implementation
# ---------------------------------------------------------------------------

_RULE_TABLE: List[tuple] = [
    # Change Planning
    (
        re.compile(
            r"\b(how (?:would|can|to|do) (?:I|we) (?:add|implement|refactor|create|introduce|migrate|replace)|"
            r"what files (?:would|to|should) (?:I|we) (?:need to |have to )?(?:modify|change|touch|update)|"
            r"plan (?:for|to)|implementation (?:plan|order|steps)|refactor.*to)\b",
            re.I,
        ),
        Intent.CHANGE_PLANNING,
        0.95,
    ),
    # Impact analysis — what breaks, blast radius, ripple effect
    (
        re.compile(
            r"\b(blast.?radius|what.?breaks|what.?changes|affected.?files?"
            r"|ripple.?effect|change.?propagat|downstream|risk.?of.?changing"
            r"|side.?effects?.of|what.?depends.?on)\b",
            re.I,
        ),
        Intent.IMPACT_ANALYSIS,
        0.92,
    ),
    # Debugging / Root-cause
    (
        re.compile(
            r"\b(debug|root.?cause|why is (?:it|this) failing|error|exception|stack.?trace"
            r"|bug|crash|failure point|where does (?:it|this) break|troubleshoot)\b",
            re.I,
        ),
        Intent.DEBUGGING,
        0.92,
    ),
    # Circular dependency
    (
        re.compile(
            r"\b(circular|cycle|cyclic|circular.depend|import.loop|dependency.cycle)\b",
            re.I,
        ),
        Intent.CIRCULAR_DEPENDENCY,
        0.95,
    ),
    # Dependencies
    (
        re.compile(
            r"\b(dependencies|packages?|external libraries|third.?party|requirements|npm packages?|pip packages?)\b",
            re.I,
        ),
        Intent.DEPENDENCY,
        0.90,
    ),
    # Dead Code
    (
        re.compile(
            r"\b(dead.?code|unused (?:functions?|files?|symbols?|methods?|variables?)|unreferenced|uncalled)\b",
            re.I,
        ),
        Intent.DEAD_CODE,
        0.92,
    ),
    # Git History / Churn
    (
        re.compile(
            r"\b(git|commit|history|recent(ly)? changed|who wrote|when was.*changed|changelog|blame|churn)\b",
            re.I,
        ),
        Intent.GIT_HISTORY,
        0.90,
    ),
    # PR Risk / Drift
    (
        re.compile(
            r"\b(pr risk|pull request|review risk|architecture drift|drift|merge risk)\b",
            re.I,
        ),
        Intent.PR_RISK,
        0.90,
    ),
    # Health / Quality / Security
    (
        re.compile(
            r"\b(health|quality|maintainability|bottlenecks?|vulnerabilit(y|ies)|security score|code smell|health score)\b",
            re.I,
        ),
        Intent.HEALTH,
        0.90,
    ),
    # Reading order / onboarding
    (
        re.compile(
            r"\b(reading.?order|reading.?path|read.?first|onboard|getting.?started|where.?to.?start"
            r"|start.?reading|best.?order|understand.?codebase|new.?developer|introduction.?to)\b",
            re.I,
        ),
        Intent.READING_ORDER,
        0.92,
    ),
    # Call graph — callers, callees, who calls what
    (
        re.compile(
            r"\b(call.?graph|who.?calls|what.?calls|callers?.of|callees?.of"
            r"|call.?chain|call.?hierarchy|invocations?.of|called.?by|calls.?into)\b",
            re.I,
        ),
        Intent.CALL_GRAPH,
        0.90,
    ),
    # API Flow & API Surface
    (
        re.compile(
            r"\b(api.?surface|public.?api|endpoints?|routes?|exported|exports?"
            r"|public.?methods?|rest.?api|http.?methods?|openapi|swagger"
            r"|fastapi.?route|flask.?route|express.?route|inference pipeline|api flow|request flow)\b",
            re.I,
        ),
        Intent.API_SURFACE,
        0.92,
    ),
    # File explanation
    (
        re.compile(
            r"\b(what does (?:file |module )?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|c|cpp|h|json|md)\b|"
            r"explain (?:file |module )?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java)\b|"
            r"what does `?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java)`? do|"
            r"role of `?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java)`?)\b",
            re.I,
        ),
        Intent.FILE_EXPLANATION,
        0.92,
    ),
    # Symbol lookup / explanation
    (
        re.compile(
            r"\b(where.?is.+defined|where.?is.+located|find.?definition|where.?is.?defined"
            r"|find.?the.?class|what.?is.?the.?definition|defined.?in|declaration.?of"
            r"|locate.?the|definition.?of|show.?me.?the.?class|show.?the.?function|"
            r"what does (?:function|class|method|symbol) `?\w+`? do)\b",
            re.I,
        ),
        Intent.SYMBOL,
        0.88,
    ),
    # Architecture — entry points, structure, layers, overview
    (
        re.compile(
            r"\b(architect|overview|entry.?point|module.?structure"
            r"|design.?of|high.?level|system.?layout"
            r"|how.?is.+organis|how.?is.+organized"
            r"|system.?design|monolith|microservice|code.?structure"
            r"|project.?structure|data flow|execution flow|pipeline)\b",
            re.I,
        ),
        Intent.ARCHITECTURE,
        0.90,
    ),
    # General Q&A fallback
    (
        re.compile(
            r"\b(how.?does|what.?does|explain|describe|tell.?me.?about|summarize"
            r"|summarise|can.?you.?explain|help.?me.?understand|what.?is.?the.?purpose"
            r"|why.?does)\b",
            re.I,
        ),
        Intent.GENERAL_QA,
        0.70,
    ),
]

_ENTITY_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,}(?:\(\))?)\b")
_FILE_PATTERN = re.compile(
    r"\b([\w./\\-]+\.(py|ts|tsx|js|jsx|java|go|rs|rb|php|cs|cpp|c|h|yml|yaml|json|md|pkl|onnx|pt|bin))\b",
    re.I,
)
_ENDPOINT_PATTERN = re.compile(
    r"(?:GET|POST|PUT|DELETE|PATCH)?\s*(/\w+(?:/[\w-]+)*)", re.I
)


class RuleBasedIntentDetector(IntentDetector):
    """Production intent detector using compiled regex rules."""

    def detect(self, question: str) -> IntentResult:
        if not question or not question.strip():
            return IntentResult(intent=Intent.UNKNOWN, confidence=0.0)

        q = question.strip()
        matched_keywords: List[str] = []
        matched_intent: Optional[Intent] = None
        matched_confidence: float = 0.0

        for pattern, intent, confidence in _RULE_TABLE:
            m = pattern.search(q)
            if m:
                matched_intent = intent
                matched_confidence = confidence
                matched_keywords = [m.group(0)]
                break

        # Check if question directly targets a file path without explicit verbs
        file_matches = [m[0] for m in _FILE_PATTERN.findall(q)]
        if matched_intent in (None, Intent.GENERAL_QA, Intent.UNKNOWN) and file_matches:
            matched_intent = Intent.FILE_EXPLANATION
            matched_confidence = 0.85

        if matched_intent is None:
            matched_intent = Intent.UNKNOWN
            matched_confidence = 0.5

        # Extract code entities (ignoring common stopwords)
        stopwords = {
            "how",
            "what",
            "where",
            "when",
            "why",
            "who",
            "which",
            "does",
            "work",
            "this",
            "that",
            "from",
            "with",
            "into",
            "explain",
            "describe",
            "show",
            "tell",
            "about",
            "file",
            "code",
            "repo",
            "repository",
            "module",
            "system",
            "component",
        }
        raw_entities = _ENTITY_PATTERN.findall(q)
        entities = [
            e
            for e in dict.fromkeys(raw_entities)
            if e.lower() not in stopwords and len(e) > 2
        ]

        endpoints = [m for m in _ENDPOINT_PATTERN.findall(q) if m.startswith("/")]

        return IntentResult(
            intent=matched_intent,
            confidence=matched_confidence,
            entities=entities,
            keywords=matched_keywords,
            file_paths=file_matches,
            endpoints=endpoints,
        )
