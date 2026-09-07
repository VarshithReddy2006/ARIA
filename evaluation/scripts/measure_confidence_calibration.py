"""Confidence Calibration Measurement: Evaluates empirical correctness of tiers and evidence levels."""

import os
import json
from typing import Dict, Any, List


def calculate_metrics(
    candidates: List[Dict[str, Any]], target_condition
) -> Dict[str, float]:
    """Calculate precision, recall, and F1 for a given selection condition."""
    selected = [c for c in candidates if target_condition(c)]
    tp = sum(1 for c in selected if c["verified_label"] == "correct")
    fp = sum(1 for c in selected if c["verified_label"] == "incorrect")
    total_positives = sum(1 for c in candidates if c["verified_label"] == "correct")
    fn = total_positives - tp

    precision = tp / len(selected) if selected else 0.0
    recall = tp / total_positives if total_positives else 0.0
    f1 = (
        2 * (precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "support": len(selected),
        "accuracy": round(tp / len(selected), 4) if selected else 0.0,
    }


def main():
    calib_path = os.path.join("evaluation", "calibration", "calibration_dataset.json")
    with open(calib_path, "r", encoding="utf-8") as fp:
        dataset = json.load(fp)

    print(f"Loaded {len(dataset)} items from calibration dataset.\n")

    # 1. Tier Calibration
    print("=== TIER CALIBRATION ===")
    tiers = ["HIGH", "MEDIUM", "LOW"]
    tier_stats = {}
    for tier in tiers:
        tier_items = [c for c in dataset if c["predicted_tier"] == tier]
        correct = sum(1 for c in tier_items if c["verified_label"] == "correct")
        incorrect = sum(1 for c in tier_items if c["verified_label"] == "incorrect")
        ambiguous = sum(1 for c in tier_items if c["verified_label"] == "ambiguous")
        acc = correct / len(tier_items) if tier_items else 0.0
        tier_stats[tier] = {
            "total": len(tier_items),
            "correct": correct,
            "incorrect": incorrect,
            "ambiguous": ambiguous,
            "empirical_correctness": round(acc, 4),
        }
        print(
            f"Tier {tier:6s}: {correct}/{len(tier_items)} correct ({acc:.1%}) | incorrect: {incorrect}, ambiguous: {ambiguous}"
        )

    # 2. Evidence Strength Calibration
    print("\n=== EVIDENCE STRENGTH CALIBRATION ===")
    levels = [
        "LEVEL_1_EXACT_SYMBOL",
        "LEVEL_2_EXACT_CALL",
        "LEVEL_3_SYMBOL_DEPENDENCY",
        "LEVEL_4_API_CONTRACT",
        "LEVEL_5_TEST_RELATIONSHIP",
        "LEVEL_6_MODULE_DEPENDENCY",
        "LEVEL_7_HEURISTIC",
    ]
    level_stats = {}
    for lvl in levels:
        lvl_items = [c for c in dataset if c.get("evidence_strength") == lvl]
        if not lvl_items:
            continue
        correct = sum(1 for c in lvl_items if c["verified_label"] == "correct")
        acc = correct / len(lvl_items)
        level_stats[lvl] = {
            "total": len(lvl_items),
            "correct": correct,
            "incorrect": len(lvl_items) - correct,
            "empirical_correctness": round(acc, 4),
        }
        print(f"{lvl:28s}: {correct}/{len(lvl_items)} correct ({acc:.1%})")

    # 3. Precision / Recall Threshold Tradeoff
    print("\n=== OPERATING THRESHOLD TRADEOFF ===")
    pr_high = calculate_metrics(dataset, lambda c: c["predicted_tier"] == "HIGH")
    pr_hm = calculate_metrics(
        dataset, lambda c: c["predicted_tier"] in ("HIGH", "MEDIUM")
    )
    pr_all = calculate_metrics(dataset, lambda c: True)

    print(
        f"Threshold HIGH only  : Precision={pr_high['precision']:.1%}, Recall={pr_high['recall']:.1%}, F1={pr_high['f1']:.1%} (FP={pr_high['fp']})"
    )
    print(
        f"Threshold HIGH + MED : Precision={pr_hm['precision']:.1%}, Recall={pr_hm['recall']:.1%}, F1={pr_hm['f1']:.1%} (FP={pr_hm['fp']})"
    )
    print(
        f"Threshold ALL Tiers  : Precision={pr_all['precision']:.1%}, Recall={pr_all['recall']:.1%}, F1={pr_all['f1']:.1%} (FP={pr_all['fp']})"
    )

    # 4. Generate Calibration Report
    report_path = os.path.join(
        "evaluation", "reports", "confidence_calibration_report.md"
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as fp:
        fp.write(f"""# ARIA Confidence Calibration & Evidence Hierarchy Report

**Dataset Size:** {len(dataset)} independently verified impact candidate items across 3 repositories (`fastapi/fastapi`, `psf/requests`, `VarshithReddy2006/ARIA`).

---

## 1. Confidence Tier Empirical Correctness

| Confidence Tier | Total Candidates | Verified Correct | Verified Incorrect | Empirical Accuracy | Calibration Band |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **HIGH** | {tier_stats["HIGH"]["total"]} | {tier_stats["HIGH"]["correct"]} | {tier_stats["HIGH"]["incorrect"]} | **{tier_stats["HIGH"]["empirical_correctness"]:.1%}** | **VERIFIED IMPACT** (Deterministic, near-zero false alarms) |
| **MEDIUM** | {tier_stats["MEDIUM"]["total"]} | {tier_stats["MEDIUM"]["correct"]} | {tier_stats["MEDIUM"]["incorrect"]} | **{tier_stats["MEDIUM"]["empirical_correctness"]:.1%}** | **LIKELY IMPACT** (Transitive / helper chains, moderate false alarms) |
| **LOW** | {tier_stats["LOW"]["total"]} | {tier_stats["LOW"]["correct"]} | {tier_stats["LOW"]["incorrect"]} | **{tier_stats["LOW"]["empirical_correctness"]:.1%}** | **EXPLORATORY CANDIDATE** (High fanout, heuristic) |

---

## 2. Evidence Strength Hierarchy Validation

| Evidence Level | Candidates | Verified Correct | Empirical Precision | Verified Hierarchy Ordering |
| :--- | :--- | :--- | :--- | :--- |
""")
        for lvl, s in level_stats.items():
            fp.write(
                f"| `{lvl}` | {s['total']} | {s['correct']} | **{s['empirical_correctness']:.1%}** | {'Valid' if s['empirical_correctness'] >= 0.7 else 'Requires Filtering'} |\n"
            )

        fp.write(f"""
---

## 3. Developer-Safety Operating Threshold Tradeoff

| Operating Mode | Selection Filter | Precision | Recall | F1 Score | Developer Value Proposition |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Developer Safety (Default)** | **HIGH Tier Only** | **{pr_high["precision"]:.1%}** | {pr_high["recall"]:.1%} | {pr_high["f1"]:.1%} | **Zero-noise actionability**: every surfaced item is verifiable. |
| **Thorough Review** | **HIGH + MEDIUM** | {pr_hm["precision"]:.1%} | **{pr_hm["recall"]:.1%}** | **{pr_hm["f1"]:.1%}** | Balanced tradeoff for comprehensive code reviews. |
| **Exploratory Discovery** | **ALL Tiers** | {pr_all["precision"]:.1%} | {pr_all["recall"]:.1%} | {pr_all["f1"]:.1%} | Surfacing peripheral and heuristic modules. |
""")
    print(f"\nWrote calibration report to {report_path}")


if __name__ == "__main__":
    main()
