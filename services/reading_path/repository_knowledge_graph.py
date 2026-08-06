"""Repository Knowledge Graph Subsystem.

Builds and queries the central Repository Knowledge Graph connecting Files, Directories,
Classes, Functions, Routes, Services, Database Tables, Patterns, and Concepts with directional edges.
"""

from __future__ import annotations

import os
from typing import Dict, List, Set, Any
from services.architecture.layer_classifier import classify_layer
from services.architecture.pattern_detector import detect_patterns


class RepositoryKnowledgeGraph:
    """Central repository knowledge graph indexing entities and relationships."""

    def __init__(self, owner_repo: str = ""):
        self.owner_repo = owner_repo
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, str]] = []
        self.concept_index: Dict[str, List[str]] = {}

    def build_graph(self, file_paths: List[str], graph_edges: List[Dict[str, str]] | None = None) -> None:
        """Build node-edge knowledge graph from repository files and graph edges."""
        graph_edges = graph_edges or []
        self.edges = graph_edges

        for path in file_paths:
            layer = classify_layer(path)
            patterns = detect_patterns(path)
            file_name = os.path.basename(path)

            self.nodes[path] = {
                "id": path,
                "label": file_name,
                "type": "file",
                "layer": layer,
                "patterns": patterns,
                "concepts": self._infer_concepts(path, layer, patterns),
            }

        # Index concepts to files
        for path, data in self.nodes.items():
            for concept in data.get("concepts", []):
                self.concept_index.setdefault(concept, []).append(path)

    def _infer_concepts(self, path: str, layer: str, patterns: List[str]) -> List[str]:
        """Infer core engineering concepts owned by a file."""
        path_lower = path.lower()
        concepts = set()

        if "auth" in path_lower or "jwt" in path_lower or "login" in path_lower:
            concepts.add("Authentication")
            concepts.add("Authorization")
        if "router" in path_lower or "api" in path_lower or "endpoint" in path_lower:
            concepts.add("Routing")
        if "service" in path_lower:
            concepts.add("Dependency Injection")
        if "db" in path_lower or "repo" in path_lower or "store" in path_lower or "model" in path_lower:
            concepts.add("Database")
        if "cache" in path_lower or "redis" in path_lower:
            concepts.add("Caching")
        if "config" in path_lower or "setting" in path_lower:
            concepts.add("Configuration")
        if "util" in path_lower or "helper" in path_lower:
            concepts.add("Validation")
        if "test" in path_lower or "spec" in path_lower:
            concepts.add("Testing")

        for p in patterns:
            concepts.add(p)

        return list(concepts) or ["Domain Logic"]

    def get_concept_files(self, concept: str) -> List[str]:
        """Return files associated with a given concept."""
        return self.concept_index.get(concept, [])

    def get_all_concepts(self) -> List[Dict[str, Any]]:
        """Return list of all indexed concepts with repository coverage."""
        result = []
        total_files = max(len(self.nodes), 1)

        for concept, files in self.concept_index.items():
            result.append({
                "concept": concept,
                "file_count": len(files),
                "coverage_pct": min(100, round((len(files) / total_files) * 100, 1)),
                "sample_files": files[:3],
            })

        return sorted(result, key=lambda x: x["file_count"], reverse=True)


def get_knowledge_graph(owner_repo: str, file_paths: List[str], graph_edges: List[Dict[str, str]] | None = None) -> RepositoryKnowledgeGraph:
    """Factory helper to construct and populate a RepositoryKnowledgeGraph."""
    pkg = RepositoryKnowledgeGraph(owner_repo)
    pkg.build_graph(file_paths, graph_edges)
    return pkg
