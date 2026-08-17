"""User Scenarios for ARIA Capacity & Load Testing."""

from __future__ import annotations

from typing import List, Dict, Any

# Target repository already indexed in ARIA
BENCHMARK_REPO = "VarshithReddy2006/Repo-Intelligence-Agent"

# Realistic developer questions against the repository
REALISTIC_CHAT_QUERIES: List[str] = [
    "What is the purpose of this repository?",
    "Explain the architecture.",
    "Where is authentication implemented?",
    "Which files depend on the graph service?",
    "How does repository indexing work?",
    "Explain the provider fallback system.",
]

# Browsing & Intelligence endpoints for realistic user exploration
BROWSING_ENDPOINTS: List[Dict[str, Any]] = [
    {"method": "GET", "path": "/api/v1/repos/recent"},
    {"method": "GET", "path": "/api/v1/repos/examples"},
    {
        "method": "GET",
        "path": f"/api/v1/analysis/{BENCHMARK_REPO.split('/')[0]}/{BENCHMARK_REPO.split('/')[1]}",
    },
    {"method": "GET", "path": f"/api/v1/symbols/tree?repo={BENCHMARK_REPO}"},
    {"method": "GET", "path": f"/api/v1/architecture/overview?repo={BENCHMARK_REPO}"},
    {"method": "GET", "path": f"/api/v1/architecture/graph?repo={BENCHMARK_REPO}"},
    {"method": "GET", "path": f"/api/v1/call-graph?repo={BENCHMARK_REPO}"},
    {"method": "GET", "path": f"/api/v1/api-surface?repo={BENCHMARK_REPO}"},
]

# Lightweight operational endpoints
LIGHTWEIGHT_ENDPOINTS: List[Dict[str, Any]] = [
    {"method": "GET", "path": "/health"},
    {"method": "GET", "path": "/metrics"},
    {"method": "GET", "path": "/api/v1/health"},
    {"method": "GET", "path": "/api/v1/chat/health"},
]

# Workload weights for Scenario C (Mixed Production Workload)
WORKLOAD_DISTRIBUTION = {
    "chat_sse": 0.60,
    "repo_analysis": 0.20,
    "repo_browsing": 0.10,
    "lightweight_ops": 0.10,
}
