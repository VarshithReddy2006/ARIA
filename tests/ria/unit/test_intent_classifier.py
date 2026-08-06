"""Unit tests for IntentClassifierService (Phase 3)."""

from __future__ import annotations


from ria.application.intent_classifier import IntentClassifierService


def test_intent_classifier_service() -> None:
    svc = IntentClassifierService()

    i1 = svc.classify_intent("How to fix this null bug in main?")
    assert i1.intent_type == "find_bug"
    assert "bug" in i1.keywords

    i2 = svc.classify_intent("Trace dependency chain for Service")
    assert i2.intent_type == "trace_dependency"

    i3 = svc.classify_intent("Perform architecture review")
    assert i3.intent_type == "architecture_review"

    i4 = svc.classify_intent("hello world")
    assert i4.intent_type == "explain_code"
