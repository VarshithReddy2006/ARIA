# ARIA Impact Analysis Latency Profile Report

**Timestamp:** 2026-09-02 13:02:11 UTC  
**Tasks Profiled:** 10 tasks across `fastapi/fastapi`, `psf/requests`, and `VarshithReddy2006/ARIA`.

---

## Latency Summary

| Metric | Measured Value |
| :--- | :--- |
| **Mean Latency** | **1465.19 ms** |
| **P50 (Median)** | **1005.50 ms** |
| **P95 Latency** | **3805.60 ms** |
| **Minimum** | 86.18 ms |
| **Maximum** | 3805.60 ms |

---

## Per-Task Breakdown

| Task ID | Repository | Latency (ms) | Affected Files | Affected Tests |
| :--- | :--- | :--- | :--- | :--- |
| `task-01-fastapi-oauth2` | `fastapi/fastapi` | 1190.96 ms | 54 | 38 |
| `task-02-fastapi-serialize-response` | `fastapi/fastapi` | 724.62 ms | 274 | 243 |
| `task-03-fastapi-status-codes` | `fastapi/fastapi` | 820.03 ms | 15 | 3 |
| `task-04-requests-session-send` | `psf/requests` | 114.97 ms | 16 | 2 |
| `task-05-requests-adapters-ssl` | `psf/requests` | 93.14 ms | 13 | 2 |
| `task-06-requests-models-response` | `psf/requests` | 86.18 ms | 15 | 1 |
| `task-07-aria-symbol-schema` | `VarshithReddy2006/ARIA` | 3805.60 ms | 106 | 45 |
| `task-08-aria-call-graph-blast-radius` | `VarshithReddy2006/ARIA` | 2746.72 ms | 91 | 25 |
| `task-09-aria-api-surface-status` | `VarshithReddy2006/ARIA` | 2659.08 ms | 76 | 30 |
| `task-10-aria-impact-engine-bucketing` | `VarshithReddy2006/ARIA` | 2410.64 ms | 80 | 22 |
