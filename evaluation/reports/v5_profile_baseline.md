# ARIA Stage-Level Latency Baseline Profile (v5 Baseline)

**Tasks Profiled:** 10 tasks across `fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`
**Total Query Latency:** Mean=844.52 ms | P50=248.65 ms | P95=4869.52 ms

---

## Stage Breakdown

| Stage | Calls | Total Time (ms) | Mean (ms) | P50 (ms) | P95 (ms) | % of Total Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `api_matching` | 10 | 1106.28 ms | 110.628 ms | 2.457 ms | 1050.335 ms | **59.6%** |
| `call_graph_traversal` | 10 | 493.92 ms | 49.392 ms | 0.135 ms | 444.410 ms | **26.6%** |
| `symbol_resolution` | 10 | 196.02 ms | 19.602 ms | 0.505 ms | 166.158 ms | **10.6%** |
| `symbol_reference_detection` | 223 | 59.13 ms | 0.265 ms | 0.145 ms | 3.631 ms | **3.2%** |
| `identifier_extraction` | 10 | 1.13 ms | 0.113 ms | 0.087 ms | 0.297 ms | **0.1%** |

---

## Dominant Bottleneck Analysis

1. **Primary Bottleneck:** `api_matching` accounts for **1106.28 ms (59.6%)** of all execution time across 10 calls.
2. **Secondary Bottleneck:** `call_graph_traversal` accounts for **493.92 ms (26.6%)** of execution time across 10 calls.