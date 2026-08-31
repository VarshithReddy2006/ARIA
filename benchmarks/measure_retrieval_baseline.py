"""Baseline retrieval benchmark script for ARIA Phase 2.

Measures:
- T_intent
- T_deterministic
- T_embedding
- T_vector
- T_rerank
- T_context
- T_non_llm
- T_total

Across representative query types and repository sizes.
"""

import os
import sys
import time
import numpy as np
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.embedding_service import EmbeddingService
from memory.chroma_store import ChromaStore
from services.chat.retrieval_pipeline import RetrievalPipeline
from services.chat.intent_detector import RuleBasedIntentDetector
from services.chat.retrieval import intelligent_retrieve, detect_deterministic_retrieval
from services.symbol_service import SymbolService
from services.arch_context_service import ArchContextService


def setup_mock_pipeline():
    """Build a standalone RetrievalPipeline with real local ChromaStore and EmbeddingService."""
    chroma = ChromaStore(persist_directory="data/chroma_test_benchmark")
    emb = EmbeddingService()
    sym = SymbolService()
    arch = ArchContextService()
    pipeline = RetrievalPipeline(
        embedding_service=emb,
        chroma_store=chroma,
        arch_context_service=arch,
        symbol_service=sym,
    )
    return pipeline, chroma, emb, sym, arch


def run_baseline_benchmarks(iterations: int = 15) -> Dict[str, Any]:
    pipeline, chroma, emb, sym, arch = setup_mock_pipeline()
    repo_name = "test-owner/test-benchmark-repo"

    # Index sample chunks representing a medium codebase
    sample_files = [
        (
            "backend/api.py",
            "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/health')\ndef health(): return {'status': 'ok'}",
        ),
        (
            "backend/routers/chat.py",
            "from services.chat.retrieval_pipeline import RetrievalPipeline\ndef chat_handler(): pass",
        ),
        (
            "services/auth_service.py",
            "class AuthService:\n    def authenticate(self, token: str) -> bool: return True",
        ),
        (
            "services/billing_service.py",
            "class BillingService:\n    def charge(self, user_id: str, amount: float): pass",
        ),
        (
            "README.md",
            "# Test Repo\nThis is a sample repository for benchmarking retrieval performance.",
        ),
    ]
    chunks = []
    for fpath, content in sample_files:
        chunks.append(
            {
                "path": fpath,
                "chunk_id": 1,
                "content": content,
                "language": "python",
                "start_line": 1,
                "end_line": len(content.splitlines()),
            }
        )
    texts = [c["content"] for c in chunks]
    embeddings = emb.generate_embeddings_batch(texts)
    chroma.index_repository(repo_name, chunks, embeddings)

    queries = [
        ("exact_file", "What does backend/api.py do?"),
        ("symbol", "Where is authenticate defined?"),
        ("architecture", "How does the backend architecture work?"),
        ("general", "How do I get started with this repository?"),
        ("semantic", "Explain how user authentication and billing work"),
    ]

    results_by_query = {}

    for q_type, q_text in queries:
        t_intent_list = []
        t_det_list = []
        t_embed_list = []
        t_vector_list = []
        t_rerank_list = []
        t_non_llm_list = []

        detector = RuleBasedIntentDetector()

        for _ in range(iterations):
            # 1. Intent detection
            t0 = time.perf_counter()
            detector.detect(q_text)
            t_intent = (time.perf_counter() - t0) * 1000
            t_intent_list.append(t_intent)

            # 2. Deterministic matching
            t0 = time.perf_counter()
            detect_deterministic_retrieval(q_text, repo_name, chroma, sym)
            t_det = (time.perf_counter() - t0) * 1000
            t_det_list.append(t_det)

            # 3. Intelligent retrieve (vector + rerank)
            t0 = time.perf_counter()
            ret_chunks, metrics = intelligent_retrieve(
                question=q_text,
                repo_name=repo_name,
                embedding_service=emb,
                chroma_store=chroma,
                symbol_service=sym,
                use_cache=False,
            )
            t_total_ret = (time.perf_counter() - t0) * 1000
            t_embed_list.append(metrics.get("embed_ms", 0.0))
            t_vector_list.append(metrics.get("search_ms", 0.0))
            t_rerank_list.append(metrics.get("rerank_ms", 0.0))
            t_non_llm_list.append(t_total_ret)

        results_by_query[q_type] = {
            "T_intent_p50": float(np.percentile(t_intent_list, 50)),
            "T_intent_p95": float(np.percentile(t_intent_list, 95)),
            "T_deterministic_p50": float(np.percentile(t_det_list, 50)),
            "T_deterministic_p95": float(np.percentile(t_det_list, 95)),
            "T_embedding_p50": float(np.percentile(t_embed_list, 50)),
            "T_embedding_p95": float(np.percentile(t_embed_list, 95)),
            "T_vector_p50": float(np.percentile(t_vector_list, 50)),
            "T_vector_p95": float(np.percentile(t_vector_list, 95)),
            "T_rerank_p50": float(np.percentile(t_rerank_list, 50)),
            "T_rerank_p95": float(np.percentile(t_rerank_list, 95)),
            "T_non_llm_p50": float(np.percentile(t_non_llm_list, 50)),
            "T_non_llm_p95": float(np.percentile(t_non_llm_list, 95)),
        }

    return results_by_query


if __name__ == "__main__":
    res = run_baseline_benchmarks(10)
    print("\n--- BASELINE RETRIEVAL BENCHMARKS ---")
    for q_type, metrics in res.items():
        print(f"\n[{q_type.upper()}]")
        for k, v in metrics.items():
            print(f"  {k}: {v:.2f}ms")
