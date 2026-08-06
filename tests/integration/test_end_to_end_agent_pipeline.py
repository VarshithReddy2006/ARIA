"""End-to-End Integration Test for Iteration 10 Agent Runtime Pipeline & Performance Targets."""

import subprocess
import time
from pathlib import Path

from ria.agent import (
    AgentRuntime,
    CheckpointManager,
    ExecutionContextManager,
    ExecutionEngine,
    GoalInterpreter,
    Planner,
    ReflectionEngine,
    TaskGraphEngine,
    TaskScheduler,
    ToolRegistry,
    VerificationEngine,
)
from ria.application.agent import AgentApplicationService, ExecuteGoalCommandDTO, ExecuteGoalUseCase
from ria.application.context import ContextApplicationService
from ria.application.index import (
    FileDiscovery,
    IndexBatchAssembler,
    IndexPipeline,
    IndexUnitBuilder,
    LanguageDetection,
    RepositoryScanner,
)
from ria.application.knowledge import KnowledgeApplicationService
from ria.application.query import QueryApplicationService
from ria.application.resolution import ResolveAndStoreCommand, ResolveAndStoreUseCase, ResolutionApplicationService
from ria.application.search import SearchApplicationService
from ria.application.sync import (
    RegisterRepositoryCommand,
    RegisterRepositoryUseCase,
    RepositorySyncService,
    SynchronizeRepositoryCommand,
    SynchronizeRepositoryUseCase,
)
from ria.config import Container, Settings
from ria.context import (
    CallExpander,
    ContextBuilder,
    ContextEngine,
    ContextExpander,
    ContextSerializer,
    Deduplicator,
    DependencyExpander,
    RankingEngine as ContextRankingEngine,
    ReferenceExpander,
    TokenBudgetOptimizer,
)
from ria.domain.index.value_objects import Language
from ria.infrastructure.storage import SQLiteFactStoreAdapter
from ria.interfaces.mcp import MCPServer
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
from ria.plugins import PluginLoader, PluginRegistry, JavaScriptTreeSitterPlugin, PythonTreeSitterPlugin, TypeScriptTreeSitterPlugin
from ria.query import QueryCache, QueryEngine, QueryExecutor, QueryOptimizer, QueryPlanner
from ria.resolution import (
    JavaScriptLanguageResolver,
    LanguageResolverRegistry,
    PythonLanguageResolver,
    ResolutionEngine,
    TypeScriptLanguageResolver,
)
from ria.search import (
    AutocompleteEngine,
    HighlightEngine,
    RankingEngine as SearchRankingEngine,
    SearchCache,
    SearchEngine,
    SearchFilterEngine,
    SearchIndex,
    SearchPlanner,
)


def test_full_agent_runtime_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Pipeline & Performance Verification Test for Iteration 10 Agent Runtime:
    Git -> Sync -> Index -> Resolve -> FactStore -> Services -> MCP -> ToolRegistry -> AgentRuntime.
    """
    # 1. Git origin
    origin_dir = tmp_path / "agent_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True)
    subprocess.run(["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True)

    py_file = origin_dir / "agent_core.py"
    py_file.write_text("class AgentCore:\n    def run(self) -> None:\n        pass\n")

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(["git", "commit", "-m", "Agent test commit"], cwd=origin_dir, check=True)

    # 2. Container & Services Setup
    settings = Settings.create_testing(tmp_path)
    container = Container.create(settings)

    sync_service = RepositorySyncService(
        git_client=container.git_client,
        registry=container.repository_registry,
        lock_manager=container.repository_lock,
        workspace_manager=container.workspace_manager,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )
    reg_use_case = RegisterRepositoryUseCase(sync_service)
    sync_use_case = SynchronizeRepositoryUseCase(sync_service)

    status_dto = reg_use_case.execute(RegisterRepositoryCommand(remote_url=str(origin_dir), name="agent_origin"))
    sync_dto = sync_use_case.execute(SynchronizeRepositoryCommand(repo_id=status_dto.repo_id))
    assert sync_dto.is_success

    # Index & Resolve
    discovery = FileDiscovery(filesystem=container.filesystem)
    lang_detect = LanguageDetection(filesystem=container.filesystem)
    scanner = RepositoryScanner(discovery, lang_detect, container.filesystem, container.hashing)

    plugin_registry = PluginRegistry()
    loader = PluginLoader(plugin_registry)
    loader.load_plugin_class(PythonTreeSitterPlugin)
    loader.load_plugin_class(TypeScriptTreeSitterPlugin)
    loader.load_plugin_class(JavaScriptTreeSitterPlugin)

    builder = IndexUnitBuilder()
    assembler = IndexBatchAssembler()

    pipeline = IndexPipeline(
        scanner=scanner,
        parser_registry=plugin_registry,
        unit_builder=builder,
        batch_assembler=assembler,
        registry=container.repository_registry,
        workspace_manager=container.workspace_manager,
        filesystem=container.filesystem,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )

    resolver_registry = LanguageResolverRegistry()
    resolver_registry.register_resolver(Language.PYTHON, PythonLanguageResolver())
    resolver_registry.register_resolver(Language.TYPESCRIPT, TypeScriptLanguageResolver())
    resolver_registry.register_resolver(Language.JAVASCRIPT, JavaScriptLanguageResolver())

    res_engine = ResolutionEngine(resolver_registry=resolver_registry)
    fact_store = SQLiteFactStoreAdapter(db_path=tmp_path / "fact_store.db")

    res_service = ResolutionApplicationService(
        index_pipeline=pipeline,
        resolution_engine=res_engine,
        fact_store=fact_store,
        registry=container.repository_registry,
        clock=container.clock,
        logger=container.logger,
        metrics=container.metrics,
    )
    res_use_case = ResolveAndStoreUseCase(res_service)
    fact_dto = res_use_case.execute(ResolveAndStoreCommand(repo_id=status_dto.repo_id))
    assert fact_dto.is_success

    # Search, Query, Context, Knowledge Application Services
    search_engine = SearchEngine(SearchPlanner(), SearchIndex(), SearchRankingEngine(), SearchFilterEngine(), HighlightEngine(), AutocompleteEngine(), SearchCache())
    query_engine = QueryEngine(QueryPlanner(), QueryExecutor(), QueryOptimizer(), QueryCache())

    search_service = SearchApplicationService(search_engine, fact_store, container.repository_registry, container.clock, container.logger, container.metrics)
    query_service = QueryApplicationService(query_engine, fact_store, container.repository_registry, container.clock, container.logger, container.metrics)

    expander = ContextExpander(ReferenceExpander(), CallExpander(), DependencyExpander())
    context_builder = ContextBuilder(expander, ContextRankingEngine(), Deduplicator(), TokenBudgetOptimizer())
    context_engine = ContextEngine(context_builder, ContextSerializer())
    context_service = ContextApplicationService(context_engine, search_engine, query_engine, fact_store, container.repository_registry, container.clock, container.logger, container.metrics)

    prov_reg = ProviderRegistry()
    prov_reg.register_provider("mock", MockLLMProvider())
    orchestrator = KnowledgeOrchestrator(IntentAnalyzer(), PromptBuilder(), prov_reg, ResponseValidator(), ResponseFormatter(), ConversationManager())
    knowledge_engine = KnowledgeEngine(orchestrator)
    knowledge_service = KnowledgeApplicationService(knowledge_engine, context_service, container.repository_registry, container.clock, container.logger, container.metrics)

    # 3. Setup MCP Server as Tool Registry adapter
    mcp_server = MCPServer(sync_service, search_service, query_service, context_service, knowledge_service)
    tool_registry = ToolRegistry()
    for tool_meta in mcp_server.list_tools():
        t_name = tool_meta["name"]
        tool_registry.register_tool(t_name, lambda params, name=t_name: mcp_server.invoke_tool(name, params))

    # 4. Setup Agent Runtime
    goal_interpreter = GoalInterpreter()
    planner = Planner()
    graph_engine = TaskGraphEngine()
    scheduler = TaskScheduler()
    ctx_mgr = ExecutionContextManager()
    executor = ExecutionEngine(graph_engine, scheduler, ctx_mgr)
    reflection_engine = ReflectionEngine()
    verification_engine = VerificationEngine()
    checkpoint_mgr = CheckpointManager()

    agent_runtime = AgentRuntime(planner, executor, tool_registry, reflection_engine, verification_engine, checkpoint_mgr)
    agent_app_service = AgentApplicationService(agent_runtime, goal_interpreter, container.repository_registry, container.clock, container.logger, container.metrics)
    execute_goal_uc = ExecuteGoalUseCase(agent_app_service)

    # Warmup
    _ = execute_goal_uc.execute(ExecuteGoalCommandDTO(repo_id=status_dto.repo_id, goal_description="Explain AgentCore architecture"))

    # 5. Measure End-to-End Performance
    t0 = time.perf_counter()
    res_dto = execute_goal_uc.execute(ExecuteGoalCommandDTO(repo_id=status_dto.repo_id, goal_description="Explain AgentCore architecture"))
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert res_dto.is_success
    assert res_dto.total_tasks == 4
    assert "executed successfully" in res_dto.answer_text
    assert elapsed_ms < 50.0, f"Agent Runtime execution latency {elapsed_ms:.2f}ms exceeded target threshold"
