"""Services package for the Repo Intelligence Agent.

Contains client wrappers for external systems, including the GitHub API,
Gemini embedding models, and Model Context Protocol (MCP) server integration.

Phase 1 additions:
  - TreeSitterService  : source file parsing and structural metadata extraction
  - GraphService       : dependency graph building and persistence
  - EntryPointService  : repository entry point detection
  - ArchitectureService: full architecture intelligence pipeline

Phase 2 additions:
  - ReadingOrderService   : optimal file-reading sequence generation
  - ImpactAnalysisService : change-impact prediction via graph traversal
  - ArchContextService    : architecture context injection for LLM prompts
"""

from .github_service import GitHubService
from .embedding_service import EmbeddingService
from .tree_sitter_service import TreeSitterService
from .graph_service import GraphService
from .entry_point_service import EntryPointService
from .architecture_service import ArchitectureService
from .reading_order_service import ReadingOrderService
from .impact_analysis_service import ImpactAnalysisService
from .arch_context_service import ArchContextService
from .issue_retrieval_service import IssueRetrievalService
from .pr_intelligence_service import PRIntelligenceService
from .architecture_drift_service import ArchitectureDriftService
from .dead_code_service import DeadCodeService

__all__ = [
    "GitHubService",
    "EmbeddingService",
    "TreeSitterService",
    "GraphService",
    "EntryPointService",
    "ArchitectureService",
    "ReadingOrderService",
    "ImpactAnalysisService",
    "ArchContextService",
    "IssueRetrievalService",
    "PRIntelligenceService",
    "ArchitectureDriftService",
    "DeadCodeService",
]
