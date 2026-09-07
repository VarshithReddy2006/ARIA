# ARIA Confidence Misclassification & Error Analysis

**Milestone:** Confidence Calibration & Evaluation Integrity v4  
**Date:** 2026-09-02

---

## 1. HIGH False Positives (Severity: CRITICAL)
- **Observed Behavior:** In the independent calibration dataset, HIGH-tier precision achieved **100%** (31/31 verified correct) with **zero false positives**.
- **Historical Analysis:** In v1 and uncalibrated models, HIGH false positives occurred primarily from:
  1. *Unqualified symbol collisions* (e.g. `send` matching both `Session.send` and raw `sock.send`). Resolved in v3 via parent-class qualification and import validation.
  2. *Wildcard imports* (`from module import *`).
  3. *Unrelated helper functions with common names* (`get`, `parse`, `validate`).
- **Policy:** Any rule generating HIGH tier must require verifiable AST evidence: exact definition, explicit AST call on a verified instance, or verified HTTP route contract.

---

## 2. LOW True Positives (Severity: MEDIUM - Recall Loss)
- **Observed Behavior:** Candidates in `LEVEL_6_MODULE_DEPENDENCY` (coarse module imports without symbol references) had an empirical correctness rate of **0.0%** when evaluated as direct impact.
- **Root Cause:** In modern Python frameworks (e.g. FastAPI), foundation modules such as `fastapi/routing.py` or `fastapi/applications.py` are imported by hundreds of tutorial files, documentation examples, and unrelated endpoints.
- **Resolution:**
  - Downstream modules importing a modified file *without* referencing the changed symbol must remain in `LOW` (`EXPLORATORY CANDIDATE`).
  - They should NOT be promoted to `MEDIUM` or bundled into `directly_affected_files` or `indirectly_affected_files`.

---

## 3. MEDIUM True Positives (Severity: MEDIUM - Promotion Opportunity)
- **Observed Candidates:**
  - `tests/test_impact_analysis.py` for Task 10 was previously classified as `MEDIUM` because `ImpactAnalysisService` (CamelCase) did not match `impact_analysis_service.py` (snake_case).
  - Normalizing CamelCase to snake_case allows `_inspect_test_file_ast` to identify that the test directly imports the primary service class of the changed file, correctly promoting it to `HIGH`.
  - Multi-hop helper chains (`LEVEL_3_SYMBOL_DEPENDENCY` at depth $\le$ 2) achieved 100% precision in calibration and represent reliable `LIKELY IMPACT` items.

---

## 4. HIGH False Negatives (Severity: HIGH - Missing Impact)
- **Identified Missing Impacts:**
  - In Task 6 (`requests-models-response`), tests interacting with `Response.content` via the higher-level client (`r = requests.get(...)`) were previously classified as MEDIUM rather than HIGH because the test called `requests.get` rather than `Response()`.
  - Adding property access detection (`r.content`) when `r` is a known return type resolves this false negative.
