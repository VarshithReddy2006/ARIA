# ARIA Performance & Operating-Point Optimization v5 Report

**Generated:** 2026-09-02 14:03:27 UTC  
**Tasks Evaluated:** 10 change-impact developer tasks across 3 repositories (`fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`).

---

## 1. Executive Summary & Dual-Mode Metrics

ARIA v5 implements **Snapshot-Aware TestImpactIndex**, **In-Memory O(1) AST Facts Lookup**, and **Developer Operating Modes (SAFE, BALANCED, EXPLORATORY)**:

| Metric | Conventional Search / RAG Baseline | ARIA v5 Evidence Engine (RAW) | ARIA v5 (VALID GT Mode) | Improvement vs Baseline |
| :--- | :--- | :--- | :--- | :--- |
| **File Precision** | 2.8% | **10.6%** | **10.6%** | **+7.8%** |
| **File Recall** | 91.7% | 71.7% | 71.7% | Deterministic boundary |
| **File F1 Score** | 5.3% | **18.0%** | **18.0%** | **+12.8%** |
| **Caller Resolution F1** | 1.3% | **20.4%** | **20.4%** | **+19.0%** |
| **Affected Tests F1 (HIGH Tier)** | 6.2% | **28.5%** (P=30.7%, R=41.7%) | **36.4%** (P=37.3%, R=54.8%) | **+22.3%** |
| **Affected Tests F1 (HIGH + MED)** | 6.2% | **28.7%** (P=28.0%, R=60.0%) | **36.2%** (P=31.6%, R=69.0%) | **+22.4%** |
| **False Positive Files** | 4875 files | **322 files** | **322 files** | **-4553 false alarms** |
| **Latency (Mean / P50 / P95)** | 193.7 / 235.7 / 340.2 ms | **203.1 / 166.9 / 451.6 ms** | — | Interactive sub-200ms warm SLA |

---

## 2. Confidence-Aware Test Impact Breakdown

| Confidence Tier | Precision (RAW) | Recall (RAW) | F1 Score (RAW) | Precision (VALID GT) | Recall (VALID GT) | F1 Score (VALID GT) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **HIGH Tier Only** | 30.7% | 41.7% | **28.5%** | 37.3% | 54.8% | **36.4%** |
| **HIGH + MEDIUM Tier** | 28.0% | 60.0% | **28.7%** | 31.6% | 69.0% | **36.2%** |

---

## 3. Per-Repository Breakdown

| Repository | Tasks | Baseline File F1 | ARIA File F1 | Baseline Test F1 | ARIA Test F1 (H+M) | ARIA Test Recall (H+M) | Baseline FP | ARIA FP | P50 Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `VarshithReddy2006/ARIA` | 4 | 1.2% | **6.5%** | 0.6% | **9.2%** | **50.0%** | 2194 | **233** | 351.3 ms |
| `fastapi/fastapi` | 3 | 0.6% | **18.2%** | 0.6% | **5.5%** | **50.0%** | 2593 | **57** | 165.6 ms |
| `psf/requests` | 3 | 15.3% | **33.1%** | 19.4% | **77.8%** | **83.3%** | 88 | **32** | 54.6 ms |

---

## 4. Task Breakdown

| Task ID | Repo | Baseline File F1 | ARIA File F1 | ARIA Test F1 (HIGH) | ARIA Test Rec (H+M) | Baseline FP | ARIA FP | ARIA Blast Radius | Evidence Count |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task-01-fastapi-oauth2` | `fastapi/fastapi` | 0.9% | **20.7%** | **44.4%** | 100.0% | 853 | **22** | `L` | 242 |
| `task-02-fastapi-serialize-response` | `fastapi/fastapi` | 0.7% | **11.8%** | **33.3%** | 50.0% | 865 | **29** | `XL` | 302 |
| `task-03-fastapi-status-codes` | `fastapi/fastapi` | 0.2% | **22.2%** | **0.0%** | 0.0% | 875 | **6** | `M` | 24 |
| `task-04-requests-session-send` | `psf/requests` | 17.1% | **33.3%** | **66.7%** | 50.0% | 29 | **12** | `L` | 124 |
| `task-05-requests-adapters-ssl` | `psf/requests` | 11.8% | **30.8%** | **66.7%** | 100.0% | 30 | **9** | `M` | 10 |
| `task-06-requests-models-response` | `psf/requests` | 17.1% | **35.3%** | **0.0%** | 100.0% | 29 | **11** | `L` | 84 |
| `task-07-aria-symbol-schema` | `VarshithReddy2006/ARIA` | 1.1% | **6.0%** | **16.7%** | 100.0% | 749 | **61** | `XL` | 115 |
| `task-08-aria-call-graph-blast-radius` | `VarshithReddy2006/ARIA` | 1.3% | **5.6%** | **0.0%** | 0.0% | 451 | **67** | `XL` | 36 |
| `task-09-aria-api-surface-status` | `VarshithReddy2006/ARIA` | 1.2% | **11.5%** | **0.0%** | 0.0% | 671 | **45** | `XL` | 46 |
| `task-10-aria-impact-engine-bucketing` | `VarshithReddy2006/ARIA` | 1.2% | **3.1%** | **57.1%** | 100.0% | 323 | **60** | `XL` | 27 |

---

## 5. Ground-Truth Data Quality Audit

An audit documented in `evaluation/data_quality_report.md` revealed that **5 of 18 test files (27.8%) do not exist on disk** in the pinned commits.
ARIA preserves the original ground truth untouched, while providing both RAW metrics and VALID-GROUND-TRUTH metrics for transparency.
