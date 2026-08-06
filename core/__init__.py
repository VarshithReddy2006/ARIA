"""Core architecture module for caching, context resolution, and pipelines."""

from .cache import AnalysisCache
from .repository_context import RepositoryContext
from .analysis_registry import AnalysisNode, AnalysisRegistry
from .build_pipeline import BuildPipeline
from .change_detector import ChangeDetector, ChangeSet
from .incremental_build_planner import BuildTask, IncrementalBuildPlanner

__all__ = [
    "AnalysisCache",
    "RepositoryContext",
    "AnalysisNode",
    "AnalysisRegistry",
    "BuildPipeline",
    "ChangeDetector",
    "ChangeSet",
    "BuildTask",
    "IncrementalBuildPlanner",
]
