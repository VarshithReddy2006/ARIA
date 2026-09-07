# ARIA Evaluation & Benchmark Suite

This directory contains the reproducible empirical evaluation framework for **ARIA (AI-Powered Repository Intelligence)**.

Its objective is to prove that ARIA's deterministic, evidence-backed impact engine solves the central developer question:

> **“What will break if I change this?”**

far more accurately than conventional code search, keyword matching, and naive vector RAG.

---

## 1. Directory Structure

```
evaluation/
├── README.md                  # This documentation
├── tasks/
│   └── tasks.json             # 10 realistic change-impact tasks with pinned git hashes & ground truth
├── runners/
│   ├── baseline_runner.py     # Conventional grep & text-chunk RAG baseline
│   └── aria_runner.py         # Real ARIA deterministic impact engine runner
├── scripts/
│   ├── run_eval.py            # Executes evaluation across all 10 tasks; computes metrics
│   ├── run_incremental_benchmarks.py  # Measures fresh vs 1-file, 3-file, 10-file diff re-indexing
│   └── prove_aria_vs_rag.py   # Head-to-head proof script comparing ARIA vs RAG on refactoring tasks
├── results/
│   ├── results.json           # Machine-readable output with per-task metrics and raw predictions
│   ├── results.csv            # Tabular summary of precision, recall, F1, latency, and FP
│   └── incremental_benchmarks.json  # Latency, memory RSS, and re-parsed file counts
└── reports/
    └── report.md              # Auto-generated markdown validation report
```

---

## 2. Representative Repositories

The benchmark operates over 3 pinned open-source and internal repositories:
1. **`fastapi/fastapi`** (`49033471594ea5d99a80abdf1043231b7791ee49`)
   - Complex dependency web, dynamic router decorators, security schemes (`OAuth2PasswordBearer`).
2. **`psf/requests`** (`5460f467b02e49471c0fd6cfc9ca0adab6351f98`)
   - Standard Python HTTP library, session management, adapter layers, SSL hooks.
3. **`VarshithReddy2006/ARIA`** (`bbc81833baa1b2c6c01a63528bf270a653281729`)
   - Production repository intelligence architecture with Tree-sitter ASTs, NetworkX call graphs, and FastAPI backends.

---

## 3. Evaluation Tasks & Ground Truth

`tasks/tasks.json` defines 10 developer tasks. Each task specifies:
- `task_id`: Unique identifier
- `repository` & `revision`: Pinned git commit
- `change_description`: Natural language change or refactor request
- `ground_truth_files`: Manually audited files directly required for the change
- `ground_truth_symbols`: Core symbols affected
- `ground_truth_callers`: Real call sites invoking the target symbols
- `ground_truth_dependencies`: Dependent subsystems
- `ground_truth_tests`: Targeted regression test suites
- `ground_truth_api_surfaces`: Public API interfaces or routes exposed
- `ground_truth_risk`: Risk rating (`low`, `medium`, `high`, `extreme`)

---

## 4. Empirical Evaluation Metrics

For each task and runner, the orchestrator evaluates:
- **Precision**: $\frac{TP}{TP + FP}$
- **Recall**: $\frac{TP}{TP + FN}$
- **F1 Score**: $2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$
- **False Positive Count**: Irrelevant files erroneously flagged as affected
- **Query Latency**: Wall-clock response time in milliseconds
- **Evidence Integrity**: Presence of exact `FACT` items referencing valid `file_path:line_number`

---

## 5. Reproduction Instructions

To reproduce all benchmarks and generate fresh reports:

### 1. Run the Core Empirical Evaluation
```bash
python evaluation/scripts/run_eval.py
```
Outputs:
- `evaluation/results/results.json`
- `evaluation/results/results.csv`
- `evaluation/reports/report.md`

### 2. Run Incremental Re-Indexing Benchmarks
```bash
python evaluation/scripts/run_incremental_benchmarks.py
```
Outputs:
- `evaluation/results/incremental_benchmarks.json`

### 3. Run Head-to-Head ARIA vs RAG Proof
```bash
python evaluation/scripts/prove_aria_vs_rag.py
```

### 4. Run Automated Trust-Critical Unit & Contract Tests
```bash
pytest tests/test_evidence_impact_analysis.py tests/test_impact_analysis.py tests/test_mcp_fastmcp_parity.py -v
```
