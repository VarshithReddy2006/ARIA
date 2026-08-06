"""Unit tests for C8 Knowledge Layer domain models, intent analyzer, prompt builder, provider registry, validator, conversation manager, formatter, and orchestrator."""

import pytest
from ria.domain.context import (
    Citation,
    ContextMetadata,
    ContextPackage,
    ContextSection,
    ContextSnippet,
    RankingScore,
)
from ria.domain.index.value_objects import FilePath
from ria.domain.knowledge import (
    ConversationId,
    ConversationTurn,
    IntentType,
    InvalidKnowledgeRequestError,
    KnowledgeRequest,
)
from ria.domain.resolution import SymbolMoniker
from ria.knowledge import (
    ConversationManager,
    IntentAnalyzer,
    KnowledgeEngine,
    KnowledgeOrchestrator,
    MockLLMProvider,
    PromptBuilder,
    ProviderRegistry,
    ResponseFormatter,
    ResponseValidator,
)


def test_knowledge_domain_value_objects() -> None:
    cid = ConversationId(value="conv_123")
    assert cid.value == "conv_123"

    with pytest.raises(InvalidKnowledgeRequestError):
        ConversationId(value="")

    req = KnowledgeRequest(conversation_id=cid, question="What is UserService?")
    assert req.question == "What is UserService?"

    with pytest.raises(InvalidKnowledgeRequestError):
        KnowledgeRequest(conversation_id=cid, question="")


def test_intent_analyzer_all_intents() -> None:
    analyzer = IntentAnalyzer()
    pkg = ContextPackage(
        package_id="p1",
        question="q",
        sections=(),
        references=(),
        metadata=ContextMetadata(0, 0, 0, 4000),
    )

    assert analyzer.analyze_intent("What is UserService?", pkg) == IntentType.DEFINITION
    assert (
        analyzer.analyze_intent("Explain the architecture", pkg)
        == IntentType.ARCHITECTURE
    )
    assert (
        analyzer.analyze_intent("How does login flow work?", pkg)
        == IntentType.CODE_FLOW
    )
    assert (
        analyzer.analyze_intent("Who calls hash_password?", pkg)
        == IntentType.CALL_GRAPH
    )
    assert (
        analyzer.analyze_intent("What depends on auth.py?", pkg)
        == IntentType.DEPENDENCY_ANALYSIS
    )
    assert (
        analyzer.analyze_intent("Investigate bug in login", pkg)
        == IntentType.BUG_INVESTIGATION
    )
    assert (
        analyzer.analyze_intent("How to refactor user module?", pkg)
        == IntentType.REFACTORING
    )
    assert (
        analyzer.analyze_intent("Generate documentation for auth", pkg)
        == IntentType.DOCUMENTATION
    )
    assert (
        analyzer.analyze_intent("Compare python versus typescript resolvers", pkg)
        == IntentType.COMPARISON
    )
    assert (
        analyzer.analyze_intent("What is the impact of changing user_id?", pkg)
        == IntentType.IMPACT_ANALYSIS
    )


def test_prompt_builder_and_provider_registry() -> None:
    builder = PromptBuilder()
    fp = FilePath(relative_path="auth.py")
    moniker = SymbolMoniker(value="repo:auth.py:global:login")
    cit = Citation(
        repo_name="repo",
        commit_sha="a" * 40,
        file_path=fp,
        module_name="auth",
        symbol_moniker=moniker,
        start_line=1,
        end_line=5,
    )
    score = RankingScore(priority=1, score_value=1.0, category="Definition")
    snip = ContextSnippet(
        snippet_id="s1",
        content="def login(): pass",
        citation=cit,
        score=score,
        estimated_tokens=10,
    )
    sec = ContextSection(title="Definition", snippets=(snip,))
    pkg = ContextPackage(
        package_id="p1",
        question="login",
        sections=(sec,),
        references=(),
        metadata=ContextMetadata(1, 1, 10, 4000),
    )

    prompt_pkg = builder.build_prompt("login", pkg, IntentType.DEFINITION)
    assert "RIA" in prompt_pkg.system_prompt
    assert "login" in prompt_pkg.user_prompt

    registry = ProviderRegistry()
    mock_prov = MockLLMProvider()
    registry.register_provider("mock", mock_prov)

    assert registry.get_provider("mock") == mock_prov


def test_conversation_manager_and_formatter() -> None:
    conv_mgr = ConversationManager()
    cid = ConversationId(value="c1")

    assert conv_mgr.get_conversation(cid) is None

    turn = ConversationTurn(user_message="hi", assistant_response="hello")
    ctx = conv_mgr.add_turn(cid, turn)
    assert len(ctx.turns) == 1

    conv_mgr.clear_conversation(cid)
    assert conv_mgr.get_conversation(cid) is None


def test_knowledge_orchestrator_pipeline() -> None:
    intent_analyzer = IntentAnalyzer()
    prompt_builder = PromptBuilder()
    registry = ProviderRegistry()
    registry.register_provider("mock", MockLLMProvider())

    validator = ResponseValidator()
    formatter = ResponseFormatter()
    conv_mgr = ConversationManager()

    orchestrator = KnowledgeOrchestrator(
        intent_analyzer, prompt_builder, registry, validator, formatter, conv_mgr
    )
    engine = KnowledgeEngine(orchestrator)

    pkg = ContextPackage(
        package_id="p1",
        question="auth",
        sections=(),
        references=(),
        metadata=ContextMetadata(0, 0, 0, 4000),
    )
    req = KnowledgeRequest(
        conversation_id=ConversationId(value="c1"), question="What is auth?"
    )

    resp = engine.answer_question(req, pkg)
    assert resp.is_success
    assert resp.answer.validation.grounding_score.is_grounded
    assert "Grounded Answer" in resp.formatted_content
