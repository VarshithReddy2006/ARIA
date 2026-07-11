"""Structural Retrieval Engine.

Implements the RetrievalPlan + execution model with specialized executors,
a context assembler, and stable ContextReference mappings.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set
import asyncio

from models.retrieval import (
    ContextReference,
    RetrievalPlan,
    RetrievalPlanStep,
    RetrievalExplanation,
    RepositoryRetrievalContext,
)
from services.chat.intent_detector import RuleBasedIntentDetector

logger = logging.getLogger(__name__)


class RetrievalExecutor(ABC):
    """Abstract base class for structural retrieval executors."""

    @abstractmethod
    async def execute(
        self, repo_name: str, targets: List[str], params: Dict[str, Any]
    ) -> List[ContextReference]:
        """Runs the retrieval step and returns a list of stable ContextReferences."""
        pass


class SubgraphExecutor(RetrievalExecutor):
    """Retrieves subgraph nodes and relationships from the Knowledge Graph Navigator."""

    def __init__(self, navigator: Optional[Any] = None) -> None:
        self.navigator = navigator

    def get_navigator(self) -> Any:
        if self.navigator is None:
            from backend.dependencies import repository_knowledge_graph_navigator

            self.navigator = repository_knowledge_graph_navigator
        return self.navigator

    async def execute(
        self, repo_name: str, targets: List[str], params: Dict[str, Any]
    ) -> List[ContextReference]:
        navigator = self.get_navigator()
        if not targets:
            # Fallback: try to find entrypoints
            entrypoints = navigator.find_entrypoints(repo_name)
            targets = [e.id for e in entrypoints[:5]]

        max_depth = params.get("max_depth", 2)
        edge_types = params.get("edge_types")

        try:
            subgraph_data = navigator.extract_subgraph(
                repo_name,
                root_entities=targets,
                max_depth=max_depth,
                edge_types=edge_types,
            )
        except Exception as e:
            logger.warning("Subgraph extraction failed in executor: %s", e)
            return []

        references = []
        for node in subgraph_data.get("nodes", []):
            node_id = node.get("id")
            node_type = node.get("type", "unknown")
            props = node.get("properties", {})
            references.append(
                ContextReference(
                    id=node_id,
                    type=node_type,
                    source="subgraph",
                    properties=props,
                )
            )
        return references


class SymbolExecutor(RetrievalExecutor):
    """Expands resolved entities to symbol definitions and references."""

    def __init__(self, symbol_service: Optional[Any] = None) -> None:
        self.symbol_service = symbol_service

    def get_service(self) -> Any:
        if self.symbol_service is None:
            from backend.dependencies import symbol_service

            self.symbol_service = symbol_service
        return self.symbol_service

    async def execute(
        self, repo_name: str, targets: List[str], params: Dict[str, Any]
    ) -> List[ContextReference]:
        symbol_service = self.get_service()
        references = []
        for target in targets:
            # target ID might have prefix like repo_name::file_path::name, extract symbol name
            symbol_name = target
            if "::" in target:
                parts = target.split("::")
                symbol_name = parts[-1]

            # 1. Resolve definition
            definition = symbol_service.get_definition(repo_name, symbol_name)
            if definition:
                norm_file = definition.file_path.replace("\\", "/")
                qualified_name = (
                    f"{definition.parent_class}.{definition.name}"
                    if definition.parent_class
                    else definition.name
                )
                symbol_id = f"{repo_name}::{norm_file}::{qualified_name}"
                references.append(
                    ContextReference(
                        id=symbol_id,
                        type="symbol",
                        source="symbol_expansion",
                        properties={
                            "name": definition.name,
                            "file_path": norm_file,
                            "line_number": definition.line_number,
                            "symbol_type": definition.type,
                            "definition": True,
                        },
                    )
                )

            # 2. Resolve references
            refs = symbol_service.get_references(repo_name, symbol_name) or []
            for ref in refs[:20]:  # limit to prevent pollution
                norm_file = ref.file_path.replace("\\", "/")
                qualified_name = (
                    f"{ref.parent_class}.{ref.name}" if ref.parent_class else ref.name
                )
                symbol_id = f"{repo_name}::{norm_file}::{qualified_name}"
                references.append(
                    ContextReference(
                        id=symbol_id,
                        type="symbol",
                        source="symbol_expansion",
                        properties={
                            "name": ref.name,
                            "file_path": norm_file,
                            "line_number": ref.line_number,
                            "symbol_type": ref.type,
                            "definition": False,
                        },
                    )
                )
        return references


class DependencyExecutor(RetrievalExecutor):
    """Walks file dependency imports and dependents."""

    def __init__(self, graph_service: Optional[Any] = None) -> None:
        self.graph_service = graph_service

    def get_service(self) -> Any:
        if self.graph_service is None:
            from backend.dependencies import graph_service

            self.graph_service = graph_service
        return self.graph_service

    async def execute(
        self, repo_name: str, targets: List[str], params: Dict[str, Any]
    ) -> List[ContextReference]:
        graph_service = self.get_service()
        dep_graph = graph_service.load_graph(repo_name)
        if dep_graph is None:
            return []

        references = []
        for target in targets:
            # Normalize target file path if applicable
            norm_target = target.replace("\\", "/")
            # Target might be in format repo_name::file_path, strip prefix if so
            if "::" in norm_target:
                parts = norm_target.split("::", 1)
                if len(parts) > 1 and "/" in parts[1]:
                    norm_target = parts[1]

            if not dep_graph.has_node(norm_target):
                continue

            # 1. Successors (Imports)
            for succ in dep_graph.successors(norm_target):
                references.append(
                    ContextReference(
                        id=f"{repo_name}::{succ}",
                        type="file",
                        source="dependency_expansion",
                        properties={"relationship": "imports", "path": succ},
                    )
                )

            # 2. Predecessors (Dependents)
            for pred in dep_graph.predecessors(norm_target):
                references.append(
                    ContextReference(
                        id=f"{repo_name}::{pred}",
                        type="file",
                        source="dependency_expansion",
                        properties={"relationship": "imported_by", "path": pred},
                    )
                )
        return references


class EmbeddingExecutor(RetrievalExecutor):
    """Retrieves supplementary text chunks and documentation from Chroma DB."""

    def __init__(self, retrieval_service: Optional[Any] = None) -> None:
        self.retrieval_service = retrieval_service

    def get_service(self) -> Any:
        if self.retrieval_service is None:
            from backend.dependencies import get_retrieval_pipeline

            self.retrieval_service = get_retrieval_pipeline()
        return self.retrieval_service

    async def execute(
        self, repo_name: str, targets: List[str], params: Dict[str, Any]
    ) -> List[ContextReference]:
        query = params.get("query")
        if not query:
            return []

        srv = self.get_service()
        try:
            chroma_store = srv.chroma_store
            query_embed = srv.embedding_service.generate_embeddings([query])[0]
            results = chroma_store.collection.query(
                query_embeddings=[query_embed],
                n_results=5,
                where={"repo_name": repo_name},
            )
        except Exception as e:
            logger.warning("Embedding retrieval failed in executor: %s", e)
            return []

        references = []
        if results and "documents" in results and results["documents"]:
            docs = results["documents"][0]
            metadatas = results["metadatas"][0] if "metadatas" in results else []
            ids = results["ids"][0] if "ids" in results else []

            for idx, doc in enumerate(docs):
                meta = metadatas[idx] if idx < len(metadatas) else {}
                file_path = meta.get("file_path", "unknown")
                chunk_id = ids[idx] if idx < len(ids) else f"chunk_{idx}"
                references.append(
                    ContextReference(
                        id=f"{repo_name}::doc::{chunk_id}",
                        type="document",
                        source="embedding",
                        properties={"file_path": file_path, "metadata": meta},
                        snippet=doc,
                    )
                )
        return references


class RepositoryContextAssembler:
    """Assembles, normalizes, and ranks retrieved ContextReferences into a unified DTO."""

    def __init__(
        self, git_history_service: Optional[Any] = None, navigator: Optional[Any] = None
    ) -> None:
        self.git_history_service = git_history_service
        self.navigator = navigator

    def get_git_history_service(self) -> Any:
        if self.git_history_service is None:
            from backend.dependencies import git_history_service

            self.git_history_service = git_history_service
        return self.git_history_service

    def get_navigator(self) -> Any:
        if self.navigator is None:
            from backend.dependencies import repository_knowledge_graph_navigator

            self.navigator = repository_knowledge_graph_navigator
        return self.navigator

    def assemble(
        self,
        repo_name: str,
        question: str,
        references_lists: List[List[ContextReference]],
        policy: str,
        resolved_entities: List[str],
        confidence: float,
    ) -> RepositoryRetrievalContext:
        # 1. Flatten and deduplicate references by stable ID
        seen_refs: Dict[str, ContextReference] = {}
        for ref_list in references_lists:
            for ref in ref_list:
                if ref.id not in seen_refs:
                    seen_refs[ref.id] = ref
                else:
                    existing = seen_refs[ref.id]
                    existing.properties.update(ref.properties)
                    if ref.snippet:
                        existing.snippet = ref.snippet

        references = list(seen_refs.values())

        # 2. Rank references based on signals (type priority, hotspot score)
        hotspots: Set[str] = set()
        try:
            ghs = self.get_git_history_service()
            churn = ghs.load(repo_name)
            if churn and churn.hotspots:
                hotspots = {h.file_path for h in churn.hotspots[:10]}
        except Exception:
            pass

        # Sort order weight: Repository (10) > Component (9) > Health/Compliance (8) > File (6) > Symbol (4) > Document (2)
        type_weights = {
            "repository": 10,
            "component": 9,
            "health": 8,
            "compliance": 8,
            "file": 6,
            "symbol": 4,
            "document": 2,
        }

        def score_reference(ref: ContextReference) -> float:
            score = float(type_weights.get(ref.type, 0))

            file_path = ref.properties.get("file_path") or ref.properties.get("path")
            if not file_path and "::" in ref.id:
                parts = ref.id.split("::")
                if len(parts) > 1 and "/" in parts[1]:
                    file_path = parts[1]

            if file_path and file_path in hotspots:
                score += 3.0

            for ent in resolved_entities:
                if ent.lower() in ref.id.lower():
                    score += 5.0
                    break

            return score

        references.sort(key=score_reference, reverse=True)

        # 3. Extract unified subgraph slice using top entities
        seed_ids = [ref.id for ref in references if ref.type in {"file", "symbol"}][:5]
        subgraph = None
        if seed_ids:
            try:
                nav = self.get_navigator()
                subgraph = nav.extract_subgraph(
                    repo_name,
                    root_entities=seed_ids,
                    max_depth=2,
                    max_nodes=30,
                    max_edges=100,
                )
            except Exception:
                pass

        metrics = {
            "total_references": len(references),
            "files_count": sum(1 for r in references if r.type == "file"),
            "symbols_count": sum(1 for r in references if r.type == "symbol"),
            "documents_count": sum(1 for r in references if r.type == "document"),
        }

        explanation = RetrievalExplanation(
            resolved_entities=resolved_entities,
            policy=policy,
            confidence=confidence,
            metrics=metrics,
        )

        return RepositoryRetrievalContext(
            repository_name=repo_name,
            question=question,
            references=references,
            subgraph=subgraph,
            explanation=explanation,
        )


class StructuralRetrievalEngine:
    """Core policy-driven planning & execution retrieval engine."""

    def __init__(
        self,
        navigator: Optional[Any] = None,
        symbol_service: Optional[Any] = None,
        graph_service: Optional[Any] = None,
        retrieval_service: Optional[Any] = None,
        assembler: Optional[RepositoryContextAssembler] = None,
    ) -> None:
        """Initialise the Structural Retrieval Engine."""
        self.navigator = navigator
        self.symbol_service = symbol_service
        self.graph_service = graph_service
        self.retrieval_service = retrieval_service
        self.assembler = assembler or RepositoryContextAssembler(navigator=navigator)

        # Map executors with NO constructor parameters to avoid imports on startup
        self.executors: Dict[str, RetrievalExecutor] = {
            "subgraph": SubgraphExecutor(navigator=navigator),
            "symbol": SymbolExecutor(symbol_service=symbol_service),
            "dependency": DependencyExecutor(graph_service=graph_service),
            "embedding": EmbeddingExecutor(retrieval_service=retrieval_service),
        }

        self.intent_detector = RuleBasedIntentDetector()

    def get_navigator(self) -> Any:
        if self.navigator is None:
            from backend.dependencies import repository_knowledge_graph_navigator

            self.navigator = repository_knowledge_graph_navigator
        return self.navigator

    def generate_plan(self, question: str, policy: str) -> RetrievalPlan:
        """Generates a RetrievalPlan containing structured steps based on policy and question."""
        intent_res = self.intent_detector.detect(question)
        targets = intent_res.entities if intent_res.entities else []

        steps = []
        if policy == "architecture":
            steps.append(
                RetrievalPlanStep(
                    executor="subgraph", targets=targets, parameters={"max_depth": 2}
                )
            )
            steps.append(RetrievalPlanStep(executor="dependency", targets=targets))
        elif policy == "implementation":
            steps.append(RetrievalPlanStep(executor="symbol", targets=targets))
            steps.append(
                RetrievalPlanStep(
                    executor="subgraph", targets=targets, parameters={"max_depth": 1}
                )
            )
            steps.append(
                RetrievalPlanStep(
                    executor="embedding",
                    targets=targets,
                    parameters={"query": question},
                )
            )
        elif policy == "impact":
            steps.append(
                RetrievalPlanStep(
                    executor="subgraph", targets=targets, parameters={"max_depth": 3}
                )
            )
            steps.append(RetrievalPlanStep(executor="dependency", targets=targets))
            steps.append(RetrievalPlanStep(executor="symbol", targets=targets))
        elif policy == "security" or policy == "performance":
            steps.append(
                RetrievalPlanStep(
                    executor="subgraph", targets=targets, parameters={"max_depth": 2}
                )
            )
            steps.append(RetrievalPlanStep(executor="dependency", targets=targets))
            steps.append(
                RetrievalPlanStep(
                    executor="embedding",
                    targets=targets,
                    parameters={"query": question},
                )
            )
        else:
            steps.append(
                RetrievalPlanStep(
                    executor="subgraph", targets=targets, parameters={"max_depth": 2}
                )
            )
            steps.append(RetrievalPlanStep(executor="symbol", targets=targets))
            steps.append(
                RetrievalPlanStep(
                    executor="embedding",
                    targets=targets,
                    parameters={"query": question},
                )
            )

        return RetrievalPlan(policy=policy, steps=steps)

    async def retrieve(
        self, repo_name: str, question: str, policy: str = "default"
    ) -> RepositoryRetrievalContext:
        """Executes a policy-driven retrieval plan and returns the assembled RepositoryRetrievalContext."""
        intent_res = self.intent_detector.detect(question)
        resolved_entities = intent_res.entities if intent_res.entities else []

        plan = self.generate_plan(question, policy)

        tasks = []
        for step in plan.steps:
            executor = self.executors.get(step.executor)
            if executor:
                targets = step.targets
                if not targets:
                    targets = resolved_entities

                mapped_targets = []
                for t in targets:
                    if "/" in t:
                        t_clean = t.replace("\\", "/")
                        mapped_targets.append(f"{repo_name}::{t_clean}")
                    else:
                        mapped_targets.append(t)

                tasks.append(
                    executor.execute(repo_name, mapped_targets, step.parameters)
                )

        results_lists = await asyncio.gather(*tasks)

        return self.assembler.assemble(
            repo_name=repo_name,
            question=question,
            references_lists=results_lists,
            policy=policy,
            resolved_entities=resolved_entities,
            confidence=intent_res.confidence,
        )
