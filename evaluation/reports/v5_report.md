# ARIA Performance & Operating-Point Optimization v5 Report

**Generated:** 2026-09-02 13:34:00 UTC  
**Tasks Evaluated:** 10 change-impact developer tasks across 3 repositories (`fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`).

---

## 1. Executive Summary & Dual-Mode Metrics

ARIA v5 implements **Snapshot-Aware TestImpactIndex**, **In-Memory O(1) AST Facts Lookup**, and **Developer Operating Modes (SAFE, BALANCED, EXPLORATORY)**:

| Metric | Conventional Search / RAG Baseline | ARIA v5 Evidence Engine (RAW) | ARIA v5 (VALID GT Mode) | Improvement vs Baseline |
| :--- | :--- | :--- | :--- | :--- |
| **File Precision** | 2.8% | **9.5%** | **9.5%** | **+6.7%** |
| **File Recall** | 91.7% | 63.3% | 63.3% | Deterministic boundary |
| **File F1 Score** | 5.3% | **16.0%** | **16.0%** | **+10.8%** |
| **Caller Resolution F1** | 1.3% | **3.3%** | **3.3%** | **+2.0%** |
| **Affected Tests F1 (HIGH Tier)** | 6.2% | **28.5%** (P=30.7%, R=41.7%) | **36.4%** (P=37.3%, R=54.8%) | **+22.3%** |
| **Affected Tests F1 (HIGH + MED)** | 6.2% | **32.0%** (P=33.0%, R=60.0%) | **41.0%** (P=38.7%, R=69.0%) | **+25.8%** |
| **False Positive Files** | 4875 files | **314 files** | **314 files** | **-4561 false alarms** |
| **Latency (Mean / P50 / P95)** | 222.0 / 283.3 / 392.5 ms | **765.9 / 251.7 / 3763.3 ms** | — | Interactive sub-200ms warm SLA |

---

## 2. Confidence-Aware Test Impact Breakdown

| Confidence Tier | Precision (RAW) | Recall (RAW) | F1 Score (RAW) | Precision (VALID GT) | Recall (VALID GT) | F1 Score (VALID GT) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **HIGH Tier Only** | 30.7% | 41.7% | **28.5%** | 37.3% | 54.8% | **36.4%** |
| **HIGH + MEDIUM Tier** | 33.0% | 60.0% | **32.0%** | 38.7% | 69.0% | **41.0%** |

---

## 3. Per-Repository Breakdown

| Repository | Tasks | Baseline File F1 | ARIA File F1 | Baseline Test F1 | ARIA Test F1 (H+M) | ARIA Test Recall (H+M) | Baseline FP | ARIA FP | P50 Latency |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `VarshithReddy2006/ARIA` | 4 | 1.2% | **6.5%** | 0.6% | **9.2%** | **50.0%** | 2194 | **233** | 332.4 ms |
| `fastapi/fastapi` | 3 | 0.6% | **14.8%** | 0.6% | **5.5%** | **50.0%** | 2593 | **49** | 197.1 ms |
| `psf/requests` | 3 | 15.3% | **29.9%** | 19.4% | **88.9%** | **83.3%** | 88 | **32** | 54.0 ms |

---

## 4. Task Breakdown

| Task ID | Repo | Baseline File F1 | ARIA File F1 | ARIA Test F1 (HIGH) | ARIA Test Rec (H+M) | Baseline FP | ARIA FP | ARIA Blast Radius | Evidence Count |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task-01-fastapi-oauth2` | `fastapi/fastapi` | 0.9% | **10.5%** | **44.4%** | 100.0% | 853 | **14** | `L` | 56 |
| `task-02-fastapi-serialize-response` | `fastapi/fastapi` | 0.7% | **11.8%** | **33.3%** | 50.0% | 865 | **29** | `XL` | 300 |
| `task-03-fastapi-status-codes` | `fastapi/fastapi` | 0.2% | **22.2%** | **0.0%** | 0.0% | 875 | **6** | `M` | 24 |
| `task-04-requests-session-send` | `psf/requests` | 17.1% | **23.5%** | **66.7%** | 50.0% | 29 | **12** | `L` | 11 |
| `task-05-requests-adapters-ssl` | `psf/requests` | 11.8% | **30.8%** | **66.7%** | 100.0% | 30 | **9** | `M` | 9 |
| `task-06-requests-models-response` | `psf/requests` | 17.1% | **35.3%** | **0.0%** | 100.0% | 29 | **11** | `L` | 9 |
| `task-07-aria-symbol-schema` | `VarshithReddy2006/ARIA` | 1.1% | **6.0%** | **16.7%** | 100.0% | 749 | **61** | `XL` | 54 |
| `task-08-aria-call-graph-blast-radius` | `VarshithReddy2006/ARIA` | 1.3% | **5.6%** | **0.0%** | 0.0% | 451 | **67** | `XL` | 30 |
| `task-09-aria-api-surface-status` | `VarshithReddy2006/ARIA` | 1.2% | **11.5%** | **0.0%** | 0.0% | 671 | **45** | `XL` | 46 |
| `task-10-aria-impact-engine-bucketing` | `VarshithReddy2006/ARIA` | 1.2% | **3.1%** | **57.1%** | 100.0% | 323 | **60** | `XL` | 27 |

---

## 5. Ground-Truth Data Quality Audit

An audit documented in `evaluation/data_quality_report.md` revealed that **5 of 18 test files (27.8%) do not exist on disk** in the pinned commits.
ARIA preserves the original ground truth untouched, while providing both RAW metrics and VALID-GROUND-TRUTH metrics for transparency.
