# ARIA Cold vs Warm vs Incremental Benchmark (v5)

## 1. Latency Breakdown

| Operational State | Mean Latency | P50 (Median) | P95 (Max) | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Cold Index Queries** | **641.68 ms** | 239.84 ms | 3001.14 ms | Initial snapshot encounter, builds in-memory TestImpactIndex |
| **Warm Cached Queries** | **133.57 ms** | **117.28 ms** | **230.35 ms** | Subsequent developer queries against indexed snapshot (interactive SLA) |
| **Incremental Update** | **24.30 ms** | 2.45 ms | 67.00 ms | Single test file modified; updates inverted index in-place without rebuilding |

## 2. Per-Task Measurements

| Task ID | Repo | Cold Latency (ms) | Warm Latency (ms) | Speedup Factor |
| :--- | :--- | :--- | :--- | :--- |
| `task-01-fastapi-oauth2` | `fastapi/fastapi` | 1890.81 ms | **113.68 ms** | **16.6x** |
| `task-02-fastapi-serialize-response` | `fastapi/fastapi` | 180.46 ms | **120.87 ms** | **1.5x** |
| `task-03-fastapi-status-codes` | `fastapi/fastapi` | 180.41 ms | **95.96 ms** | **1.9x** |
| `task-04-requests-session-send` | `psf/requests` | 271.89 ms | **45.99 ms** | **5.9x** |
| `task-05-requests-adapters-ssl` | `psf/requests` | 62.48 ms | **49.54 ms** | **1.3x** |
| `task-06-requests-models-response` | `psf/requests` | 49.82 ms | **40.96 ms** | **1.2x** |
| `task-07-aria-symbol-schema` | `VarshithReddy2006/ARIA` | 3001.14 ms | **208.95 ms** | **14.4x** |
| `task-08-aria-call-graph-blast-radius` | `VarshithReddy2006/ARIA` | 244.12 ms | **209.34 ms** | **1.2x** |
| `task-09-aria-api-surface-status` | `VarshithReddy2006/ARIA` | 235.55 ms | **230.35 ms** | **1.0x** |
| `task-10-aria-impact-engine-bucketing` | `VarshithReddy2006/ARIA` | 300.09 ms | **220.04 ms** | **1.4x** |
