"""Metrics router — GET /metrics."""

from fastapi import APIRouter, Response
from core.metrics import metrics_registry

router = APIRouter(tags=["Metrics"])


@router.get("/metrics")
def get_metrics():
    """Returns Prometheus metrics."""
    from backend.dependencies import analysis_cache

    metrics_data = metrics_registry.generate_prometheus_metrics(cache=analysis_cache)
    return Response(content=metrics_data, media_type="text/plain; version=0.0.4")
