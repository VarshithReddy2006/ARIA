"""Repository Knowledge Graph Builder Service.

Composer that orchestrates the construction of the Repository Knowledge Graph
via extensible providers and returns the read-only Pydantic representation.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
import networkx as nx

from models.knowledge_graph import (
    KnowledgeGraph,
    KnowledgeGraphNode,
    KnowledgeGraphEdge,
    KnowledgeGraphSummary,
)

logger = logging.getLogger(__name__)


class KnowledgeGraphProvider(ABC):
    """Abstract base class representing a plugin provider for knowledge graph entities/edges."""

    @abstractmethod
    def populate(self, repo_name: str, twin: Any, graph: nx.DiGraph) -> None:
        """Populate entities and relationships into the unified NetworkX graph."""
        pass


class MetadataProvider(KnowledgeGraphProvider):
    """Provides Repository root, Health, Compliance, and Architecture report nodes and edges."""

    def populate(self, repo_name: str, twin: Any, graph: nx.DiGraph) -> None:
        # 1. Add Repository Root node
        repo_id = repo_name
        graph.add_node(
            repo_id,
            type="repository",
            name=repo_name.split("/")[-1],
            owner=repo_name.split("/")[0] if "/" in repo_name else "",
            tech_stack=twin.metadata.get("tech_stack", []),
            total_loc=twin.metadata.get("total_loc", 0),
        )

        # 2. Add Health Report node
        health_id = f"{repo_id}::health"
        graph.add_node(
            health_id,
            type="health",
            overall_score=twin.health_summary.get("overall_score", 0.0),
            grade=twin.health_summary.get("grade", "F"),
            breakdown=twin.health_summary.get("breakdown", {}),
        )
        graph.add_edge(repo_id, health_id, type="HAS_HEALTH")

        # 3. Add Compliance Report node
        compliance_id = f"{repo_id}::compliance"
        graph.add_node(
            compliance_id,
            type="compliance",
            status=twin.compliance_summary.get("status", "non-compliant"),
            reasons=twin.compliance_summary.get("reasons", []),
            dead_code_ratio=twin.compliance_summary.get("dead_code_ratio", 0.0),
        )
        graph.add_edge(repo_id, compliance_id, type="HAS_COMPLIANCE")

        # 4. Add Architecture Component nodes
        arch_summary = twin.architecture_summary
        if arch_summary:
            arch_id = f"{repo_id}::architecture"
            graph.add_node(
                arch_id,
                type="architecture",
                cycles_count=arch_summary.get("cycles_count", 0),
                scc_count=arch_summary.get("strongly_connected_components", 0),
            )
            graph.add_edge(repo_id, arch_id, type="HAS_ARCHITECTURE")


class HierarchyProvider(KnowledgeGraphProvider):
    """Provides Directory and File node entities and CONTAINS relationships."""

    def populate(self, repo_name: str, twin: Any, graph: nx.DiGraph) -> None:
        repo_id = repo_name
        files = twin.files

        added_dirs: Set[str] = set()

        for file_path in files:
            # Normalize path separators
            norm_path = file_path.replace("\\", "/")
            parts = norm_path.split("/")

            # Add directory nodes recursively
            current_dir_id = repo_id
            for i in range(len(parts) - 1):
                sub_dir_path = "/".join(parts[: i + 1])
                sub_dir_id = f"{repo_id}::{sub_dir_path}"

                if sub_dir_id not in added_dirs:
                    graph.add_node(
                        sub_dir_id,
                        type="directory",
                        name=parts[i],
                        path=sub_dir_path,
                    )
                    # Link parent directory/repo to this directory
                    graph.add_edge(current_dir_id, sub_dir_id, type="CONTAINS")
                    added_dirs.add(sub_dir_id)

                current_dir_id = sub_dir_id

            # Add File node
            file_id = f"{repo_id}::{norm_path}"
            graph.add_node(
                file_id,
                type="file",
                name=parts[-1],
                path=norm_path,
            )
            # Link final directory containing it to the file node
            graph.add_edge(current_dir_id, file_id, type="CONTAINS")


class SymbolProvider(KnowledgeGraphProvider):
    """Provides Symbol nodes and DECLARES relationships."""

    def populate(self, repo_name: str, twin: Any, graph: nx.DiGraph) -> None:
        repo_id = repo_name
        from backend.dependencies import symbol_service

        symbol_index = symbol_service.load(repo_name)
        if not symbol_index:
            return

        # Add all symbols
        for sym in symbol_index.symbols:
            norm_file = sym.file_path.replace("\\", "/")
            file_id = f"{repo_id}::{norm_file}"
            qualified_name = f"{sym.parent_class}.{sym.name}" if sym.parent_class else sym.name
            symbol_id = f"{repo_id}::{norm_file}::{qualified_name}"

            graph.add_node(
                symbol_id,
                type="symbol",
                name=sym.name,
                symbol_type=sym.type,
                line_number=sym.line_number,
                language=sym.language,
            )

            # Link File to Symbol declaration
            graph.add_edge(file_id, symbol_id, type="DECLARES")

            # Link Class to Method if nested
            if sym.parent_class:
                class_id = f"{repo_id}::{norm_file}::{sym.parent_class}"
                if class_id in graph:
                    graph.add_edge(class_id, symbol_id, type="DECLARES")


class DependencyProvider(KnowledgeGraphProvider):
    """Provides IMPORTS edges between File nodes based on imports dependency graph."""

    def populate(self, repo_name: str, twin: Any, graph: nx.DiGraph) -> None:
        repo_id = repo_name
        from backend.dependencies import graph_service

        dep_graph = graph_service.load_graph(repo_name)
        if dep_graph is None:
            return

        for u, v in dep_graph.edges():
            u_norm = u.replace("\\", "/")
            v_norm = v.replace("\\", "/")
            u_id = f"{repo_id}::{u_norm}"
            v_id = f"{repo_id}::{v_norm}"

            # Only add edge if both nodes are present in the hierarchy
            if u_id in graph and v_id in graph:
                graph.add_edge(u_id, v_id, type="IMPORTS")


class CallGraphProvider(KnowledgeGraphProvider):
    """Provides CALLS edges between Symbol nodes based on call graph edges."""

    def populate(self, repo_name: str, twin: Any, graph: nx.DiGraph) -> None:
        repo_id = repo_name
        from backend.dependencies import graph_service

        call_graph = graph_service.load_graph(f"{repo_name}_call_graph")
        if call_graph is None:
            return

        for u, v in call_graph.edges():
            # Call graph node format: "file_path::qualified_name"
            if "::" in u and "::" in v:
                u_file, u_qual = u.split("::", 1)
                v_file, v_qual = v.split("::", 1)

                u_file_clean = u_file.replace('\\', '/')
                v_file_clean = v_file.replace('\\', '/')
                u_id = f"{repo_id}::{u_file_clean}::{u_qual}"
                v_id = f"{repo_id}::{v_file_clean}::{v_qual}"

                if u_id in graph and v_id in graph:
                    graph.add_edge(u_id, v_id, type="CALLS")


class RepositoryKnowledgeGraphBuilder:
    """Thin composer that runs registered providers to build the RepositoryKnowledgeGraph."""

    def __init__(
        self,
        twin_builder: Optional[Any] = None,
        cache: Optional[Any] = None,
        providers: Optional[List[KnowledgeGraphProvider]] = None,
    ) -> None:
        """Initialise the Knowledge Graph composer service."""
        from backend.dependencies import (
            repository_twin_builder as default_tb,
            analysis_cache as default_cache,
        )

        self.twin_builder = twin_builder or default_tb
        self.cache = cache or default_cache

        # Set default providers
        self.providers = providers if providers is not None else [
            MetadataProvider(),
            HierarchyProvider(),
            SymbolProvider(),
            DependencyProvider(),
            CallGraphProvider(),
        ]

    def register_provider(self, provider: KnowledgeGraphProvider) -> None:
        """Dynamically registers a new plugin provider to extend the Knowledge Graph."""
        self.providers.append(provider)

    def build_networkx_graph(self, repo_name: str) -> nx.DiGraph:
        """Builds and returns the internal NetworkX DiGraph by running all providers."""
        twin = self.twin_builder.build_twin(repo_name)
        graph = nx.DiGraph()

        for provider in self.providers:
            try:
                provider.populate(repo_name, twin, graph)
            except Exception as e:
                logger.error(
                    "Provider %s failed during twin composition for %s: %s",
                    provider.__class__.__name__,
                    repo_name,
                    e,
                    exc_info=True,
                )

        return graph

    def build_graph(self, repo_name: str) -> KnowledgeGraph:
        """Assembles and returns the fully serialized Pydantic KnowledgeGraph."""
        # 1. Try to fetch from cache first
        cache_key = f"{repo_name}_knowledge_graph"
        cached = self.cache.get(repo_name, "knowledge_graph", 1)
        if cached is not None:
            return cached

        # 2. Build internal graph
        nx_graph = self.build_networkx_graph(repo_name)

        # 3. Serialize nodes and edges
        nodes = []
        for node_id, data in nx_graph.nodes(data=True):
            node_type = data.get("type", "unknown")
            props = {k: v for k, v in data.items() if k != "type"}
            nodes.append(KnowledgeGraphNode(id=node_id, type=node_type, properties=props))

        edges = []
        for u, v, data in nx_graph.edges(data=True):
            edge_type = data.get("type", "unknown")
            props = {k: v for k, v in data.items() if k != "type"}
            edges.append(KnowledgeGraphEdge(source=u, target=v, type=edge_type, properties=props))

        kg = KnowledgeGraph(repository_name=repo_name, nodes=nodes, edges=edges)

        # 4. Save to cache
        self.cache.set(repo_name, "knowledge_graph", kg, 1)

        return kg

    def build_graph_summary(self, repo_name: str) -> KnowledgeGraphSummary:
        """Retrieves or builds a lightweight summary stats model of the Knowledge Graph."""
        kg = self.build_graph(repo_name)

        # Aggregate counts
        node_breakdown: Dict[str, int] = {}
        for node in kg.nodes:
            node_breakdown[node.type] = node_breakdown.get(node.type, 0) + 1

        edge_breakdown: Dict[str, int] = {}
        for edge in kg.edges:
            edge_breakdown[edge.type] = edge_breakdown.get(edge.type, 0) + 1

        return KnowledgeGraphSummary(
            repository_name=repo_name,
            nodes_count=len(kg.nodes),
            edges_count=len(kg.edges),
            node_types_breakdown=node_breakdown,
            edge_types_breakdown=edge_breakdown,
        )
