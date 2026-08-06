"""Composition root.

The single place where concrete adapters are chosen and wired to ports. Every other
module receives its collaborators as constructor arguments and never reaches for a
global.

Why a function and not module-level singletons
----------------------------------------------
SDD section 7 explicitly rejects shared mutable in-process state, recording that
the previous architecture's import-time singletons "made multi-worker deployment
incorrect: N workers, N divergent views, nondeterministic answers". Construction is
therefore an explicit call returning an immutable container, which means:

* a test builds a container against a temporary directory with one line;
* two containers can coexist in one process without interfering;
* import has no side effects, so importing a module cannot open a database.

Wiring order follows the dependency direction of SDD section 2.3: configuration,
then observability, then adapters, then use cases.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

from ria.application.commit_discovery import CommitDiscovery
from ria.application.commit_resolver import CommitResolver
from ria.application.file_enumerator import FileEnumerator
from ria.application.ingestion_handlers import build_ingestion_handlers
from ria.application.ingestion_service import IngestionService
from ria.application.job_runner import JobRunner
from ria.application.mirror_manager import MirrorManager
from ria.application.repository_manager import RepositoryManager
from ria.config.settings import Settings
from ria.domain.language import DEFAULT_LANGUAGE_CATALOGUE, LanguageCatalogue
from ria.application.language_plugin import DefaultLanguagePlugin
from ria.application.parser_registry import ParserRegistry
from ria.application.parser_service import ParserService
from ria.domain.enums import LanguageTier, MINIMUM_PARSER_CAPABILITIES
from ria.domain.models.language_plugin import (
    ExtractorDescriptor,
    LanguagePluginDescriptor,
    PluginIdentity,
)
from ria.domain.models.parser_identity import ComponentVersion
from ria.infrastructure.git.subprocess_git_client import SubprocessGitClient
from ria.infrastructure.parser.extractors.js_ts_extractor import (
    JS_TS_EXTRACTOR_CAPABILITIES,
    JsTsSyntaxExtractor,
)
from ria.infrastructure.parser.extractors.python_extractor import (
    PYTHON_EXTRACTOR_CAPABILITIES,
    PythonSyntaxExtractor,
)
from ria.infrastructure.parser.tree_sitter_adapter import TreeSitterAdapter
from ria.infrastructure.storage.filesystem_blob_store import FilesystemBlobStore
from ria.infrastructure.storage.sqlite.connection import ConnectionProvider
from ria.infrastructure.storage.sqlite.migrations import Migration, MigrationRunner
from ria.application.agent_platform_service import AgentPlatformService
from ria.application.context_engine_service import ContextEngineService
from ria.application.graph_service import GraphBuilderService
from ria.application.query_service import RepositoryQueryService
from ria.application.reasoning_service import ReasoningEngineService
from ria.application.repository_execution_service import RepositoryExecutionService
from ria.application.twin_service import RepositoryTwinService
from ria.application.workflow_service import WorkflowService
from ria.infrastructure.models.provider_registry import ModelProviderRegistry
from ria.infrastructure.storage.sqlite.agent_store import SqliteAgentPlatformStore
from ria.infrastructure.storage.sqlite.context_store import SqliteContextCacheStore
from ria.infrastructure.git.git_repository import GitRepositoryService
from ria.infrastructure.storage.sqlite.execution_store import SqliteExecutionStore
from ria.infrastructure.storage.sqlite.graph_store import SqliteGraphCacheStore
from ria.infrastructure.storage.sqlite.query_store import SqliteQueryCacheStore
from ria.infrastructure.storage.sqlite.reasoning_store import SqliteReasoningCacheStore
from ria.infrastructure.storage.sqlite.workflow_store import SqliteWorkflowStore
from ria.infrastructure.storage.sqlite.twin_store import (
    SqliteTwinCacheStore,
    SqliteTwinStore,
)
from ria.application.semantic_service import SemanticResolutionService
from ria.infrastructure.storage.sqlite.semantic_cache_store import (
    SqliteSemanticCacheStore,
)
from ria.infrastructure.storage.sqlite.parse_cache_store import SqliteParseCacheStore
from ria.infrastructure.storage.sqlite.unit_of_work import SqliteUnitOfWorkFactory
from ria.infrastructure.system_clock import SystemClock
from ria.observability.logging import configure_logging, get_logger
from ria.observability.metrics import InMemoryMetricsSink, NullMetricsSink
from ria.observability.progress import LoggingProgressSink
from ria.ports.metrics import MetricsSink
from ria.ports.parser import ParserPort, ParserRegistryPort
from ria.ports.progress import ProgressSink

__all__ = ["Container", "build_container", "build_default_parser_registry"]

_LOGGER = get_logger(__name__)


def build_default_parser_registry(parser_adapter: ParserPort) -> ParserRegistryPort:
    """Build a ParserRegistry populated with default language plugins (Python, JS, TS, TSX).

    Args:
        parser_adapter: ParserPort adapter for tree-sitter.

    Returns:
        Populated ParserRegistryPort.
    """
    registry = ParserRegistry()

    # 1. Python Plugin
    py_extractor = PythonSyntaxExtractor()
    py_descriptor = LanguagePluginDescriptor(
        identity=PluginIdentity("python", ComponentVersion("python-plugin", "1.0.0")),
        extensions=(".py", ".pyi"),
        grammar_name="python",
        parser_version=parser_adapter.parser_version("python"),
        extractor=ExtractorDescriptor(
            name=py_extractor.extractor_version().name,
            version=py_extractor.extractor_version(),
            capabilities=PYTHON_EXTRACTOR_CAPABILITIES,
        ),
        tier=LanguageTier.TIER_A,
        capabilities=MINIMUM_PARSER_CAPABILITIES | PYTHON_EXTRACTOR_CAPABILITIES,
    )
    registry.register_plugin(
        DefaultLanguagePlugin(
            descriptor=py_descriptor, parser=parser_adapter, extractor=py_extractor
        )
    )

    # 2. JS/TS Extractors & Plugins
    jsts_extractor = JsTsSyntaxExtractor()

    for lang, exts, ts_lang_key in (
        ("javascript", (".js", ".jsx", ".mjs", ".cjs"), "javascript"),
        ("typescript", (".ts", ".mts", ".cts"), "typescript"),
        ("tsx", (".tsx",), "tsx"),
    ):
        descriptor = LanguagePluginDescriptor(
            identity=PluginIdentity(lang, ComponentVersion(f"{lang}-plugin", "1.0.0")),
            extensions=exts,
            grammar_name=lang,
            parser_version=parser_adapter.parser_version(ts_lang_key),
            extractor=ExtractorDescriptor(
                name=jsts_extractor.extractor_version().name,
                version=jsts_extractor.extractor_version(),
                capabilities=JS_TS_EXTRACTOR_CAPABILITIES,
            ),
            tier=LanguageTier.TIER_A,
            capabilities=MINIMUM_PARSER_CAPABILITIES | JS_TS_EXTRACTOR_CAPABILITIES,
        )
        registry.register_plugin(
            DefaultLanguagePlugin(
                descriptor=descriptor, parser=parser_adapter, extractor=jsts_extractor
            )
        )

    return registry


@dataclass(frozen=True)
class Container:
    """Resolved application graph.

    Frozen: the graph is built once and never mutated. A container whose members
    could be swapped after construction would reintroduce the ambient mutable state
    this design exists to avoid.

    Attributes:
        settings: Resolved configuration.
        clock: Time source.
        metrics: Metrics sink.
        language_catalogue: Language detection and classification table.
        connections: SQLite connection provider.
        unit_of_work_factory: Creates a transaction per operation.
        blob_store: Content-addressable store.
        git: Read-only git access.
        parse_cache_store: Persistent parse tree cache.
        parser_service: Source code parsing.
        repository_manager: Repository registration and lifecycle use cases.
        commit_resolver: Ref resolution and commit recording use cases.
        progress: Destination for pipeline progress events.
        mirror_manager: Acquires and locates repository mirrors.
        file_enumerator: Builds a commit manifest from a git tree.
        commit_discovery: Records branches and commits and enqueues ingestion work.
        ingestion_service: Ingests one commit and makes it queryable.
        job_runner: Leases and executes queued jobs.
    """

    settings: Settings
    clock: SystemClock
    metrics: MetricsSink
    language_catalogue: LanguageCatalogue
    connections: ConnectionProvider
    unit_of_work_factory: SqliteUnitOfWorkFactory
    blob_store: FilesystemBlobStore
    git: SubprocessGitClient
    parse_cache_store: SqliteParseCacheStore
    parser_service: ParserService
    repository_manager: RepositoryManager
    commit_resolver: CommitResolver
    progress: ProgressSink
    mirror_manager: MirrorManager
    file_enumerator: FileEnumerator
    commit_discovery: CommitDiscovery
    ingestion_service: IngestionService
    job_runner: JobRunner

    def close(self) -> None:
        """Release the calling thread's resources.

        Closes this thread's database connection. Each thread must call this at the
        end of its life: connections are per-thread and closing another thread's
        would be unsafe.
        """
        self.connections.close()

    def mirror_path(self, moniker: Union[str, object]) -> Path:
        """Resolve the local mirror directory for a repository.

        The mirror is a cache of upstream truth (SDD section 6.2) and may be deleted
        at any time. Its location is derived from the moniker rather than stored, so
        that the mapping is reproducible and no additional state can drift.

        The path is built from sanitised components: only alphanumerics, hyphens,
        underscores and dots survive, so a moniker can never escape the mirror root
        or introduce a path separator.

        Args:
            moniker: Repository moniker, or its string form.

        Returns:
            Absolute path of the repository's mirror directory.
        """
        text = str(moniker)
        safe = "".join(
            character if character.isalnum() or character in "-_." else "_"
            for character in text
        )
        return self.settings.storage.mirror_root / safe


def build_container(
    settings: Optional[Settings] = None,
    *,
    run_migrations: bool = True,
    language_catalogue: Optional[LanguageCatalogue] = None,
) -> Container:
    """Build the application graph.

    Args:
        settings: Configuration to use. When ``None``, configuration is resolved
            from the environment.
        run_migrations: Whether to apply pending schema migrations. Left enabled by
            default so that a freshly built container is immediately usable;
            disable it when a caller wants to inspect or control migration timing.
        language_catalogue: Language table to use. Overridable so that a test can
            exercise classification against a small fixed catalogue.

    Returns:
        The resolved container.

    Raises:
        ConfigurationError: If a required directory cannot be created.
        StorageError: If the database cannot be opened or migrated.
    """
    resolved = settings or Settings()
    resolved.ensure_directories()
    configure_logging(resolved.observability)

    metrics: MetricsSink = (
        InMemoryMetricsSink()
        if resolved.observability.metrics_enabled
        else NullMetricsSink()
    )
    clock = SystemClock()

    connections = ConnectionProvider(
        resolved.storage.database_path,
        busy_timeout_ms=resolved.storage.sqlite_busy_timeout_ms,
    )
    if run_migrations:
        applied: Sequence[Migration] = MigrationRunner(connections).run()
        _LOGGER.debug(
            "container migrations complete",
            extra={"applied": [migration.version for migration in applied]},
        )

    unit_of_work_factory = SqliteUnitOfWorkFactory(connections, metrics)

    blob_store = FilesystemBlobStore(
        resolved.storage.blob_store_path,
        metrics,
        shard_depth=resolved.storage.blob_shard_depth,
        shard_width=resolved.storage.blob_shard_width,
    )

    git = SubprocessGitClient(resolved.git, metrics)

    # Milestone 3 — parser layer.
    parse_cache_store = SqliteParseCacheStore(connections)
    parser_adapter = TreeSitterAdapter(metrics=metrics)
    parser_registry = build_default_parser_registry(parser_adapter)
    parser_service = ParserService(
        cache_store=parse_cache_store,
        blob_store=blob_store,
        registry=parser_registry,
        metrics=metrics,
    )

    repository_manager = RepositoryManager(
        unit_of_work_factory,
        clock,
        metrics,
        default_tenant_id=resolved.default_tenant_id,
    )
    commit_resolver = CommitResolver(git, unit_of_work_factory, clock, metrics)

    # Milestone 2 — ingestion.
    progress: ProgressSink = LoggingProgressSink()

    mirror_manager = MirrorManager(git, resolved.storage.mirror_root, metrics)
    file_enumerator = FileEnumerator(
        git,
        blob_store,
        language_catalogue or DEFAULT_LANGUAGE_CATALOGUE,
        clock,
        metrics,
        progress,
        max_blob_bytes=resolved.git.max_blob_bytes,
    )
    commit_discovery = CommitDiscovery(
        git, unit_of_work_factory, clock, metrics, progress
    )
    # Milestone 4 — semantic resolution layer.
    semantic_cache_store = SqliteSemanticCacheStore(connections)
    semantic_service = SemanticResolutionService(cache_store=semantic_cache_store)

    # Milestone 5 — repository knowledge graph.
    graph_cache_store = SqliteGraphCacheStore(connections)
    graph_service = GraphBuilderService(cache_store=graph_cache_store)

    # Milestone 6 — repository digital twin.
    twin_cache_store = SqliteTwinCacheStore(connections)
    twin_store = SqliteTwinStore(connections)
    twin_service = RepositoryTwinService(
        store=twin_store,
        cache_store=twin_cache_store,
        metrics_sink=metrics,
    )

    # Milestone 7 — repository query & analysis engine.
    query_cache_store = SqliteQueryCacheStore(connections)
    _query_service = RepositoryQueryService(
        cache_store=query_cache_store,
        metrics_sink=metrics,
    )

    # Milestone 8 — AI context & retrieval engine.
    context_cache_store = SqliteContextCacheStore(connections)
    _context_engine_service = ContextEngineService(
        cache_store=context_cache_store,
        metrics_sink=metrics,
    )

    # Milestone 9 — AI reasoning engine.
    provider_registry = ModelProviderRegistry()
    reasoning_cache_store = SqliteReasoningCacheStore(connections)
    _reasoning_engine_service = ReasoningEngineService(
        provider=provider_registry.get_provider("local"),
        cache_store=reasoning_cache_store,
        metrics_sink=metrics,
    )

    # Milestone 10 — Multi-Agent Developer Platform.
    _agent_platform_store = SqliteAgentPlatformStore(connections)
    _agent_platform_service = AgentPlatformService(
        reasoning_engine=_reasoning_engine_service,
        metrics_sink=metrics,
    )

    # Milestone 11 — Autonomous Development Workflow Engine.
    workflow_store = SqliteWorkflowStore(connections)
    _workflow_service = WorkflowService(
        workflow_store=workflow_store,
        metrics_sink=metrics,
    )

    # Milestone 12 — Repository Execution & Continuous Learning Engine.
    git_repo_service = GitRepositoryService()
    execution_store = SqliteExecutionStore(connections)
    _execution_service = RepositoryExecutionService(
        execution_store=execution_store,
        metrics_sink=metrics,
        git_repo=git_repo_service,
    )

    ingestion_service = IngestionService(
        mirror_manager,
        commit_resolver,
        file_enumerator,
        unit_of_work_factory,
        clock,
        metrics,
        progress,
        parser_service=parser_service,
        semantic_service=semantic_service,
        graph_service=graph_service,
        twin_service=twin_service,
    )
    job_runner = JobRunner(
        unit_of_work_factory,
        clock,
        metrics,
        build_ingestion_handlers(
            repository_manager,
            mirror_manager,
            commit_discovery,
            ingestion_service,
            metrics,
        ),
        owner=_worker_identity(),
    )

    _LOGGER.info(
        "container built",
        extra={
            "environment": resolved.environment,
            "database": str(resolved.storage.database_path),
            "blob_store": str(resolved.storage.blob_store_path),
        },
    )

    return Container(
        settings=resolved,
        clock=clock,
        metrics=metrics,
        language_catalogue=language_catalogue or DEFAULT_LANGUAGE_CATALOGUE,
        connections=connections,
        unit_of_work_factory=unit_of_work_factory,
        blob_store=blob_store,
        git=git,
        parse_cache_store=parse_cache_store,
        parser_service=parser_service,
        repository_manager=repository_manager,
        commit_resolver=commit_resolver,
        progress=progress,
        mirror_manager=mirror_manager,
        file_enumerator=file_enumerator,
        commit_discovery=commit_discovery,
        ingestion_service=ingestion_service,
        job_runner=job_runner,
    )


def _worker_identity() -> str:
    """Build an identifier for this process, recorded on every job lease.

    Host and process together identify the worker uniquely enough to trace a stuck
    job back to the process that claimed it, which is the only purpose the value
    serves. A random identifier would be unique but would not survive into an
    operator's investigation.

    Returns:
        An identifier of the form ``host/pid``.
    """
    return f"{socket.gethostname()}/{os.getpid()}"
