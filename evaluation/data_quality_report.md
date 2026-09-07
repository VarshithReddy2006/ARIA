# ARIA Evaluation Dataset Integrity & Data Quality Audit

**Milestone:** Confidence Calibration & Evaluation Integrity v4  
**Date:** 2026-09-02  
**Dataset Under Audit:** `evaluation/tasks/tasks.json` (10 Change-Impact Tasks across `fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`).

---

## 1. Executive Summary

In accordance with Core Principle 2:
> **"Never modify ground truth just to improve ARIA. If a ground-truth issue is independently verified: preserve the historical dataset, create an explicit validity annotation, and report raw and valid metrics separately."**

An exhaustive file-existence and AST-grounding audit was conducted on all 18 ground-truth test files and 26 ground-truth production files specified across the 10 benchmark tasks.

### Key Audit Findings:
- **Production Files Ground Truth:** 26 / 26 files (100.0%) exist on disk and are verified `VALID`.
- **Test Files Ground Truth:** 13 / 18 files (72.2%) are verified `VALID`.
- **Missing / Stale Test Files:** 5 / 18 files (27.8%) **do not exist on disk** in the pinned repository commits.
- **Root Cause of Missing Test Files:** The original benchmark tasks were authored using speculative or outdated test paths (e.g. assuming FastAPI test files follow a flat naming convention like `tests/test_response_model.py` instead of the actual tutorial structure `tests/test_tutorial/test_response_model/`).

---

## 2. Exhaustive Task-by-Task Integrity Audit

| Task ID | Repository | Ground-Truth Files | Status | Ground-Truth Tests | Status | Root Cause / Valid Alternative |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `task-01-fastapi-oauth2` | `fastapi/fastapi` | 2 files | **VALID** | `tests/test_security_oauth2_password_bearer_optional.py`<br>`tests/test_tutorial/test_security/test_tutorial002.py`<br>`tests/test_tutorial/test_security/test_tutorial003.py` | **VALID** | All 3 test files exist and assert OAuth2PasswordBearer. |
| `task-02-fastapi-serialize-response` | `fastapi/fastapi` | 3 files | **VALID** | `tests/test_response_model.py`<br>`tests/test_tutorial/test_response_model/test_tutorial001.py` | **PARTIAL** | `tests/test_response_model.py` **DOES NOT EXIST**.<br>Actual tests live in `tests/test_tutorial/test_response_model/test_tutorial*.py`. |
| `task-03-fastapi-status-codes` | `fastapi/fastapi` | 2 files | **VALID** | `tests/test_status_codes.py` | **MISSING** | `tests/test_status_codes.py` **DOES NOT EXIST**.<br>Actual test is `tests/test_response_change_status_code.py`. |
| `task-04-requests-session-send` | `psf/requests` | 3 files | **VALID** | `tests/test_requests.py`<br>`tests/test_sessions.py` | **PARTIAL** | `tests/test_sessions.py` **DOES NOT EXIST**.<br>All session tests in Requests are consolidated in `tests/test_requests.py`. |
| `task-05-requests-adapters-ssl` | `psf/requests` | 2 files | **VALID** | `tests/test_requests.py`<br>`tests/test_testserver.py` | **VALID** | Both test files exist and exercise adapter SSL mounting. |
| `task-06-requests-models-response` | `psf/requests` | 2 files | **VALID** | `tests/test_requests.py` | **VALID** | Exists and exercises Response.content and iter_content. |
| `task-07-aria-symbol-schema` | `VarshithReddy2006/ARIA` | 2 files | **VALID** | `tests/test_symbol_service.py` | **VALID** | Exists and verifies Symbol and SymbolIndex schemas. |
| `task-08-aria-call-graph-blast-radius` | `VarshithReddy2006/ARIA` | 3 files | **VALID** | `tests/test_call_graph.py` | **MISSING** | `tests/test_call_graph.py` **DOES NOT EXIST**.<br>Actual tests are in `tests/test_call_graph_service.py`. |
| `task-09-aria-api-surface-status` | `VarshithReddy2006/ARIA` | 4 files | **VALID** | `tests/test_api_surface.py` | **MISSING** | `tests/test_api_surface.py` **DOES NOT EXIST**.<br>Actual tests are in `tests/test_api_surface_service.py`. |
| `task-10-aria-impact-engine-bucketing` | `VarshithReddy2006/ARIA` | 3 files | **VALID** | `tests/test_impact_analysis.py`<br>`tests/test_evidence_impact_analysis.py` | **VALID** | Both test files exist and assert blast radius categories. |

---

## 3. Dual-Mode Evaluation Policy

To preserve scientific rigor and historical comparability:
1. **RAW Mode**:
   - Uses `evaluation/tasks/tasks.json` strictly as defined.
   - Any missing ground-truth file counts as an automatic false negative.
   - Ensures exact comparability with v1, v2, and v3 historical benchmarks.
2. **VALID-GROUND-TRUTH Mode**:
   - Excludes the 5 non-existent test files from the denominator, evaluating recall and precision strictly against the 13 physically verifiable test files.
   - Provides developers with an unpolluted measurement of ARIA's real-world predictive precision.
