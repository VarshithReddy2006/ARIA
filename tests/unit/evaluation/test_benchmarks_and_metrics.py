"""Unit tests for Benchmark Framework and Regression Suite."""

from pathlib import Path

from ria.evaluation import (
    BenchmarkHarness,
    DatasetGenerator,
    PerformanceBaseline,
    RegressionSuite,
    ReportGenerator,
)


def test_benchmark_harness_and_report_generation(tmp_path: Path) -> None:
    dataset = DatasetGenerator.create_small_mixed_repo(
        tmp_path, py_files=10, ts_files=10, js_files=10
    )
    harness = BenchmarkHarness(work_dir=tmp_path / "work")

    index_batch, result = harness.run_benchmark(dataset)

    assert result.file_count == 30
    assert result.overall_throughput_files_per_sec > 0.0
    assert len(result.stage_metrics) == 3
    assert len(index_batch.parse_units) == 30

    # Verify Regression Suite
    baseline = PerformanceBaseline(min_throughput_files_per_sec=1.0)
    regression_suite = RegressionSuite(baseline)
    violations = regression_suite.verify_no_regression(result)
    assert len(violations) == 0, f"Baseline regression violations: {violations}"

    # Verify Report Generator
    report_md = ReportGenerator.generate_benchmark_report([result])
    assert "Executive Summary" in report_md
    assert "RECOMMENDATION: FREEZE FOUNDATION ITERATION 1" in report_md
