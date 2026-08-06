"""MCP Service Resolution Bridge.

Re-exports existing dependency getters from backend/dependencies.py so that
MCP tool modules have a single import location without coupling to FastAPI.

No new service construction occurs here. Every getter delegates to the
thread-safe lazy singleton machinery in backend/dependencies.py.
"""

from backend.dependencies import (
    ANALYSIS_STORE,
    get_symbol_service,
    get_call_graph_service,
    get_dead_code_service,
    get_retrieval_service,
    get_architecture_service,
    get_graph_service,
    get_graph_serializer,
    get_reading_order_service,
    get_impact_analysis_service,
    get_api_surface_service,
    get_workspace_service,
    get_report_composer,
    get_html_renderer,
    get_markdown_renderer,
    get_pdf_renderer,
    get_structural_retrieval_engine,
    get_engineering_reasoning_engine,
    get_github_service,
    get_build_pipeline,
    get_analysis_registry,
    get_snapshot_store,
    get_embedding_service,
    get_chroma_store,
    get_chunker,
    get_git_history_service,
    _persist_analysis_store,
)

__all__ = [
    "ANALYSIS_STORE",
    "get_symbol_service",
    "get_call_graph_service",
    "get_dead_code_service",
    "get_retrieval_service",
    "get_architecture_service",
    "get_graph_service",
    "get_graph_serializer",
    "get_reading_order_service",
    "get_impact_analysis_service",
    "get_api_surface_service",
    "get_workspace_service",
    "get_report_composer",
    "get_html_renderer",
    "get_markdown_renderer",
    "get_pdf_renderer",
    "get_structural_retrieval_engine",
    "get_engineering_reasoning_engine",
    "get_github_service",
    "get_build_pipeline",
    "get_analysis_registry",
    "get_snapshot_store",
    "get_embedding_service",
    "get_chroma_store",
    "get_chunker",
    "get_git_history_service",
    "_persist_analysis_store",
]
