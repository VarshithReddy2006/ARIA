"""End-to-End Integration Test for C9 Developer Interfaces Pipeline & Performance Targets."""

import subprocess
import time
from pathlib import Path

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
from ria.application.resolution import (
    ResolveAndStoreCommand,
    ResolveAndStoreUseCase,
    ResolutionApplicationService,
)
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
from ria.interfaces.cli import CLIRunner
from ria.interfaces.mcp import MCPServer
from ria.interfaces.rest import RESTAPIServer
from ria.interfaces.sdk.python import RIAClient
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
from ria.plugins import (
    PluginLoader,
    PluginRegistry,
    JavaScriptTreeSitterPlugin,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)
from ria.query import (
    QueryCache,
    QueryEngine,
    QueryExecutor,
    QueryOptimizer,
    QueryPlanner,
)
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


def test_full_developer_interfaces_end_to_end_pipeline(tmp_path: Path) -> None:
    """End-to-End Pipeline & Performance Verification Test for C9 Developer Interfaces:
    Git -> Sync -> Index -> Resolve -> FactStore -> Services -> REST / CLI / MCP / SDK.
    """
    # 1. Git origin
    origin_dir = tmp_path / "iface_origin"
    origin_dir.mkdir()
    subprocess.run(["git", "init"], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "config", "user.name", "TestRunner"], cwd=origin_dir, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "runner@test.com"], cwd=origin_dir, check=True
    )

    py_file = origin_dir / "api_service.py"
    py_file.write_text(
        "class APIService:\n    def execute(self) -> str:\n        return 'ok'\n"
    )

    subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Interface test commit"], cwd=origin_dir, check=True
    )

    # 2. Container & Application Services Setup
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

    status_dto = reg_use_case.execute(
        RegisterRepositoryCommand(remote_url=str(origin_dir), name="iface_origin")
    )
    sync_dto = sync_use_case.execute(
        SynchronizeRepositoryCommand(repo_id=status_dto.repo_id)
    )
    assert sync_dto.is_success

    # Index & Resolve
    discovery = FileDiscovery(filesystem=container.filesystem)
    lang_detect = LanguageDetection(filesystem=container.filesystem)
    scanner = RepositoryScanner(
        discovery, lang_detect, container.filesystem, container.hashing
    )

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
    resolver_registry.register_resolver(
        Language.TYPESCRIPT, TypeScriptLanguageResolver()
    )
    resolver_registry.register_resolver(
        Language.JAVASCRIPT, JavaScriptLanguageResolver()
    )

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
    search_engine = SearchEngine(
        SearchPlanner(),
        SearchIndex(),
        SearchRankingEngine(),
        SearchFilterEngine(),
        HighlightEngine(),
        AutocompleteEngine(),
        SearchCache(),
    )
    query_engine = QueryEngine(
        QueryPlanner(), QueryExecutor(), QueryOptimizer(), QueryCache()
    )

    search_service = SearchApplicationService(
        search_engine,
        fact_store,
        container.repository_registry,
        container.clock,
        container.logger,
        container.metrics,
    )
    query_service = QueryApplicationService(
        query_engine,
        fact_store,
        container.repository_registry,
        container.clock,
        container.logger,
        container.metrics,
    )

    expander = ContextExpander(
        ReferenceExpander(), CallExpander(), DependencyExpander()
    )
    context_builder = ContextBuilder(
        expander, ContextRankingEngine(), Deduplicator(), TokenBudgetOptimizer()
    )
    context_engine = ContextEngine(context_builder, ContextSerializer())
    context_service = ContextApplicationService(
        context_engine,
        search_engine,
        query_engine,
        fact_store,
        container.repository_registry,
        container.clock,
        container.logger,
        container.metrics,
    )

    prov_reg = ProviderRegistry()
    prov_reg.register_provider("mock", MockLLMProvider())
    orchestrator = KnowledgeOrchestrator(
        IntentAnalyzer(),
        PromptBuilder(),
        prov_reg,
        ResponseValidator(),
        ResponseFormatter(),
        ConversationManager(),
    )
    knowledge_engine = KnowledgeEngine(orchestrator)
    knowledge_service = KnowledgeApplicationService(
        knowledge_engine,
        context_service,
        container.repository_registry,
        container.clock,
        container.logger,
        container.metrics,
    )

    # 3. Test REST API Server Performance (<5ms request, <1ms health)
    rest_server = RESTAPIServer(
        sync_service, search_service, query_service, context_service, knowledge_service
    )

    t0 = time.perf_counter()
    health_resp = rest_server.handle_request("GET", "/health")
    health_ms = (time.perf_counter() - t0) * 1000.0
    assert health_resp.is_success
    assert health_ms < 1.0, (
        f"Health endpoint overhead {health_ms:.2f}ms exceeded target of 1.0ms"
    )

    t0 = time.perf_counter()
    srch_resp = rest_server.handle_request(
        "POST", "/search", {"repo_id": status_dto.repo_id, "query_text": "APIService"}
    )
    rest_ms = (time.perf_counter() - t0) * 1000.0
    assert srch_resp.is_success
    assert rest_ms < 10.0, (
        f"REST search overhead {rest_ms:.2f}ms exceeded target threshold"
    )

    # 4. Test MCP Server Performance (<10ms tool dispatch)
    mcp_server = MCPServer(
        sync_service, search_service, query_service, context_service, knowledge_service
    )

    t0 = time.perf_counter()
    mcp_res = mcp_server.invoke_tool(
        "search_symbol", {"repo_id": status_dto.repo_id, "query": "APIService"}
    )
    mcp_ms = (time.perf_counter() - t0) * 1000.0
    assert mcp_res["is_success"]
    assert mcp_ms < 10.0, f"MCP tool dispatch {mcp_ms:.2f}ms exceeded target of 10.0ms"

    # 5. Test Python SDK Performance (<2ms wrapper overhead)
    sdk_client = RIAClient(
        sync_service, search_service, query_service, context_service, knowledge_service
    )

    t0 = time.perf_counter()
    sdk_res = sdk_client.search(status_dto.repo_id, "APIService")
    sdk_ms = (time.perf_counter() - t0) * 1000.0
    assert sdk_res.is_success
    assert sdk_ms < 5.0, (
        f"SDK wrapper overhead {sdk_ms:.2f}ms exceeded target threshold"
    )

    # 6. Test CLI Performance (<200ms startup & execution)
    cli_runner = CLIRunner(
        sync_service, search_service, query_service, context_service, knowledge_service
    )

    t0 = time.perf_counter()
    cli_ret = cli_runner.run(
        ["search", "--repo-id", status_dto.repo_id, "--query", "APIService"]
    )
    cli_ms = (time.perf_counter() - t0) * 1000.0
    assert cli_ret == 0
    assert cli_ms < 200.0, (
        f"CLI execution latency {cli_ms:.2f}ms exceeded target of 200.0ms"
    )
