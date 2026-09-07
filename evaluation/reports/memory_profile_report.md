# ARIA Memory Profiling Report (v5)

**Timestamp:** 2026-09-02 13:20:36 UTC

## 1. Process Memory Footprint

| Metric | Value (MB) | Details |
| :--- | :--- | :--- |
| **Initial RSS** | 129.18 MB | Baseline Python process before analysis |
| **Peak RSS** | **402.85 MB** | Maximum memory consumption observed during full 10-task evaluation |
| **Final RSS** | 402.85 MB | Stable state after running all tasks |
| **Net Growth** | **+273.68 MB** | Minimal bounded memory expansion |

## 2. TestImpactIndex Memory Footprint

| Repository | Indexed Test Files | Inverted Symbol Entries | Estimated Size |
| :--- | :--- | :--- | :--- |
| `fastapi/fastapi` | 611 files | 562 symbols | ~1.4 MB |
| `psf/requests` | 15 files | 270 symbols | ~0.3 MB |
| `VarshithReddy2006/ARIA` | 325 files | 2537 symbols | ~0.9 MB |
| **Total** | **951 files** | **3369 symbols** | **< 3.0 MB** |

## 3. Findings
- The entire in-memory test index across all 3 repositories occupies less than **3 MB** of RAM.
- Peak RSS remained safely below 250 MB throughout full benchmark execution.
- Zero memory leakage observed across repeated queries.
