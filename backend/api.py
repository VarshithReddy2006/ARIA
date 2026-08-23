"""FastAPI application entry point for ARIA (AI-Powered Repository Intelligence Agent).

Responsibilities of this file (only):
  - Load environment variables
  - Create the FastAPI application instance
  - Register CORS middleware
  - Mount all routers
  - Trigger analysis-store hydration on startup
  - Expose the __main__ entry point for direct uvicorn execution

All business logic, service singletons, request/response models, and helper
functions live in dedicated modules:
  backend/dependencies.py          — service singletons & analysis store
  backend/routers/*.py             — endpoint handlers grouped by domain
  services/ingestion_service.py    — detect_tech_stack_and_deps, parse_repo_name
  services/architecture_summary_service.py — generate_architecture_summary
"""

import sys
import os
from typing import Any

# Ensure project root is on sys.path so all local packages are importable
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.settings import settings

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.security_middleware import HealthExemptTrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from backend.logging_middleware import RequestIdMiddleware
from backend.security_middleware import RateLimitMiddleware
from backend.metrics_middleware import MetricsMiddleware

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.settings import settings
    from backend.logging_config import configure_logging
    from storage.migrations import run_migrations
    from ria.container import build_container

    # 1. Configure logging on application startup
    configure_logging(log_level=settings.log_level, log_format=settings.log_format)
    # 2. Run database migrations on startup
    run_migrations()
    # 3. Hydrate ANALYSIS_STORE from disk
    from backend.dependencies import _load_analysis_store

    _load_analysis_store()

    # 4. Initialize RIA Composition Root Container
    container = build_container(run_migrations=False)
    app.state.container = container
    app.state.git = container.git
    app.state.parser_service = container.parser_service
    app.state.repository_manager = container.repository_manager
    app.state.ingestion_service = container.ingestion_service

    # 5. Warm up high-impact services
    _warmup_services()
    # 6. Validate LLM providers during startup before serving traffic
    await validate_llm_providers()

    # Store singletons on app.state
    from backend import dependencies as deps

    app.state.snapshot_store = deps.get_snapshot_store()
    app.state.analysis_cache = deps.get_analysis_cache()
    app.state.symbol_service = deps.get_symbol_service()
    app.state.architecture_service = deps.get_architecture_service()
    app.state.graph_service = deps.get_graph_service()
    app.state.github_service = deps.get_github_service()
    app.state.embedding_service = deps.get_embedding_service()
    app.state.chroma_store = deps.get_chroma_store()
    app.state.pr_intelligence_service = deps.get_pr_intelligence_service()
    app.state.dead_code_service = deps.get_dead_code_service()
    app.state.architecture_drift_service = deps.get_architecture_drift_service()
    app.state.workspace_service = deps.get_workspace_service()

    try:
        yield
    finally:
        # Cleanup container and database resources on shutdown
        if hasattr(app.state, "container") and app.state.container:
            try:
                app.state.container.close()
            except Exception:
                pass


app = FastAPI(
    title="ARIA — AI-Powered Repository Intelligence Agent",
    description="Backend services exposing multi-agent codebase analysis and chat.",
    version="1.5.0",
    lifespan=lifespan,
)

# Register global exception handlers (R-019)
from backend.exception_handlers import register_exception_handlers  # noqa: E402

register_exception_handlers(app)

# Production Middlewares
from backend.security_middleware import APIKeyMiddleware  # noqa: E402

_cors_origins = [settings.frontend_url]
if settings.app_env != "production":
    # Development convenience: allow common local frontend dev server origins.
    if "localhost:4321" not in settings.frontend_url:
        _cors_origins.append("http://localhost:4321")
    if "localhost:5173" not in settings.frontend_url:
        _cors_origins.append("http://localhost:5173")

app.add_middleware(
    APIKeyMiddleware,
    api_key=settings.api_key,
    app_env=settings.app_env,
    allowed_origins=_cors_origins,
)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimitMiddleware, limit=settings.rate_limit_per_minute)
app.add_middleware(MetricsMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
_allowed_hosts = list(settings.allowed_hosts)
if settings.app_env != "production" and "*" not in _allowed_hosts:
    for test_host in ("testserver", "testclient"):
        if test_host not in _allowed_hosts:
            _allowed_hosts.append(test_host)

app.add_middleware(HealthExemptTrustedHostMiddleware, allowed_hosts=_allowed_hosts)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)


def _warmup_services() -> None:
    import logging

    logger = logging.getLogger("backend.api")
    try:
        if settings.app_env != "production":
            from services.embedding_service import _get_model

            logger.info("Warming up embedding model and tokenizer...")
            model = _get_model()
            model.encode(
                ["Represent this sentence: dummy text"], show_progress_bar=False
            )
            logger.info("Embedding model and tokenizer warmed up successfully.")
        else:
            logger.info(
                "Production mode: Skipping eager embedding model warmup to conserve memory."
            )

        from services.tree_sitter_service import TreeSitterService

        logger.info("Warming up Python Tree-sitter parser...")
        ts = TreeSitterService()
        ts.parse_file("dummy.py", "def dummy(): pass")
        logger.info("Python Tree-sitter parser warmed up successfully.")
    except Exception as exc:
        logger.warning("Startup warm-up failed: %s", exc, exc_info=True)


# ---------------------------------------------------------------------------
# Startup Validation — validate LLM providers before serving traffic
# ---------------------------------------------------------------------------


async def validate_llm_providers() -> None:
    """Verify LLM provider configuration locally during startup.

    Startup performs only local configuration checks. No network/API calls are
    made to Gemini or DeepSeek. Live provider validation is deferred to
    explicit diagnostics or actual provider usage.
    """
    import logging as _logging
    from services.llm import ProviderFactory

    _logger = _logging.getLogger("backend.startup")

    _logger.info(
        "Checking LLM provider configuration (local-only, zero network requests)..."
    )

    try:
        configs = ProviderFactory.check_configuration(settings=settings)
    except Exception as exc:
        _logger.critical(
            "LLM provider configuration check failed unexpectedly: %s",
            exc,
            exc_info=True,
        )
        if settings.app_env == "production":
            raise RuntimeError(
                "LLM provider configuration check failed during startup. "
                "Check GEMINI_API_KEY / DEEPSEEK_API_KEY."
            ) from exc
        return

    primary = settings.llm_provider.lower().strip()
    primary_cfg = configs.get(primary, {})

    for name, cfg in configs.items():
        if cfg.get("configured"):
            _logger.info(
                "LLM_PROVIDER_CONFIG provider=%s model=%s configured=true "
                "auth_credential_present=true (network check deferred to request time)",
                name,
                cfg.get("model", "unknown"),
            )
        else:
            _logger.warning(
                "LLM_PROVIDER_CONFIG provider=%s model=%s configured=false "
                "auth_credential_present=false",
                name,
                cfg.get("model", "unknown"),
            )

    if not primary_cfg.get("configured"):
        msg = (
            f"Primary LLM provider '{primary}' has no API key configured. "
            "Check GEMINI_API_KEY / DEEPSEEK_API_KEY."
        )

        if settings.app_env == "production":
            _logger.critical("STARTUP WARNING — %s", msg)
        else:
            _logger.warning(msg)
        return

    _logger.info(
        "LLM configuration verified: primary provider '%s' (%s) configured.",
        primary,
        primary_cfg.get("model", "unknown"),
    )


# ---------------------------------------------------------------------------
# Public re-exports — backward-compatible shims so that existing test files
# that do `from backend.api import ANALYSIS_STORE, symbol_service, ...`
# continue to work without modification.
# ---------------------------------------------------------------------------
def __getattr__(name: str) -> Any:
    import backend.dependencies as deps

    return getattr(deps, name)


# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------
from backend.routers.health import router as health_router  # noqa: E402
from backend.routers.repositories import router as repositories_router  # noqa: E402
from backend.routers.chat import router as chat_router, graph_rag_router  # noqa: E402
from backend.routers.architecture import router as architecture_router  # noqa: E402
from backend.routers.graph import router as graph_router  # noqa: E402
from backend.routers.symbols import router as symbols_router  # noqa: E402
from backend.routers.pr import router as pr_router  # noqa: E402
from backend.routers.git_history import router as git_history_router  # noqa: E402
from backend.routers.call_graph import router as call_graph_router  # noqa: E402
from backend.routers.api_surface import router as api_surface_router  # noqa: E402
from backend.routers.metrics import router as metrics_router  # noqa: E402
from backend.routers.report import router as report_router  # noqa: E402
from backend.routers.twin import router as twin_router  # noqa: E402
from backend.routers.knowledge_graph import router as knowledge_graph_router  # noqa: E402
from backend.routers.retrieval import router as retrieval_router  # noqa: E402
from backend.routers.reasoning import router as reasoning_router  # noqa: E402
from backend.routers.memory import router as memory_router  # noqa: E402
from backend.routers.inspection import router as inspection_router  # noqa: E402
from backend.routers.monitoring import router as monitoring_router  # noqa: E402
from backend.routers.advisor import router as advisor_router  # noqa: E402
from backend.routers.execution import router as execution_router  # noqa: E402
from backend.routers.workspace import router as workspace_router  # noqa: E402


# Add legacy redirection middleware (R-009)
from fastapi import Request  # noqa: E402
from fastapi.responses import RedirectResponse  # noqa: E402


@app.middleware("http")
async def legacy_prefix_redirect_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and not path.startswith("/api/v1/"):
        if request.method == "OPTIONS":
            request.scope["path"] = "/api/v1" + path[4:]
            return await call_next(request)
        target_path = "/api/v1" + path[4:]
        if request.url.query:
            target_path += "?" + request.url.query
        response = RedirectResponse(
            url=target_path,
            status_code=308,
            headers={"Deprecation": "true", "Sunset": "2026-12-31"},
        )
        origin = request.headers.get("origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    return await call_next(request)


# ---------------------------------------------------------------------------
# Router registration — Single canonical /api/v1 base prefix (R-009)
# ---------------------------------------------------------------------------
# System ops & metrics top-level shortcuts
app.include_router(health_router)
app.include_router(metrics_router)

# Versioned API routes under /api/v1
app.include_router(health_router, prefix="/api/v1")
app.include_router(repositories_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(architecture_router, prefix="/api/v1")
app.include_router(graph_router, prefix="/api/v1")
app.include_router(symbols_router, prefix="/api/v1")
app.include_router(pr_router, prefix="/api/v1")
app.include_router(git_history_router, prefix="/api/v1")
app.include_router(call_graph_router, prefix="/api/v1")
app.include_router(api_surface_router, prefix="/api/v1")
app.include_router(metrics_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(twin_router, prefix="/api/v1")
app.include_router(knowledge_graph_router, prefix="/api/v1")
app.include_router(retrieval_router, prefix="/api/v1")
app.include_router(reasoning_router, prefix="/api/v1")
app.include_router(graph_rag_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(inspection_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(advisor_router, prefix="/api/v1")
app.include_router(execution_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Frontend static files (Astro production build)
# ---------------------------------------------------------------------------
from fastapi.staticfiles import StaticFiles  # noqa: E402

_frontend_dist = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
    "dist",
)
if not os.path.isdir(_frontend_dist) and os.path.isdir("/app/frontend/dist"):
    _frontend_dist = "/app/frontend/dist"

if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")


# ---------------------------------------------------------------------------
# Direct execution entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from backend.settings import settings

    is_dev = settings.app_env == "development"
    workers = 1 if is_dev else settings.effective_workers

    uvicorn.run(
        "backend.api:app",
        host=settings.host,
        port=settings.port,
        reload=is_dev,
        reload_dirs=["backend", "services", "agents", "memory", "models"]
        if is_dev
        else None,
        workers=workers if not is_dev else None,
    )
