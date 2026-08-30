"""Question Novelty Scoring & Entity Grounding — Phase 12.

Calculates multi-dimensional novelty scores for candidate follow-up questions,
strictly rejecting generic questions, duplicates, and conversational regressions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Set

logger = logging.getLogger(__name__)

# Patterns that flag a question as too generic or repository-agnostic
_GENERIC_PATTERNS = [
    r"how does this repository work",
    r"how does the backend work",
    r"what are the main risks",
    r"what else should i inspect",
    r"are there any other files",
    r"can you tell me more",
    r"how to improve this code",
    r"what best practices are followed",
    r"is there any documentation",
    r"how do dependencies work",
]


@dataclass
class FollowUpCandidate:
    """A scored candidate follow-up prompt."""

    prompt: str
    target_entity: Optional[str] = None
    novelty_score: float = 0.0
    strategy: str = "general"
    depth_level: int = 1
    rejection_reason: Optional[str] = None


class QuestionNoveltyScorer:
    """Scores candidate questions to select the highest-novelty, entity-grounded prompts."""

    @classmethod
    def score_candidate(
        cls,
        candidate_text: str,
        current_question: str,
        conversation_history: List[dict],
        explored_entities: Set[str],
        unresolved_aspects: List[str],
        current_depth: int = 1,
    ) -> FollowUpCandidate:
        """Compute holistic novelty score for a candidate question."""
        prompt = candidate_text.strip()
        low_prompt = prompt.lower()

        # 1. Reject generic patterns
        for pat in _GENERIC_PATTERNS:
            if re.search(pat, low_prompt):
                return FollowUpCandidate(
                    prompt=prompt,
                    novelty_score=-100.0,
                    rejection_reason="Matches generic template pattern",
                )

        # 2. Reject questions without concrete entities or technical specificity
        has_entity = (
            bool(
                re.search(
                    r"[\w\-\./]+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|md|pkl|onnx|h5|pt)",
                    prompt,
                )
            )
            or bool(re.search(r"`[\w\.\(\)/]+`", prompt))
            or bool(re.search(r"/\w+", prompt))
            or bool(re.search(r"\b[A-Za-z0-9_]+\(\)", prompt))
        )
        if not has_entity:
            # Check if mentions specific repo concepts
            if not any(
                k in low_prompt
                for k in [
                    "schema",
                    "pipeline",
                    "caller",
                    "validation",
                    "blast radius",
                    "fixture",
                    "endpoint",
                ]
            ):
                return FollowUpCandidate(
                    prompt=prompt,
                    novelty_score=-50.0,
                    rejection_reason="Lacks concrete repository entity or technical specificity",
                )

        # 3. Check similarity with current question and past turns
        low_current = current_question.lower()
        if cls._jaccard_similarity(low_prompt, low_current) > 0.65:
            return FollowUpCandidate(
                prompt=prompt,
                novelty_score=-80.0,
                rejection_reason="Too similar to current question",
            )

        for turn in conversation_history:
            prev_content = (turn.get("content") or "").lower()
            if cls._jaccard_similarity(low_prompt, prev_content) > 0.60:
                return FollowUpCandidate(
                    prompt=prompt,
                    novelty_score=-80.0,
                    rejection_reason="Duplicate of earlier conversation turn",
                )

        # Base score
        score = 60.0

        # Entity bonuses
        extracted_entities = cls._extract_entities(prompt)
        novel_entities = [e for e in extracted_entities if e not in explored_entities]
        if novel_entities:
            score += 25.0 * min(len(novel_entities), 2)
        elif extracted_entities:
            score += 15.0

        if any(
            e.endswith((".pkl", ".onnx", ".pt", ".h5", ".joblib"))
            for e in extracted_entities
        ):
            score += 20.0

        # Unresolved thread relevance
        for unres in unresolved_aspects:
            overlap = set(unres.lower().split()) & set(low_prompt.split())
            if len(overlap) >= 2:
                score += 15.0
                break

        # Depth alignment (higher depth questions favored as turn count increases)
        if current_depth >= 4 and any(
            k in low_prompt
            for k in ["caller", "break if", "blast radius", "test", "fixture", "modify"]
        ):
            score += 15.0
        elif current_depth <= 3 and any(
            k in low_prompt for k in ["how", "does", "feature", "pipeline", "route"]
        ):
            score += 10.0

        return FollowUpCandidate(
            prompt=prompt,
            target_entity=extracted_entities[0] if extracted_entities else None,
            novelty_score=score,
            depth_level=current_depth,
        )

    @staticmethod
    def _jaccard_similarity(s1: str, s2: str) -> float:
        w1 = set(re.findall(r"\w+", s1))
        w2 = set(re.findall(r"\w+", s2))
        if not w1 or not w2:
            return 0.0
        return len(w1 & w2) / len(w1 | w2)

    @staticmethod
    def _extract_entities(text: str) -> List[str]:
        entities = []
        for m in re.findall(
            r"[\w\-\./]+\.(?:py|js|ts|tsx|jsx|json|yaml|yml|md|pkl|onnx|h5|pt)", text
        ):
            entities.append(m)
        for m in re.findall(r"`([\w\.\(\)/]+)`", text):
            entities.append(m)
        for m in re.findall(r"\b([A-Za-z0-9_]+\(\))", text):
            entities.append(m)
        return list(dict.fromkeys(entities))
