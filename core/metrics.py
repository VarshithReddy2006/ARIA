"""Lightweight Metrics Registry — delegated to core.observability.metrics."""

from core.observability.metrics import (
    MetricsCollector,
    MetricsExporter,
    PrometheusExporter,
    metrics_collector,
)

# Backward-compatible alias
MetricsRegistry = MetricsCollector
metrics_registry = metrics_collector

__all__ = [
    "MetricsCollector",
    "MetricsExporter",
    "PrometheusExporter",
    "MetricsRegistry",
    "metrics_registry",
]
