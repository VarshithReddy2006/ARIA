"""Tests for ImpactDebugger and confidence tier classifications."""

from models.phase2 import ConfidenceTier, EvidenceStrength
from services.impact_debugger import ImpactDebugger


def test_impact_debugger_create_detail():
    detail = ImpactDebugger.create_detail(
        file_path="services/auth.py",
        confidence_tier=ConfidenceTier.HIGH,
        evidence_strength=EvidenceStrength.LEVEL_1_EXACT_SYMBOL,
        reason="Defines AuthService class",
        propagation_path=["services/auth.py"],
        target_symbols=["AuthService.login"],
        verifications={"is_seed": True, "has_symbol_def": True},
    )

    assert detail.file_path == "services/auth.py"
    assert detail.confidence_tier == ConfidenceTier.HIGH
    assert detail.confidence_score == 1.0
    assert detail.evidence_strength == EvidenceStrength.LEVEL_1_EXACT_SYMBOL
    assert "AuthService" in detail.reason
    assert detail.verifications["is_seed"] is True


def test_impact_debugger_explanation_format():
    detail = ImpactDebugger.create_detail(
        file_path="routers/api.py",
        confidence_tier=ConfidenceTier.HIGH,
        evidence_strength=EvidenceStrength.LEVEL_2_EXACT_CALL,
        reason="Calls target function AuthService.login directly at line 42",
        propagation_path=["services/auth.py", "routers/api.py"],
        target_symbols=["AuthService.login"],
    )

    explanation = ImpactDebugger.format_explanation(detail)
    assert "HIGH CONFIDENCE" in explanation
    assert "routers/api.py" in explanation
    assert "LEVEL_2_EXACT_CALL" in explanation
    assert "services/auth.py" in explanation
    assert "routers/api.py" in explanation


def test_impact_debugger_full_debug_report():
    detail1 = ImpactDebugger.create_detail(
        file_path="services/auth.py",
        confidence_tier=ConfidenceTier.HIGH,
        evidence_strength=EvidenceStrength.LEVEL_1_EXACT_SYMBOL,
        reason="Root definition",
        propagation_path=["services/auth.py"],
    )
    detail2 = ImpactDebugger.create_detail(
        file_path="utils/helpers.py",
        confidence_tier=ConfidenceTier.LOW,
        evidence_strength=EvidenceStrength.LEVEL_6_MODULE_DEPENDENCY,
        reason="Transitive import only",
        propagation_path=["services/auth.py", "utils/helpers.py"],
    )

    report = ImpactDebugger.format_full_debug_report([detail1, detail2])
    assert "ARIA IMPACT ANALYSIS DEBUGGER REPORT" in report
    assert "[HIGH CONFIDENCE FILES (1)]" in report
    assert "[LOW CONFIDENCE FILES (1)]" in report
    assert "services/auth.py" in report
    assert "utils/helpers.py" in report
