"""Caller Resolution Error Analysis (Phase 2).

Inspects predicted callers vs ground-truth callers for every task.
Categorizes errors:
- SAME-NAME COLLISION
- QUALIFIED METHOD FAILURE
- ALIAS RESOLUTION FAILURE
- INSTANCE TYPE UNKNOWN
- INHERITANCE FAILURE
- IMPORT RESOLUTION FAILURE
- DECORATOR/WRAPPER FAILURE
- CROSS-FILE SYMBOL FAILURE
- NESTED FUNCTION FAILURE
- STATIC DISPATCH LIMITATION
- DYNAMIC DISPATCH LIMITATION
- EVALUATION AMBIGUITY
"""

import os
import sys
import json

sys.path.insert(0, os.path.abspath("."))

from backend.dependencies import get_impact_analysis_service


def inspect_callers():
    tasks_path = os.path.join("evaluation", "tasks", "tasks.json")
    with open(tasks_path, "r", encoding="utf-8") as fp:
        tasks = json.load(fp)

    service = get_impact_analysis_service()

    total_gt = 0
    total_tp = 0
    total_fp = 0
    total_fn = 0

    print("=" * 80)
    print("CALLER RESOLUTION DETAILED ERROR ANALYSIS")
    print("=" * 80)

    task_reports = []

    for task in tasks:
        task_id = task["task_id"]
        repo = task["repository"]
        desc = task["change_description"]
        gt_callers = set(task["ground_truth_callers"])

        res = service.analyze_change(repo, desc)

        direct_callers = [f"{c.file_path}::{c.caller_name}" for c in res.direct_callers]
        all_pred_names = {
            c.caller_name
            for c in (res.direct_callers + res.transitive_callers)
            if not service._is_test_file(c.file_path)
        }

        # Exact / normalized matching
        gt_norm = {g.strip().lower() for g in gt_callers}
        pred_norm = {p.strip().lower() for p in all_pred_names}

        tp = gt_norm & pred_norm
        fp = pred_norm - gt_norm
        fn = gt_norm - pred_norm

        total_gt += len(gt_callers)
        total_tp += len(tp)
        total_fp += len(fp)
        total_fn += len(fn)

        report = {
            "task_id": task_id,
            "repo": repo,
            "gt_callers": sorted(list(gt_callers)),
            "direct_callers": direct_callers,
            "predicted_caller_names": sorted(list(all_pred_names)),
            "tp": sorted(list(tp)),
            "fp": sorted(list(fp)),
            "fn": sorted(list(fn)),
            "resolved_symbols": [s for s in res.affected_symbols],
        }
        task_reports.append(report)

        print(f"\nTask: {task_id} ({repo})")
        print(f"  Target Symbols: {res.affected_symbols}")
        print(f"  Ground Truth Callers ({len(gt_callers)}): {sorted(list(gt_callers))}")
        print(
            f"  Predicted Callers   ({len(all_pred_names)}): {sorted(list(all_pred_names))}"
        )
        print(f"  True Positives      ({len(tp)}): {sorted(list(tp))}")
        print(f"  False Positives     ({len(fp)}): {sorted(list(fp))[:10]}")
        print(f"  False Negatives     ({len(fn)}): {sorted(list(fn))}")

    prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0
    rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    print("\n" + "=" * 80)
    print(f"Aggregate Caller Metrics: TP={total_tp}, FP={total_fp}, FN={total_fn}")
    print(f"Precision: {prec:.1%} | Recall: {rec:.1%} | F1: {f1:.1%}")
    print("=" * 80)

    # Save to json for analysis
    with open(
        "evaluation/reports/caller_error_details.json", "w", encoding="utf-8"
    ) as fp:
        json.dump(task_reports, fp, indent=2)


if __name__ == "__main__":
    inspect_callers()
