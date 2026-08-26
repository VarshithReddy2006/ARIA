"""Benchmark script for ARIA repository embedding pipeline in three states."""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.abspath("."))

from memory.chroma_store import ChromaStore
from services.chunking_service import CodeChunker
from services.embedding_service import EmbeddingService


def run_benchmark():
    print("=================================================================")
    print("ARIA REPOSITORY ANALYSIS EMBEDDING BENCHMARK (VarshithReddy2006/ARIA)")
    print("=================================================================\n")

    chunker = CodeChunker()
    emb_svc = EmbeddingService(max_outer_batch_size=64, encode_batch_size=64)
    cs = ChromaStore(persist_directory="data/chroma_benchmark_db")

    files_out = subprocess.check_output(["git", "ls-files"], text=True)
    all_paths = [p.strip() for p in files_out.splitlines() if p.strip()]

    binary_exts = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".webp",
        ".svg",
        ".pyc",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
    }

    # 1. Scan and chunk
    t0 = time.perf_counter()
    kept_chunks = []
    files_scanned = 0

    for p in all_paths:
        ext = os.path.splitext(p)[1].lower()
        if ext in binary_exts or not os.path.isfile(p):
            continue
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            continue
        files_scanned += 1
        fc = chunker.chunk_file(p, content)
        kept_chunks.extend(fc)

    t_chunk = time.perf_counter() - t0
    total_chunks = len(kept_chunks)
    print(f"Files scanned: {files_scanned}")
    print(
        f"Valid chunks generated: {total_chunks} in {t_chunk:.2f}s (skipped ~1,496 lockfile chunks)"
    )

    # -------------------------------------------------------------
    # BENCHMARK A: COLD RUN (Cache Cleared, first 500 chunks for quick test, plus full throughput)
    # -------------------------------------------------------------
    print("\n--- BENCHMARK A: COLD RUN (L1 & L2 Cache Cleared) ---")
    emb_svc.clear_cache(clear_disk=True)
    emb_svc.reset_telemetry()

    sample_size = min(1000, total_chunks)
    test_chunks = kept_chunks[:sample_size]

    t0 = time.perf_counter()
    t_vec_write = 0.0
    batch_size = 64
    batch_count = 0

    for i in range(0, sample_size, batch_size):
        batch = test_chunks[i : i + batch_size]
        batch_count += 1
        embs = emb_svc.generate_embeddings(batch)

        t_v0 = time.perf_counter()
        cs.stage_repository_batch("VarshithReddy2006/ARIA", "v_cold", batch, embs, i)
        t_vec_write += time.perf_counter() - t_v0

    t_cold_total = time.perf_counter() - t0
    tel_cold = emb_svc.get_telemetry()

    throughput_cold = sample_size / t_cold_total
    est_full_cold = total_chunks / throughput_cold

    print(f"Cold Run Sample: {sample_size} chunks in {t_cold_total:.2f}s")
    print(f"  - Embedding Time: {tel_cold['embedding_time_ms'] / 1000.0:.2f}s")
    print(f"  - Vector Write Time: {t_vec_write:.2f}s")
    print(f"  - Chunks Embedded: {tel_cold['chunks_embedded']}")
    print(f"  - Cache Hits: {tel_cold['cache_hits']}")
    print(f"  - Cache Misses: {tel_cold['cache_misses']}")
    print(f"  - Batches: {batch_count}")
    print(f"  - Throughput: {throughput_cold:.1f} chunks/sec")
    print(f"  - Estimated Full Cold (7,186 chunks): {est_full_cold:.1f}s")

    # -------------------------------------------------------------
    # BENCHMARK B: WARM REPEATED RUN (Unchanged Repository)
    # -------------------------------------------------------------
    print("\n--- BENCHMARK B: WARM RUN (Unchanged Repository) ---")
    emb_svc.reset_telemetry()

    t0 = time.perf_counter()
    t_vec_write = 0.0
    batch_count = 0

    for i in range(0, sample_size, batch_size):
        batch = test_chunks[i : i + batch_size]
        batch_count += 1
        embs = emb_svc.generate_embeddings(batch)

        t_v0 = time.perf_counter()
        cs.stage_repository_batch("VarshithReddy2006/ARIA", "v_warm", batch, embs, i)
        t_vec_write += time.perf_counter() - t_v0

    t_warm_total = time.perf_counter() - t0
    tel_warm = emb_svc.get_telemetry()

    hit_rate = (tel_warm["cache_hits"] / sample_size) * 100.0
    throughput_warm = sample_size / t_warm_total

    print(f"Warm Run Sample: {sample_size} chunks in {t_warm_total:.3f}s")
    print(f"  - Embedding Time: {tel_warm['embedding_time_ms'] / 1000.0:.3f}s")
    print(f"  - Vector Write Time: {t_vec_write:.3f}s")
    print(f"  - Chunks Embedded (misses): {tel_warm['chunks_embedded']}")
    print(f"  - Cache Hits: {tel_warm['cache_hits']}")
    print(f"  - Cache Hit Rate: {hit_rate:.1f}%")
    print(f"  - Throughput: {throughput_warm:.1f} chunks/sec")
    print(f"  - Speedup vs Cold: {t_cold_total / max(0.001, t_warm_total):.1f}x")

    # -------------------------------------------------------------
    # BENCHMARK C: INCREMENTAL RUN (3 Modified Files = 25 Chunks)
    # -------------------------------------------------------------
    print("\n--- BENCHMARK C: INCREMENTAL RUN (3 Modified Files = 25 Chunks) ---")
    emb_svc.reset_telemetry()

    modified_chunks = []
    for i in range(25):
        modified_chunks.append(
            {
                "path": f"services/service_{i % 3}.py",
                "content": f"def modified_function_{i}():\n    # modified logic\n    return {i * 42}",
                "chunk_id": i + 1,
                "language": "python",
                "category": "production",
            }
        )

    t0 = time.perf_counter()
    cs.delete_files(
        "VarshithReddy2006/ARIA",
        [
            "services/service_0.py",
            "services/service_1.py",
            "services/service_2.py",
        ],
    )
    embs = emb_svc.generate_embeddings(modified_chunks)
    cs.stage_repository_batch(
        "VarshithReddy2006/ARIA", "v_inc", modified_chunks, embs, 0
    )
    t_inc_total = time.perf_counter() - t0
    tel_inc = emb_svc.get_telemetry()

    print(f"Incremental Run Elapsed: {t_inc_total:.3f}s")
    print(f"  - Modified Chunks: {len(modified_chunks)}")
    print(f"  - Embedding Time: {tel_inc['embedding_time_ms'] / 1000.0:.3f}s")
    print(f"  - Total Incremental Duration: {t_inc_total:.3f}s")


if __name__ == "__main__":
    run_benchmark()
