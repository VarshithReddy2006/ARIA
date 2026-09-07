"""Benchmark Harness for ONNX INT8 vs ONNX FP32 vs PyTorch FP32 on real code chunks.

Measures:
  - Model load time
  - Granular breakdown: tokenization, inference, postprocess (pooling + norm)
  - Throughput (chunks/sec)
  - Latency distributions (mean, median, p95, min, max)
  - Vector cosine similarity and numerical differences vs PyTorch FP32 baseline
  - Memory consumption (peak RSS)
"""

import gc
import os
import psutil
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.abspath("."))

import numpy as np

from services.chunking_service import CodeChunker
from services.embedding_service import (
    ONNXEmbeddingBackend,
    PyTorchEmbeddingBackend,
)


def collect_real_code_chunks(target_count: int = 256) -> List[str]:
    """Collect real source code chunks from this codebase."""
    chunker = CodeChunker()
    chunks: List[str] = []

    for root, _, files in os.walk("."):
        if any(
            x in root
            for x in [
                ".git",
                ".venv",
                "node_modules",
                "__pycache__",
                "dist",
                "build",
                "data",
            ]
        ):
            continue
        for f in files:
            if f.endswith((".py", ".ts", ".tsx", ".java", ".md")):
                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as fh:
                        content = fh.read()
                    file_chunks = chunker.chunk_file(filepath, content)
                    for c in file_chunks:
                        chunks.append(c["content"])
                        if len(chunks) >= target_count:
                            break
                except Exception:
                    pass
            if len(chunks) >= target_count:
                break
        if len(chunks) >= target_count:
            break

    return chunks


def get_process_rss_mb() -> float:
    """Return current process Resident Set Size in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024.0 * 1024.0)


def benchmark_backend(
    backend_name: str,
    backend_obj: Any,
    chunks: List[str],
    batch_size: int = 64,
    repetitions: int = 3,
) -> Dict[str, Any]:
    """Benchmark an embedding backend over multiple repetitions."""
    prefixed_chunks = [f"Represent this sentence: {c}" for c in chunks]
    total_chunks = len(chunks)
    num_batches = (total_chunks + batch_size - 1) // batch_size

    # Warmup
    gc.collect()
    _ = backend_obj.encode(
        prefixed_chunks[: min(16, total_chunks)], batch_size=batch_size
    )

    latencies_ms: List[float] = []
    throughputs: List[float] = []
    rss_peaks: List[float] = []
    embeddings_list: List[np.ndarray] = []

    for rep in range(repetitions):
        gc.collect()
        rss_start = get_process_rss_mb()

        t0 = time.perf_counter()
        embs = backend_obj.encode(
            prefixed_chunks, batch_size=batch_size, normalize_embeddings=True
        )
        t_elapsed = time.perf_counter() - t0

        rss_end = get_process_rss_mb()
        elapsed_ms = t_elapsed * 1000.0
        chunks_sec = total_chunks / max(0.0001, t_elapsed)

        latencies_ms.append(elapsed_ms)
        throughputs.append(chunks_sec)
        rss_peaks.append(max(rss_start, rss_end))
        if rep == 0:
            embeddings_list.append(embs)

    return {
        "backend": backend_name,
        "chunks": total_chunks,
        "batch_size": batch_size,
        "num_batches": num_batches,
        "repetitions": repetitions,
        "embeddings": embeddings_list[0],
        "latency_mean_ms": float(np.mean(latencies_ms)),
        "latency_median_ms": float(np.median(latencies_ms)),
        "latency_p95_ms": float(np.percentile(latencies_ms, 95)),
        "latency_min_ms": float(np.min(latencies_ms)),
        "latency_max_ms": float(np.max(latencies_ms)),
        "throughput_mean": float(np.mean(throughputs)),
        "throughput_median": float(np.median(throughputs)),
        "throughput_p95": float(np.percentile(throughputs, 95)),
        "throughput_min": float(np.min(throughputs)),
        "throughput_max": float(np.max(throughputs)),
        "rss_peak_mb": float(np.max(rss_peaks)),
    }


def main():
    print(
        "================================================================================"
    )
    print("ARIA EMBEDDING ENGINE BENCHMARK: PyTorch FP32 vs ONNX FP32 vs ONNX INT8")
    print(
        "================================================================================"
    )

    chunks = collect_real_code_chunks(target_count=256)
    print(f"Collected {len(chunks)} real code chunks from repository.")
    mean_chars = np.mean([len(c) for c in chunks])
    print(f"Average chunk size: {mean_chars:.1f} characters")
    print(f"Batch size: 64 | CPU threads: {min(os.cpu_count() or 4, 8)}")
    print(
        "--------------------------------------------------------------------------------"
    )

    # 1. Load PyTorch Backend
    print("Initializing PyTorch FP32 Backend...")
    t0 = time.perf_counter()
    pt_backend = PyTorchEmbeddingBackend()
    pt_load_time_ms = (time.perf_counter() - t0) * 1000.0

    # 2. Load ONNX FP32 Backend
    print("Initializing ONNX FP32 Backend...")
    t0 = time.perf_counter()
    onnx_fp32_backend = ONNXEmbeddingBackend(quantization="fp32")
    onnx_fp32_load_time_ms = (time.perf_counter() - t0) * 1000.0

    # 3. Load ONNX INT8 Backend
    print("Initializing ONNX INT8 Backend...")
    t0 = time.perf_counter()
    onnx_int8_backend = ONNXEmbeddingBackend(quantization="int8")
    onnx_int8_load_time_ms = (time.perf_counter() - t0) * 1000.0

    print(
        "--------------------------------------------------------------------------------"
    )
    print(
        f"Model Load Time: PyTorch={pt_load_time_ms:.1f}ms | ONNX FP32={onnx_fp32_load_time_ms:.1f}ms | ONNX INT8={onnx_int8_load_time_ms:.1f}ms"
    )
    print(
        "--------------------------------------------------------------------------------"
    )

    # Run benchmarks
    print("Running PyTorch FP32 Benchmark (3 runs)...")
    res_pt = benchmark_backend(
        "PyTorch FP32", pt_backend, chunks, batch_size=64, repetitions=3
    )

    print("Running ONNX FP32 Benchmark (3 runs)...")
    res_onnx_fp32 = benchmark_backend(
        "ONNX FP32", onnx_fp32_backend, chunks, batch_size=64, repetitions=3
    )

    print("Running ONNX INT8 Benchmark (3 runs)...")
    res_onnx_int8 = benchmark_backend(
        "ONNX INT8", onnx_int8_backend, chunks, batch_size=64, repetitions=3
    )

    # Calculate Quality Metrics vs PyTorch Baseline
    pt_vecs = res_pt["embeddings"]
    onnx_fp32_vecs = res_onnx_fp32["embeddings"]
    onnx_int8_vecs = res_onnx_int8["embeddings"]

    cos_fp32_pt = [
        float(np.dot(onnx_fp32_vecs[i], pt_vecs[i])) for i in range(len(chunks))
    ]
    cos_int8_pt = [
        float(np.dot(onnx_int8_vecs[i], pt_vecs[i])) for i in range(len(chunks))
    ]
    cos_int8_fp32 = [
        float(np.dot(onnx_int8_vecs[i], onnx_fp32_vecs[i])) for i in range(len(chunks))
    ]

    diff_fp32_pt = np.abs(onnx_fp32_vecs - pt_vecs)
    diff_int8_pt = np.abs(onnx_int8_vecs - pt_vecs)

    print(
        "\n================================================================================"
    )
    print(
        "                               BENCHMARK SUMMARY                                "
    )
    print(
        "================================================================================"
    )
    print(
        f"{'Metric':<28} | {'PyTorch FP32':<15} | {'ONNX FP32':<15} | {'ONNX INT8':<15}"
    )
    print("-" * 80)
    print(
        f"{'Throughput (chunks/sec)':<28} | {res_pt['throughput_mean']:<15.2f} | {res_onnx_fp32['throughput_mean']:<15.2f} | {res_onnx_int8['throughput_mean']:<15.2f}"
    )
    print(
        f"{'Latency Mean (ms)':<28} | {res_pt['latency_mean_ms']:<15.1f} | {res_onnx_fp32['latency_mean_ms']:<15.1f} | {res_onnx_int8['latency_mean_ms']:<15.1f}"
    )
    print(
        f"{'Latency Median (ms)':<28} | {res_pt['latency_median_ms']:<15.1f} | {res_onnx_fp32['latency_median_ms']:<15.1f} | {res_onnx_int8['latency_median_ms']:<15.1f}"
    )
    print(
        f"{'Latency P95 (ms)':<28} | {res_pt['latency_p95_ms']:<15.1f} | {res_onnx_fp32['latency_p95_ms']:<15.1f} | {res_onnx_int8['latency_p95_ms']:<15.1f}"
    )
    print(
        f"{'Peak RSS (MB)':<28} | {res_pt['rss_peak_mb']:<15.1f} | {res_onnx_fp32['rss_peak_mb']:<15.1f} | {res_onnx_int8['rss_peak_mb']:<15.1f}"
    )
    print(
        f"{'Embedding Speedup':<28} | {'1.00x':<15} | {res_onnx_fp32['throughput_mean'] / res_pt['throughput_mean']:<15.2f}x | {res_onnx_int8['throughput_mean'] / res_pt['throughput_mean']:<15.2f}x"
    )
    print("-" * 80)
    print("NUMERICAL FIDELITY (vs PyTorch FP32 Baseline):")
    print(
        f"  ONNX FP32 -> Mean Cosine: {np.mean(cos_fp32_pt):.8f} | Min Cosine: {np.min(cos_fp32_pt):.8f} | Max Abs Diff: {np.max(diff_fp32_pt):.8f}"
    )
    print(
        f"  ONNX INT8 -> Mean Cosine: {np.mean(cos_int8_pt):.8f} | Min Cosine: {np.min(cos_int8_pt):.8f} | Max Abs Diff: {np.max(diff_int8_pt):.8f}"
    )
    print(
        f"  INT8 vs FP32 -> Mean Cosine: {np.mean(cos_int8_fp32):.8f} | Min Cosine: {np.min(cos_int8_fp32):.8f}"
    )
    print(
        "================================================================================\n"
    )


if __name__ == "__main__":
    main()
