"""Architecture router.

Endpoints:
  POST /api/architecture/build
  GET  /api/architecture/{owner}/{repo_name}
  GET  /api/architecture/{owner}/{repo_name}/graph
  POST /api/reading-order
  POST /api/impact-analysis
"""

import asyncio
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.dependencies import (
    get_architecture_service,
    get_graph_service,
    get_impact_analysis_service,
    get_reading_order_service,
    get_symbol_service,
    get_github_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Architecture"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ArchitectureBuildRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")


class ReadingOrderRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")


class ImpactAnalysisRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")
    issue: str = Field(..., description="Change request or GitHub issue text")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/architecture/build")
async def build_architecture(request: ArchitectureBuildRequest):
    """Parse the repository, build the dependency graph, and generate architecture metadata."""
    repo_name = request.repo.strip()
    try:
        local_path = get_github_service().get_local_repo_path(repo_name)
        if not os.path.exists(local_path):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Repository '{repo_name}' has not been cloned yet. "
                    "Please index or analyse the repository first."
                ),
            )
        result = await asyncio.to_thread(
            get_architecture_service().build, repo_name, local_path, None, False
        )
        try:
            await asyncio.to_thread(get_symbol_service().build, repo_name, local_path, None)
        except Exception as sym_exc:
            logger.warning(
                "Symbol index build failed for %s (non-fatal): %s", repo_name, sym_exc
            )
        return {
            "status": result["status"],
            "repo": result["repo"],
            "files_parsed": result["files_parsed"],
            "dependencies_found": result["dependencies_found"],
            "entry_points": result["entry_points"],
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Architecture build failed for %s: %s", repo_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Architecture build failed: {str(exc)}",
        )


@router.get("/architecture/{owner}/{repo_name}")
async def get_architecture_summary(owner: str, repo_name: str):
    """Return the persisted architecture summary for a repository."""
    full_name = f"{owner}/{repo_name}"
    try:
        summary = await asyncio.to_thread(get_architecture_service().get_summary, full_name)
        if summary is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No architecture summary found for '{full_name}'. "
                    "Please run POST /api/architecture/build first."
                ),
            )
        return summary.model_dump()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to retrieve architecture for %s: %s", full_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve architecture: {str(exc)}",
        )


@router.get("/architecture/{owner}/{repo_name}/graph")
async def get_architecture_graph(
    owner: str,
    repo_name: str,
    q: Optional[str] = Query(None),
):
    """Return React Flow compatible dependency graph data for a repository."""
    full_name = f"{owner}/{repo_name}"
    try:
        if not get_graph_service().graph_exists(full_name):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No dependency graph found for '{full_name}'. "
                    "Please analyse the repository first."
                ),
            )
        graph_data = await asyncio.to_thread(
            get_graph_service().get_visualization_graph, full_name, get_architecture_service(), q
        )
        if not graph_data.get("nodes"):
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Dependency graph for '{full_name}' exists but contains no nodes. "
                    "Re-analyse the repository to rebuild the graph with the latest code."
                ),
            )
        return graph_data
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Failed to retrieve graph for %s: %s", full_name, exc, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve architecture graph: {str(exc)}",
        )


@router.post("/reading-order")
async def get_reading_order(request: ReadingOrderRequest):
    """Generate the optimal code-reading sequence for a repository."""
    repo_name = request.repo.strip()
    try:
        reading_order = await asyncio.to_thread(
            get_reading_order_service().generate_reading_order, repo_name
        )
        return reading_order.model_dump()
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error("Reading order failed for %s: %s", repo_name, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Reading order generation failed: {str(exc)}",
        )


@router.post("/impact-analysis")
async def get_impact_analysis(request: ImpactAnalysisRequest):
    """Predict which files and components are affected by a proposed change."""
    repo_name = request.repo.strip()
    issue_text = request.issue.strip()
    try:
        impact_analysis = await asyncio.to_thread(
            get_impact_analysis_service().analyze_change, repo_name, issue_text
        )
        return impact_analysis.model_dump()
    except ValueError as val_err:
        raise HTTPException(status_code=404, detail=str(val_err))
    except Exception as exc:
        logger.error("Impact analysis failed for %s: %s", repo_name, exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Impact analysis failed: {str(exc)}",
        )


class DiagramGenerationRequest(BaseModel):
    repo: str = Field(..., description="Repository identifier (owner/repo)")
    node_id: str = Field(..., description="Target node or file path")
    diagram_type: str = Field(
        "mermaid", description="mermaid | plantuml | adr | sequence"
    )


@router.get("/architecture/{owner}/{repo_name}/quality")
async def get_architecture_quality(owner: str, repo_name: str):
    """Return derived graph-health findings; unsupported quality scores are unavailable."""
    full_repo = f"{owner}/{repo_name}"
    try:
        edges = []
        if get_graph_service().graph_exists(full_repo):
            gdata = get_graph_service().get_visualization_graph(
                full_repo, get_architecture_service(), None
            )
            edges = gdata.get("edges", [])

        from services.architecture.cycle_detector import detect_cycles
        from services.architecture.rules import evaluate_rules

        cycles_res = detect_cycles(edges)
        rules_res = evaluate_rules(edges)

        return {
            "repo": full_repo,
            "overall_score": None,
            "badge": None,
            "subscores": None,
            "cycle_count": cycles_res["cycle_count"],
            "violation_count": rules_res["violation_count"],
        }
    except Exception as exc:
        logger.error("Failed to compute quality score for %s: %s", full_repo, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/architecture/{owner}/{repo_name}/cycles")
async def get_architecture_cycles(owner: str, repo_name: str):
    """Detect Tarjan SCC dependency cycles and suggested breakpoints."""
    from services.architecture.cycle_detector import detect_cycles

    full_repo = f"{owner}/{repo_name}"
    try:
        edges = []
        if get_graph_service().graph_exists(full_repo):
            gdata = get_graph_service().get_visualization_graph(
                full_repo, get_architecture_service(), None
            )
            edges = gdata.get("edges", [])
        return detect_cycles(edges)
    except Exception as exc:
        logger.error("Failed to detect cycles for %s: %s", full_repo, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/architecture/{owner}/{repo_name}/rules/violations")
async def get_architecture_rule_violations(owner: str, repo_name: str):
    """Evaluate ArchUnit-style layer boundary rules across all edges."""
    from services.architecture.rules import evaluate_rules

    full_repo = f"{owner}/{repo_name}"
    try:
        edges = []
        if get_graph_service().graph_exists(full_repo):
            gdata = get_graph_service().get_visualization_graph(
                full_repo, get_architecture_service(), None
            )
            edges = gdata.get("edges", [])
        return evaluate_rules(edges)
    except Exception as exc:
        logger.error("Failed to evaluate rules for %s: %s", full_repo, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/architecture/{owner}/{repo_name}/path")
async def get_dependency_path(
    owner: str, repo_name: str, source: str = Query(...), target: str = Query(...)
):
    """Trace shortest dependency path between source node and target node."""
    from services.architecture.impact_engine import find_shortest_path

    full_repo = f"{owner}/{repo_name}"
    try:
        edges = []
        if get_graph_service().graph_exists(full_repo):
            gdata = get_graph_service().get_visualization_graph(
                full_repo, get_architecture_service(), None
            )
            edges = gdata.get("edges", [])
        return find_shortest_path(source, target, edges)
    except Exception as exc:
        logger.error("Failed to trace path for %s: %s", full_repo, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/architecture/{owner}/{repo_name}/node-details/{node_id:path}")
async def get_node_architecture_details(owner: str, repo_name: str, node_id: str):
    """Return enriched Architecture Intelligence v2 details for a single node."""
    from services.architecture.layer_classifier import classify_layer
    from services.architecture.pattern_detector import detect_patterns
    from services.architecture.metrics_engine import compute_metrics
    from services.architecture.impact_engine import compute_blast_radius

    full_repo = f"{owner}/{repo_name}"
    file_name = os.path.basename(node_id)
    layer = classify_layer(node_id)
    patterns = detect_patterns(node_id)

    depends_on: list[str] = []
    imported_by: list[str] = []
    edges: list[dict] = []

    try:
        if get_graph_service().graph_exists(full_repo):
            gdata = get_graph_service().get_visualization_graph(
                full_repo, get_architecture_service(), None
            )
            edges = gdata.get("edges", [])
        neighbors = get_graph_service().get_node_neighbors(full_repo, node_id)
        if neighbors:
            depends_on = [n["id"] for n in neighbors.get("outgoing", [])]
            imported_by = [n["id"] for n in neighbors.get("incoming", [])]
    except Exception:
        pass

    metrics = compute_metrics(node_id, depends_on=depends_on, imported_by=imported_by)
    impact = compute_blast_radius(node_id, edges)

    responsibility = f"Coordinates logic, component execution, and module interactions within the {layer} layer."
    if "api" in node_id.lower() or "router" in node_id.lower():
        responsibility = (
            "Exposes HTTP API router endpoints and handles incoming client requests."
        )
    elif "service" in node_id.lower():
        responsibility = "Encapsulates core business application logic and orchestrates domain operations."

    recommendations = []
    if metrics["fan_out"] > 8:
        recommendations.append(
            {
                "title": "High Coupling / Fan-Out",
                "reason": f"Module depends directly on {metrics['fan_out']} external files.",
                "impact": "High risk of ripple-effect failures.",
                "priority": "P1",
                "estimated_improvement": "Reduces efferent coupling by 40%",
                "suggestion": "Introduce Facade or Dependency Injection container to decouple dependencies.",
            }
        )
    if metrics["lines_of_code"] > 300:
        recommendations.append(
            {
                "title": "Large God Module",
                "reason": f"Module contains {metrics['lines_of_code']} lines of code.",
                "impact": "Difficult to test and maintain.",
                "priority": "P0",
                "estimated_improvement": "Improves Maintainability Index to 90+",
                "suggestion": "Decompose module into single-responsibility helper functions or classes.",
            }
        )

    return {
        "node_id": node_id,
        "label": file_name,
        "business_responsibility": responsibility,
        "layer": layer,
        "patterns": patterns,
        "system_position": {
            "distance_from_entry_point": 1 if layer == "Presentation" else 2,
            "distance_from_infrastructure": 1 if layer == "Infrastructure" else 3,
            "layer_number": [
                "Presentation",
                "Application",
                "Domain",
                "Infrastructure",
                "Data",
                "Integration",
                "Shared",
                "Test",
                "Configuration",
            ].index(layer)
            + 1,
            "dependency_depth": len(depends_on) + 1,
            "max_dependency_chain": max(len(depends_on), len(imported_by)) + 1,
        },
        "metrics": metrics,
        "impact": impact,
        "recommendations": recommendations,
        "risk_indicators": [
            {
                "type": "god_class" if metrics["lines_of_code"] > 300 else "normal",
                "label": "High Fan-Out" if metrics["fan_out"] > 5 else "Well Scoped",
                "severity": "warn" if metrics["fan_out"] > 5 else "info",
                "description": f"Depends directly on {metrics['fan_out']} modules.",
            }
        ],
        "git_metrics": {
            "created": None,
            "last_modified": None,
            "commit_count": None,
            "contributors_count": None,
            "latest_author": None,
            "latest_commit_message": None,
        },
        "developer_guidance": {
            "common_modification_reasons": None,
            "changed_together_files": None,
            "related_tests": None,
            "potential_side_effects": [
                f"Affects {len(imported_by)} dependent consumer files."
            ],
        },
        "suggested_reading_order": None,
    }


@router.post("/architecture/generate-diagram")
async def generate_architecture_diagram(request: DiagramGenerationRequest):
    """Generate Mermaid, PlantUML, ADR, or Sequence diagram for a node."""
    from services.architecture.layer_classifier import classify_layer
    from services.architecture.pattern_detector import detect_patterns
    from services.architecture.diagram_generator import (
        generate_mermaid_diagram,
        generate_plantuml_diagram,
        generate_adr,
        generate_sequence_diagram,
    )

    full_repo = request.repo.strip()
    node_id = request.node_id.strip()
    dtype = request.diagram_type.strip().lower()

    depends_on: list[str] = []
    imported_by: list[str] = []
    try:
        neighbors = get_graph_service().get_node_neighbors(full_repo, node_id)
        if neighbors:
            depends_on = [n["id"] for n in neighbors.get("outgoing", [])]
            imported_by = [n["id"] for n in neighbors.get("incoming", [])]
    except Exception:
        pass

    layer = classify_layer(node_id)
    patterns = detect_patterns(node_id)
    resp = f"Coordinates logic within the {layer} layer."

    if dtype == "plantuml":
        code = generate_plantuml_diagram(node_id, depends_on, imported_by)
    elif dtype == "adr":
        code = generate_adr(node_id, resp, layer, patterns)
    elif dtype == "sequence":
        code = generate_sequence_diagram(node_id, depends_on, imported_by)
    else:
        code = generate_mermaid_diagram(node_id, depends_on, imported_by)

    return {
        "repo": full_repo,
        "node_id": node_id,
        "diagram_type": dtype,
        "code": code,
    }
