"""Engineering Reasoning Engine (ERE).

Implements the modular sub-engine reasoning architecture: EvidenceAnalyzer,
RuleEngine, ConfidenceEngine, and RecommendationPlanner, coordinated by
the EngineeringReasoningEngine orchestrator.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from models.retrieval import RepositoryRetrievalContext
from models.reasoning import (
    Evidence,
    Hypothesis,
    Contradiction,
    DecisionOption,
    DecisionAnalysis,
    Recommendation,
    ConfidenceBreakdown,
    ReasoningResult,
    ReasoningChainNode,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-Engine 1: Evidence Analyzer
# ---------------------------------------------------------------------------

class EvidenceAnalyzer:
    """Transforms loose ContextReferences into strongly-typed Evidence findings."""

    def analyze(self, context: RepositoryRetrievalContext) -> List[Evidence]:
        evidence_list = []
        for idx, ref in enumerate(context.references):
            # Calculate evidence quality based on structured type
            quality = 1.0
            if ref.type == "file":
                quality = 1.0
                desc = f"Verified source file presence: {ref.properties.get('path', ref.id)}"
            elif ref.type == "symbol":
                quality = 0.9
                desc = f"Verified symbol '{ref.properties.get('name', ref.id)}' in file {ref.properties.get('file_path')}"
            elif ref.type == "health":
                quality = 0.85
                desc = f"Repository health report: Overall Score {ref.properties.get('overall_score')}"
            elif ref.type == "compliance":
                quality = 0.85
                desc = f"Repository compliance status: {ref.properties.get('status')}"
            elif ref.type == "document":
                quality = 0.6  # less structured than raw code
                desc = f"Documentation match: {ref.properties.get('file_path', ref.id)}"
            else:
                quality = 0.5
                desc = f"Retrieved reference of type: {ref.type}"

            evidence_list.append(
                Evidence(
                    id=f"EVD-{idx + 1:03d}",
                    type=ref.type,
                    source=ref.source or "unknown",
                    reference_id=ref.id,
                    description=desc,
                    quality_score=quality,
                )
            )
        return evidence_list


# ---------------------------------------------------------------------------
# Pluggable RulePacks & Sub-Engine 2: Rule Engine
# ---------------------------------------------------------------------------

class RulePack(ABC):
    """Base interface for pluggable engineering reasoning rules."""

    @abstractmethod
    def evaluate(
        self,
        evidence: List[Evidence],
        hypotheses: List[Hypothesis],
        contradictions: List[Contradiction],
    ) -> None:
        """Evaluates rules against evidence, formulating hypotheses and contradictions."""
        pass


class ArchitectureRulePack(RulePack):
    """Rule pack evaluating circular dependency and structural coupling smells."""

    def evaluate(
        self,
        evidence: List[Evidence],
        hypotheses: List[Hypothesis],
        contradictions: List[Contradiction],
    ) -> None:
        # Check for cycles
        cycle_evidence = [e for e in evidence if e.type == "architecture" and e.reference_id.endswith("::architecture")]
        for ev in cycle_evidence:
            hypotheses.append(
                Hypothesis(
                    id="HYP-ARCH-01",
                    description="The repository layout contains circular dependency cycles.",
                    status="validated",
                    supporting_evidence=[ev.id],
                )
            )

        # Check for high coupling
        dep_evidence = [e for e in evidence if e.source == "dependency_expansion"]
        if len(dep_evidence) >= 8:
            hypotheses.append(
                Hypothesis(
                    id="HYP-ARCH-02",
                    description="High coupling detected in key module dependencies.",
                    status="validated",
                    supporting_evidence=[e.id for e in dep_evidence],
                )
            )


class BugRulePack(RulePack):
    """Rule pack evaluating bug risk areas based on call chains and symbol definition states."""

    def evaluate(
        self,
        evidence: List[Evidence],
        hypotheses: List[Hypothesis],
        contradictions: List[Contradiction],
    ) -> None:
        # Check for high blast radius call chains
        symbol_evidence = [e for e in evidence if e.type == "symbol" and e.reference_id.split("::")[-1].startswith("_")]
        if symbol_evidence:
            hypotheses.append(
                Hypothesis(
                    id="HYP-BUG-01",
                    description="Private internal helpers are heavily queried, indicating leaky abstraction risks.",
                    status="validated",
                    supporting_evidence=[e.id for e in symbol_evidence],
                )
            )


class ComplianceRulePack(RulePack):
    """Rule pack evaluating license presence and warning status compliance."""

    def evaluate(
        self,
        evidence: List[Evidence],
        hypotheses: List[Hypothesis],
        contradictions: List[Contradiction],
    ) -> None:
        compliance_evidence = [e for e in evidence if e.type == "compliance"]
        for ev in compliance_evidence:
            if "warning" in ev.description.lower() or "non-compliant" in ev.description.lower():
                hypotheses.append(
                    Hypothesis(
                        id="HYP-COMP-01",
                        description="Codebase has unresolved compliance warnings.",
                        status="validated",
                        supporting_evidence=[ev.id],
                    )
                )

            # Contradiction: Compliance report has warnings, but overall score is high
            health_evs = [e for e in evidence if e.type == "health"]
            if health_evs and ("warning" in ev.description.lower() or "non-compliant" in ev.description.lower()):
                contradictions.append(
                    Contradiction(
                        id="CON-COMP-01",
                        description="Compliance report warns of risks, but Health score indicates high quality.",
                        conflicting_evidence=[ev.id, health_evs[0].id],
                        severity="medium",
                    )
                )


class RuleEngine:
    """Coordinates pluggable RulePacks to evaluate hypotheses and contradictions."""

    def __init__(self, rule_packs: Optional[List[RulePack]] = None) -> None:
        self.rule_packs = rule_packs if rule_packs is not None else [
            ArchitectureRulePack(),
            BugRulePack(),
            ComplianceRulePack(),
        ]

    def evaluate(self, evidence: List[Evidence]) -> tuple[List[Hypothesis], List[Contradiction]]:
        hypotheses: List[Hypothesis] = []
        contradictions: List[Contradiction] = []

        for pack in self.rule_packs:
            try:
                pack.evaluate(evidence, hypotheses, contradictions)
            except Exception as e:
                logger.error("RulePack %s failed during evaluation: %s", pack.__class__.__name__, e, exc_info=True)

        return hypotheses, contradictions


# ---------------------------------------------------------------------------
# Sub-Engine 3: Confidence Engine
# ---------------------------------------------------------------------------

class ConfidenceEngine:
    """Computes separated trust scores for evidence quality, reasoning, and recommendations."""

    def calculate(self, evidence: List[Evidence], contradictions: List[Contradiction], validated_count: int) -> ConfidenceBreakdown:
        # 1. Evidence Quality
        if evidence:
            avg_quality = sum(e.quality_score for e in evidence) / len(evidence) * 100.0
        else:
            avg_quality = 80.0 # default baseline

        # 2. Reasoning Confidence
        # Lose 25% for every contradiction detected
        reasoning_score = max(10.0, 100.0 - (len(contradictions) * 25.0))

        # 3. Recommendation Confidence
        # Higher if we have validated hypotheses and high evidence quality
        recommendation_score = (avg_quality + reasoning_score) / 2.0
        if validated_count == 0:
            recommendation_score = max(10.0, recommendation_score - 20.0)

        return ConfidenceBreakdown(
            evidence_quality=round(avg_quality, 1),
            reasoning_confidence=round(reasoning_score, 1),
            recommendation_confidence=round(recommendation_score, 1),
        )


# ---------------------------------------------------------------------------
# Sub-Engine 4: Recommendation Planner & Decision Analysis
# ---------------------------------------------------------------------------

class RecommendationPlanner:
    """Generates trade-offs and decision options before planning final Recommendations."""

    def plan(
        self,
        repo_name: str,
        validated_hypotheses: List[Hypothesis],
        confidence_breakdown: ConfidenceBreakdown,
    ) -> tuple[Optional[DecisionAnalysis], List[Recommendation]]:
        if not validated_hypotheses:
            return None, []

        # Find targets from supporting evidence
        # Default target
        target = repo_name
        for hyp in validated_hypotheses:
            if hyp.supporting_evidence:
                target = hyp.supporting_evidence[0]
                break

        # 1. Build Decision Analysis evaluating trade-offs
        options = [
            DecisionOption(
                name="Proactive Refactoring",
                description="Aggressively split highly coupled modules and resolve cycle dependencies.",
                pros=["Improves long-term hygiene", "Reduces blast radius"],
                cons=["Takes significant development effort", "Risk of regression"],
                recommendation_confidence=confidence_breakdown.recommendation_confidence,
            ),
            DecisionOption(
                name="Defensive Wrapping",
                description="Encapsulate highly coupled elements behind simple API interfaces or adapters.",
                pros=["Faster implementation time", "Minimal regression footprint"],
                cons=["Increases indirect layers", "Hides structural coupling rather than fixing it"],
                recommendation_confidence=max(10.0, confidence_breakdown.recommendation_confidence - 10.0),
            )
        ]
        decision = DecisionAnalysis(
            problem_statement=f"Code coupling or cycles detected affecting target: {target}",
            options=options,
        )

        # 2. Plan Recommendation DTOs
        recs = []
        for idx, hyp in enumerate(validated_hypotheses):
            rec_type = "refactor"
            if "compliance" in hyp.id.lower() or "comp" in hyp.id.lower():
                rec_type = "compliance_fix"

            recs.append(
                Recommendation(
                    id=f"REC-{idx + 1:03d}",
                    type=rec_type,
                    target=target,
                    priority="high" if confidence_breakdown.recommendation_confidence > 70 else "medium",
                    estimated_effort="4h" if rec_type == "refactor" else "1h",
                    reasoning_chain=[hyp.id],
                )
            )

        return decision, recs


# ---------------------------------------------------------------------------
# Orchestrator: Engineering Reasoning Engine
# ---------------------------------------------------------------------------

class EngineeringReasoningEngine:
    """lightweight orchestrator coordinating sub-engine reasoning stages."""

    def __init__(
        self,
        analyzer: Optional[EvidenceAnalyzer] = None,
        rule_engine: Optional[RuleEngine] = None,
        confidence_engine: Optional[ConfidenceEngine] = None,
        planner: Optional[RecommendationPlanner] = None,
    ) -> None:
        """Initialise ERE Orchestrator."""
        self.analyzer = analyzer or EvidenceAnalyzer()
        self.rule_engine = rule_engine or RuleEngine()
        self.confidence_engine = confidence_engine or ConfidenceEngine()
        self.planner = planner or RecommendationPlanner()

    def reason(
        self,
        repo_name: str,
        question: str,
        policy: str,
        context: RepositoryRetrievalContext,
    ) -> ReasoningResult:
        """Transforms RepositoryRetrievalContext evidence into a composed structured ReasoningResult."""
        # 1. Analyze evidence
        evidence = self.analyzer.analyze(context)

        # 2. Evaluate RulePacks (Hypotheses and Contradictions)
        # Configure rulepacks based on policy if custom, else use defaults
        hypotheses, contradictions = self.rule_engine.evaluate(evidence)

        # 3. Calculate Confidence metrics
        validated_hyps = [h for h in hypotheses if h.status == "validated"]
        confidence_breakdown = self.confidence_engine.calculate(
            evidence,
            contradictions,
            len(validated_hyps),
        )

        # 4. Plan Recommendations & Decision options
        decision_analysis, recommendations = self.planner.plan(
            repo_name,
            validated_hyps,
            confidence_breakdown,
        )

        # Create confidence explanation string
        explanation = (
            f"Evidence Quality is {confidence_breakdown.evidence_quality}% based on retrieved reference structures. "
            f"Reasoning chain consistency score is {confidence_breakdown.reasoning_confidence}% with "
            f"{len(contradictions)} contradiction(s) found. Actionable recommendation trust score is "
            f"{confidence_breakdown.recommendation_confidence}%."
        )

        # Convert findings to graph nodes internally
        graph_nodes = []
        # Add Evidence nodes
        for e in evidence:
            graph_nodes.append(
                ReasoningChainNode(
                    id=e.id,
                    type="evidence",
                    label=e.description,
                    relationships=[],
                )
            )
        # Add Hypothesis nodes (link to supporting evidence)
        for h in hypotheses:
            relationships = [{"target": eid, "type": "SUPPORTS"} for eid in h.supporting_evidence]
            graph_nodes.append(
                ReasoningChainNode(
                    id=h.id,
                    type="hypothesis",
                    label=h.description,
                    relationships=relationships,
                )
            )
        # Add Recommendation nodes (link to hypothesis reasoning chains)
        for r in recommendations:
            relationships = [{"target": hid, "type": "IMPLIES"} for hid in r.reasoning_chain]
            graph_nodes.append(
                ReasoningChainNode(
                    id=r.id,
                    type="recommendation",
                    label=f"Recommend: {r.type} targeting {r.target}",
                    relationships=relationships,
                )
            )

        return ReasoningResult(
            repository_name=repo_name,
            question=question,
            policy=policy,
            evidence=evidence,
            hypotheses=hypotheses,
            contradictions=contradictions,
            decision_analysis=decision_analysis,
            recommendations=recommendations,
            confidence=confidence_breakdown,
            confidence_explanation=explanation,
            reasoning_graph_nodes=graph_nodes,
        )
