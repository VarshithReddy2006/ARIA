"""Benchmark Dataset Manifest & Generator."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ria.domain.common.value_objects import Timestamp


@dataclass(frozen=True, slots=True)
class BenchmarkDatasetSpec:
    """Specification of a repository benchmark fixture."""

    name: str
    size_category: str  # Small (<1K), Medium (1K-10K), Large (10K-100K)
    language: str
    target_dir: Path
    file_count: int
    total_bytes: int
    commit_sha: str
    branch: str = "main"


class DatasetGenerator:
    """Generates synthetic multi-language benchmark repositories for performance validation."""

    @classmethod
    def create_small_mixed_repo(cls, root_dir: Path, py_files: int = 50, ts_files: int = 50, js_files: int = 50) -> BenchmarkDatasetSpec:
        """Create a small (~150 files) mixed Python/TypeScript/JavaScript repository fixture."""
        repo_dir = root_dir / "benchmark_small_mixed"
        repo_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Benchmarker"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "bench@test.com"], cwd=repo_dir, check=True)

        total_bytes = 0
        total_files = 0

        # Python files
        src_py = repo_dir / "src_py"
        src_py.mkdir()
        for i in range(py_files):
            p = src_py / f"module_{i}.py"
            code = f"# Python module {i}\ndef process_data_{i}(val: int) -> int:\n    return val * {i}\n"
            p.write_text(code)
            total_bytes += len(code)
            total_files += 1

        # TypeScript files
        src_ts = repo_dir / "src_ts"
        src_ts.mkdir()
        for i in range(ts_files):
            p = src_ts / f"service_{i}.ts"
            code = f"// TypeScript service {i}\nexport interface Model{i} {{\n  id: number;\n}}\nexport function fetch{i}(): Model{i} {{\n  return {{ id: {i} }};\n}}\n"
            p.write_text(code)
            total_bytes += len(code)
            total_files += 1

        # JavaScript files
        src_js = repo_dir / "src_js"
        src_js.mkdir()
        for i in range(js_files):
            p = src_js / f"util_{i}.js"
            code = f"// JS Utility {i}\nfunction compute_{i}(a, b) {{\n  return a + b + {i};\n}}\nmodule.exports = {{ compute_{i} }};\n"
            p.write_text(code)
            total_bytes += len(code)
            total_files += 1

        # Commit repository
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Benchmark dataset commit"], cwd=repo_dir, check=True, capture_output=True)

        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
        commit_sha = res.stdout.strip()

        return BenchmarkDatasetSpec(
            name="benchmark_small_mixed",
            size_category="Small (<1K files)",
            language="Mixed (Python, TypeScript, JavaScript)",
            target_dir=repo_dir,
            file_count=total_files,
            total_bytes=total_bytes,
            commit_sha=commit_sha,
            branch="main",
        )

    @classmethod
    def create_deep_nested_repo(cls, root_dir: Path, depth: int = 5) -> BenchmarkDatasetSpec:
        """Create a deep nested directory structure repository fixture for stress testing."""
        repo_dir = root_dir / "benchmark_deep_nested"
        repo_dir.mkdir(parents=True, exist_ok=True)

        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Benchmarker"], cwd=repo_dir, check=True)
        subprocess.run(["git", "config", "user.email", "bench@test.com"], cwd=repo_dir, check=True)

        curr = repo_dir
        total_files = 0
        total_bytes = 0

        for d in range(depth):
            curr = curr / f"level_{d}"
            curr.mkdir()
            p = curr / f"node_{d}.py"
            code = f"# Level {d}\nclass NodeLevel{d}:\n    pass\n"
            p.write_text(code)
            total_bytes += len(code)
            total_files += 1

        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Deep nested commit"], cwd=repo_dir, check=True, capture_output=True)

        res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
        commit_sha = res.stdout.strip()

        return BenchmarkDatasetSpec(
            name="benchmark_deep_nested",
            size_category="Small (Deep directory structure)",
            language="Python",
            target_dir=repo_dir,
            file_count=total_files,
            total_bytes=total_bytes,
            commit_sha=commit_sha,
            branch="main",
        )
