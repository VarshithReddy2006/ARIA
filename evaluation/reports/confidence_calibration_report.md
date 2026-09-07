# ARIA Confidence Calibration & Evidence Hierarchy Report

**Dataset Size:** 50 independently verified impact candidate items across 3 repositories (`fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`).

---

## 1. Confidence Tier Empirical Correctness

| Confidence Tier | Total Candidates | Verified Correct | Verified Incorrect | Empirical Accuracy | Calibration Band |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **HIGH** | 31 | 31 | 0 | **100.0%** | **VERIFIED IMPACT** (Deterministic, near-zero false alarms) |
| **MEDIUM** | 8 | 7 | 1 | **87.5%** | **LIKELY IMPACT** (Transitive / helper chains, moderate false alarms) |
| **LOW** | 11 | 0 | 11 | **0.0%** | **EXPLORATORY CANDIDATE** (High fanout, heuristic) |

---

## 2. Evidence Strength Hierarchy Validation

| Evidence Level | Candidates | Verified Correct | Empirical Precision | Verified Hierarchy Ordering |
| :--- | :--- | :--- | :--- | :--- |
| `LEVEL_1_EXACT_SYMBOL` | 20 | 20 | **100.0%** | Valid |
| `LEVEL_2_EXACT_CALL` | 9 | 9 | **100.0%** | Valid |
| `LEVEL_3_SYMBOL_DEPENDENCY` | 7 | 7 | **100.0%** | Valid |
| `LEVEL_4_API_CONTRACT` | 2 | 2 | **100.0%** | Valid |
| `LEVEL_5_TEST_RELATIONSHIP` | 1 | 0 | **0.0%** | Requires Filtering |
| `LEVEL_6_MODULE_DEPENDENCY` | 10 | 0 | **0.0%** | Requires Filtering |
| `LEVEL_7_HEURISTIC` | 1 | 0 | **0.0%** | Requires Filtering |

---

## 3. Developer-Safety Operating Threshold Tradeoff

| Operating Mode | Selection Filter | Precision | Recall | F1 Score | Developer Value Proposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Developer Safety (Default)** | **HIGH Tier Only** | **100.0%** | 81.6% | 89.9% | **Zero-noise actionability**: every surfaced item is verifiable. |
| **Thorough Review** | **HIGH + MEDIUM** | 97.4% | **100.0%** | **98.7%** | Balanced tradeoff for comprehensive code reviews. |
| **Exploratory Discovery** | **ALL Tiers** | 76.0% | 100.0% | 86.4% | Surfacing peripheral and heuristic modules. |
