"""Stress and Scalability Tests for Foundation Iteration 1."""

from pathlib import Path

from ria.evaluation import BenchmarkHarness, DatasetGenerator, PerformanceBaseline, RegressionSuite


def test_stress_deep_nested_directory(tmp_path: Path) -> None:
    dataset = DatasetGenerator.create_deep_nested_repo(tmp_path, depth=5)
    harness = BenchmarkHarness(work_dir=tmp_path / "work_deep")

    index_batch, result = harness.run_benchmark(dataset)

    assert result.file_count == 5
    assert len(index_batch.parse_units) == 5
    assert result.peak_memory_bytes > 0


def test_stress_repeated_sync_and_indexing_cycles(tmp_path: Path) -> None:
    dataset = DatasetGenerator.create_small_mixed_repo(tmp_path, py_files=5, ts_files=5, js_files=5)
    harness = BenchmarkHarness(work_dir=tmp_path / "work_repeat")

    # Cycle 1
    batch1, res1 = harness.run_benchmark(dataset)
    # Cycle 2
    batch2, res2 = harness.run_benchmark(dataset)

    assert res1.file_count == 15
    assert res2.file_count == 15
    # Memory growth check
    assert res2.peak_memory_bytes < res1.peak_memory_bytes * 3.0
