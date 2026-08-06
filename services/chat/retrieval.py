"""Intelligent Retrieval — Phases 5 & 6.

Improvements over the original flat top-5 search:
  - Lockfile / generated file exclusion (Tier 4 weight = 0, never retrieved)
  - Repository-aware tier weighting applied to distances
  - Asymmetric BGE query prefix ("Represent this sentence for searching…")
  - Top-15 → rerank → deduplicate → top-5 pipeline
  - Chunk deduplication: identical content hashes are collapsed

Tier weights
------------
  Tier 1 (1.0): backend/, services/, routers/, models/, frontend/src/
  Tier 2 (0.6): README, docs/
  Tier 3 (0.2): requirements.txt, package.json, pyproject.toml, *.toml, *.cfg
  Tier 4 (0.0): lock files, node_modules/, dist/, coverage/, vendor/, *.min.js

Reranker
--------
  Simple cross-encoder approximation using token overlap between the query
  and the chunk content. No external model required — fast, deterministic,
  zero latency overhead from model loading.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier weights and exclusion patterns
# ---------------------------------------------------------------------------

# Files matching these patterns are EXCLUDED from retrieval entirely (weight 0)
_EXCLUDED_PATTERNS: List[re.Pattern] = [
    re.compile(r"package-lock\.json$", re.I),
    re.compile(r"pnpm-lock\.yaml$", re.I),
    re.compile(r"yarn\.lock$", re.I),
    re.compile(r"composer\.lock$", re.I),
    re.compile(r"Gemfile\.lock$", re.I),
    re.compile(r"Cargo\.lock$", re.I),
    re.compile(r"poetry\.lock$", re.I),
    re.compile(r"\.lock$", re.I),
    re.compile(r"node_modules[/\\]", re.I),
    re.compile(r"[/\\]dist[/\\]", re.I),
    re.compile(r"[/\\]build[/\\]", re.I),
    re.compile(r"[/\\]coverage[/\\]", re.I),
    re.compile(r"[/\\]vendor[/\\]", re.I),
    re.compile(r"[/\\]\.cache[/\\]", re.I),
    re.compile(r"[/\\]__pycache__[/\\]", re.I),
    re.compile(r"\.min\.(js|css)$", re.I),
    re.compile(
        r"\.(png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|otf|pdf|zip|gz|tar)$", re.I
    ),
    re.compile(r"\.(pyc|pyo|class|o|a|so|dll|exe|bin)$", re.I),
    re.compile(r"\.map$", re.I),
    re.compile(r"\.snap$", re.I),
    re.compile(r"[/\\]out[/\\]", re.I),
    re.compile(r"[/\\]snapshots[/\\]", re.I),
    re.compile(r"\.pytest_cache[/\\]", re.I),
    re.compile(r"[/\\]\.pytest_cache[/\\]", re.I),
    re.compile(r"\.git[/\\]", re.I),
    re.compile(r"\.venv[/\\]", re.I),
    re.compile(r"\.kiro[/\\]", re.I),
    re.compile(r"\.vscode[/\\]", re.I),
]

_FILE_PATHS_CACHE: Dict[str, tuple[float, List[str]]] = {}
_CACHE_TTL = 30.0  # seconds


def get_unique_file_paths(repo_name: str, chroma_store) -> List[str]:
    import sys

    is_testing = "pytest" in sys.modules or "unittest" in sys.modules

    import time

    now = time.time()

    # Prune stale entries to prevent unbounded memory growth
    stale_keys = [k for k, (t, _) in _FILE_PATHS_CACHE.items() if now - t >= _CACHE_TTL]
    for k in stale_keys:
        _FILE_PATHS_CACHE.pop(k, None)

    if not is_testing and repo_name in _FILE_PATHS_CACHE:
        cache_time, paths = _FILE_PATHS_CACHE[repo_name]
        if now - cache_time < _CACHE_TTL:
            return paths

    try:
        if callable(getattr(type(chroma_store), "get_repository_file_paths", None)):
            paths = chroma_store.get_repository_file_paths(repo_name)
        else:
            res = chroma_store.collection.get(
                where={"repo_name": repo_name}, include=["metadatas"]
            )
            metas = res.get("metadatas", []) if res else []
            paths = sorted(
                {meta["file_path"] for meta in metas if meta and meta.get("file_path")}
            )
        _FILE_PATHS_CACHE[repo_name] = (now, paths)
        return paths
    except Exception as exc:
        logger.warning("Failed to fetch file paths from Chroma: %s", exc)
        return []


def get_base_filename(filename: str) -> str:
    fn = filename.lower()
    fn_no_ext = fn.rsplit(".", 1)[0] if "." in fn else fn
    for suffix in ("_test", "-test", ".test", ".spec"):
        if fn_no_ext.endswith(suffix):
            fn_no_ext = fn_no_ext[: -len(suffix)]
        if fn_no_ext.startswith("test_"):
            fn_no_ext = fn_no_ext[5:]
        elif fn_no_ext.startswith("test-"):
            fn_no_ext = fn_no_ext[5:]
    return fn_no_ext


def extract_file_candidates(question: str) -> List[str]:
    pattern = re.compile(
        r"\b(?:[a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+|[Dd]ockerfile|[Mm]akefile|[Rr]eadme|[Ll]icense)\b"
    )
    matches = pattern.findall(question)
    candidates = []
    for m in matches:
        m_clean = m.strip(".,;:!?\"'`()[]{}")
        if m_clean:
            candidates.append(m_clean.replace("\\", "/"))
    return candidates


def is_non_preferred_file(path: str) -> bool:
    """Return True if the path is test, mock, compiled, or other non-production file."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    for part in parts:
        if part in (
            "tests",
            "test",
            "__tests__",
            "spec",
            "mock",
            "mocks",
            "fixtures",
            "out",
            "dist",
            "build",
            "coverage",
            "node_modules",
            ".vscode",
            ".kiro",
            ".pytest_cache",
        ):
            return True
        if part.startswith("test_") or part.startswith("mock_"):
            return True
    filename = parts[-1]
    if (
        filename.startswith("test_")
        or filename.startswith("mock_")
        or ".test." in filename
        or ".spec." in filename
        or ".mock." in filename
        or filename.endswith("_test.py")
        or filename.endswith("_mock.py")
    ):
        return True
    return False


def get_directory_rank(path: str) -> int:
    """Return ranking index for the path directories (lower is closer/preferred)."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    if "backend" in parts:
        return 0
    if "services" in parts:
        return 1
    if "frontend" in parts:
        return 2
    if "src" in parts:
        return 3
    if "docs" in parts or "doc" in parts:
        return 4
    if "tests" in parts or "test" in parts:
        return 5
    return 6


def detect_deterministic_retrieval(
    question: str,
    repo_name: str,
    chroma_store,
    symbol_service,
) -> Optional[Dict[str, Any]]:
    """Detect if the query explicitly references a file path, filename, or symbol.

    Returns details if matched, else None.
    """
    candidates = extract_file_candidates(question)
    file_paths = get_unique_file_paths(repo_name, chroma_store)
    if not file_paths:
        return None

    # 1. Exact path match (bypasses all else, is case-insensitive normalized)
    for path in file_paths:
        path_norm = path.replace("\\", "/").lower()
        for cand in candidates:
            cand_norm = cand.replace("\\", "/").lower()
            if path_norm == cand_norm or (
                "/" in cand_norm
                and (
                    path_norm.endswith("/" + cand_norm)
                    or path_norm.startswith(cand_norm)
                )
            ):
                return {
                    "matched_file": path,
                    "confidence": 100,
                    "match_type": "path",
                    "clarification_needed": False,
                    "choices": [],
                }

    # 2. Exact filename match
    for cand in candidates:
        cand_filename = os.path.basename(cand).lower()
        matching_files = []
        for path in file_paths:
            if os.path.basename(path).lower() == cand_filename:
                matching_files.append(path)

        if matching_files:
            # Filter to production files
            prod_files = [f for f in matching_files if not is_non_preferred_file(f)]

            if len(prod_files) == 1:
                return {
                    "matched_file": prod_files[0],
                    "confidence": 98,
                    "match_type": "filename",
                    "clarification_needed": False,
                    "choices": [],
                }
            elif len(prod_files) > 1:
                # Group by rank
                ranked_prod = defaultdict(list)
                for f in prod_files:
                    ranked_prod[get_directory_rank(f)].append(f)

                min_rank = min(ranked_prod.keys())
                closest_prod_files = ranked_prod[min_rank]

                if len(closest_prod_files) == 1:
                    return {
                        "matched_file": closest_prod_files[0],
                        "confidence": 98,
                        "match_type": "filename",
                        "clarification_needed": False,
                        "choices": [],
                    }
                else:
                    return {
                        "matched_file": None,
                        "confidence": 98,
                        "match_type": "filename",
                        "clarification_needed": True,
                        "choices": closest_prod_files,
                        "candidate": cand_filename,
                    }
            else:
                # Fallback to non-production files
                ranked_non_prod = defaultdict(list)
                for f in matching_files:
                    ranked_non_prod[get_directory_rank(f)].append(f)

                min_rank = min(ranked_non_prod.keys())
                closest_non_prod = ranked_non_prod[min_rank]

                return {
                    "matched_file": closest_non_prod[0],
                    "confidence": 98,
                    "match_type": "filename",
                    "clarification_needed": False,
                    "choices": [],
                }

    # 3. Exact symbol match
    if symbol_service:
        # Extract alphanumeric words
        words = re.findall(r"\b[a-zA-Z_]\w*\b", question)
        for word in words:
            if word.lower() in {
                "explain",
                "describe",
                "show",
                "what",
                "how",
                "why",
                "where",
                "who",
                "when",
                "the",
                "a",
                "an",
                "is",
                "of",
                "to",
                "and",
                "in",
                "file",
                "class",
                "function",
                "method",
            }:
                continue
            try:
                sym = symbol_service.get_definition(repo_name, word)
                if sym:
                    sym_file = sym.file_path
                    if not is_non_preferred_file(sym_file):
                        return {
                            "matched_file": sym_file,
                            "confidence": 96,
                            "match_type": "symbol",
                            "clarification_needed": False,
                            "choices": [],
                        }
            except Exception as e:
                logger.warning("Error checking symbol '%s': %s", word, e)

    return None


def find_matched_symbols(
    question: str, repo_name: str, symbol_service
) -> Dict[str, List[Any]]:
    """Return a dictionary mapping normalized file paths to Symbol objects matched in the question."""
    matched = {}
    try:
        index = symbol_service.load(repo_name)
        if index and index.symbols:
            # Extract words from question
            words = set(re.findall(r"[a-zA-Z_]\w*", question))
            words_lower = {w.lower() for w in words}
            for s in index.symbols:
                if s.name in words or s.name.lower() in words_lower:
                    norm_path = s.file_path.replace("\\", "/").lower()
                    if norm_path not in matched:
                        matched[norm_path] = []
                    matched[norm_path].append(s)
    except Exception as exc:
        logger.warning("Failed to find matched symbols: %s", exc)
    return matched


def find_chunk_line_numbers(
    file_path: str, chunk_content: str
) -> Optional[tuple[int, int]]:
    """Find the 1-indexed start and end line numbers of chunk_content in file_path on disk."""
    try:
        test_path = file_path
        if not os.path.exists(test_path):
            return None
        with open(test_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        chunk_lines = [
            line.strip() for line in chunk_content.splitlines() if line.strip()
        ]
        if not chunk_lines:
            return None

        for idx in range(len(lines)):
            match = True
            for offset, cl in enumerate(chunk_lines):
                if idx + offset >= len(lines):
                    match = False
                    break
                if cl not in lines[idx + offset]:
                    match = False
                    break
            if match:
                start_line = idx + 1
                end_line = idx + len(chunk_lines)
                return start_line, end_line
    except Exception:
        pass
    return None


def is_architecture_file(path: str) -> bool:
    """Return True if the file path represents an architecture summary, index, or entry point."""
    p = path.replace("\\", "/").lower()
    if "architecture" in p or "overview" in p:
        return True
    if p in (
        "backend/api.py",
        "backend/main.py",
        "backend/dependencies.py",
        "architecture.md",
        "README.md",
    ):
        return True
    return False


# Path prefix → tier weight
_TIER_1_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(backend|services|routers|models|agents|core)[/\\]", re.I),
    re.compile(r"^frontend[/\\]src[/\\]", re.I),
    re.compile(r"^src[/\\]", re.I),
    re.compile(r"\.(py|ts|tsx|js|jsx|java|go|rs|rb|cs|cpp|c)$", re.I),
]

_TIER_2_PATTERNS: List[re.Pattern] = [
    re.compile(r"(readme|README)\.", re.I),
    re.compile(r"^docs?[/\\]", re.I),
    re.compile(r"\.(md|rst|txt)$", re.I),
]

_TIER_3_PATTERNS: List[re.Pattern] = [
    re.compile(r"requirements.*\.txt$", re.I),
    re.compile(r"pyproject\.toml$", re.I),
    re.compile(r"setup\.(py|cfg)$", re.I),
    re.compile(r"package\.json$", re.I),
    re.compile(r"tsconfig.*\.json$", re.I),
    re.compile(r"\.(toml|cfg|ini|env\.example)$", re.I),
    re.compile(r"dockerfile$", re.I),
    re.compile(r"docker-compose.*\.yml$", re.I),
]


def _get_tier_weight(file_path: str) -> float:
    """Return the tier weight for a given file path (0.0 = exclude)."""
    p = file_path.replace("\\", "/")

    for pat in _EXCLUDED_PATTERNS:
        if pat.search(p):
            return 0.0

    # Tier 3 checked before Tier 2 because some Tier 3 files (requirements.txt)
    # would otherwise match Tier 2's generic .txt pattern.
    for pat in _TIER_3_PATTERNS:
        if pat.search(p):
            return 0.2

    for pat in _TIER_1_PATTERNS:
        if pat.search(p):
            return 1.0

    for pat in _TIER_2_PATTERNS:
        if pat.search(p):
            return 0.6

    # Default to Tier 1 weight for unknown types
    return 1.0


def _content_hash(content: str) -> str:
    """MD5 of stripped content for deduplication."""
    return hashlib.md5(content.strip().encode("utf-8")).hexdigest()


def _token_overlap_score(query: str, content: str) -> float:
    """Approximate reranking score using normalised token overlap.

    Returns a float in [0, 1]. Higher = better match.
    Avoids loading any ML model — pure string ops.
    """

    def tokenise(text: str) -> set:
        # Lower-case, split on non-alphanumeric, remove stop words
        tokens = re.findall(r"[a-zA-Z_]\w*", text.lower())
        stop = {
            "the",
            "a",
            "an",
            "is",
            "in",
            "it",
            "of",
            "to",
            "do",
            "does",
            "what",
            "how",
            "why",
            "where",
            "this",
            "that",
            "are",
            "for",
            "be",
            "was",
            "or",
            "and",
            "on",
            "at",
        }
        return {t for t in tokens if t not in stop and len(t) > 1}

    q_tokens = tokenise(query)
    c_tokens = tokenise(content)

    if not q_tokens:
        return 0.0
    if not c_tokens:
        return 0.0

    overlap = len(q_tokens & c_tokens)
    # Normalise by query length — precision-oriented
    return overlap / len(q_tokens)


# ---------------------------------------------------------------------------
# BGE asymmetric query prefix
# ---------------------------------------------------------------------------

_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def build_query_text(question: str) -> str:
    """Prepend the BGE asymmetric query prefix for retrieval queries.

    Documents indexed without any prefix (as BGE asymmetric embedding design
    requires). Queries use this prefix to improve retrieval precision.
    """
    return f"{_BGE_QUERY_PREFIX}{question}"


# ---------------------------------------------------------------------------
# Main retrieval pipeline
# ---------------------------------------------------------------------------


def is_test_file(path: str) -> bool:
    """Return True if the path represents a test file/directory."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    for part in parts:
        if part in ("tests", "__tests__", "spec", "mock", "fixtures"):
            return True
        if part.startswith("test_"):
            return True
    filename = parts[-1]
    if (
        filename.startswith("test_")
        or ".test." in filename
        or filename.endswith("_test.py")
    ):
        return True
    if "vscode-extension/src/test/" in p or "vscode-extension/out/test/" in p:
        return True
    return False


def is_generated_or_compiled(path: str) -> bool:
    """Return True if the path represents compiled, generated, or output files."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    for part in parts:
        if part in ("dist", "out", "coverage", "build", "target", "maps", "snapshots"):
            return True
    filename = parts[-1]
    if (
        filename.endswith(".map")
        or filename.endswith(".snap")
        or filename.endswith(".min.js")
    ):
        return True
    return False


def is_subpath_in_query(subpath: str, query: str) -> bool:
    """Return True if subpath (exact path or filename) is explicitly referenced in query."""
    subpath = subpath.replace("\\", "/").lower().strip()
    query = query.replace("\\", "/").lower().strip()
    if not subpath or not query:
        return False
    escaped = re.escape(subpath)
    # Boundaries can be whitespace, quotes, brackets, parentheses, punctuation, or slashes
    pattern = r"(?:^|[\s\"'`()<>[\]/\\])" + escaped + r"(?:$|[\s\"'`()<>[\].,;:!?/\\])"
    return bool(re.search(pattern, query))


def is_file_excluded(path: str, candidates: List[str], asks_about_tests: bool) -> bool:
    """Return True if the file should be excluded based on retrieval rules.

    Excludes tests, lockfiles, generated files, and build artifacts,
    unless they are explicitly requested by the user.
    """
    p_clean = path.replace("\\", "/").lower()
    filename = os.path.basename(p_clean)
    filename_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename

    # Check if explicitly requested
    is_explicitly_requested = False
    for cand in candidates:
        cand_lower = cand.lower().replace("\\", "/")
        cand_filename = os.path.basename(cand_lower)
        cand_filename_no_ext = (
            cand_filename.rsplit(".", 1)[0] if "." in cand_filename else cand_filename
        )

        if (
            p_clean == cand_lower
            or p_clean.endswith("/" + cand_lower)
            or filename == cand_filename
            or filename_no_ext == cand_filename_no_ext
        ):
            is_explicitly_requested = True
            break

    if is_explicitly_requested:
        return False

    # Exclude tests if not explicitly asked
    if is_test_file(path) and not asks_about_tests:
        return True

    # Exclude generated/compiled files
    if is_generated_or_compiled(path):
        return True

    # Exclude lockfiles/other patterns in Tier 4 weight list
    for pat in _EXCLUDED_PATTERNS:
        if pat.search(p_clean):
            return True

    return False


def determine_ranking_category(
    path: str,
    question: str,
    candidates: List[str],
    matched_symbols_by_file: Dict[str, List[Any]],
    asks_about_tests: bool,
) -> tuple[float, str]:
    """Return (base_score, why_this_file) for the given file path based on rankings."""
    p_clean = path.replace("\\", "/").lower()
    filename = os.path.basename(p_clean)
    filename_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename

    is_exact_path = False
    is_exact_filename = False

    for cand in candidates:
        cand_lower = cand.lower().replace("\\", "/")
        cand_filename = os.path.basename(cand_lower)
        cand_filename_no_ext = (
            cand_filename.rsplit(".", 1)[0] if "." in cand_filename else cand_filename
        )

        if p_clean == cand_lower or p_clean.endswith("/" + cand_lower):
            is_exact_path = True
            break
        if filename == cand_filename or filename_no_ext == cand_filename_no_ext:
            is_exact_filename = True

    is_exact_symbol = p_clean in matched_symbols_by_file
    is_arch = is_architecture_file(path)
    is_test = is_test_file(path)
    is_gen = is_generated_or_compiled(path)
    weight = _get_tier_weight(path)

    # 1. Exact path match
    if is_exact_path:
        return 1000000.0, "Matched exact path"

    # 2. Exact filename match
    if is_exact_filename:
        return 900000.0, "Matched exact filename"

    # 3. Exact symbol match
    if is_exact_symbol:
        return 800000.0, "Contains requested symbol"

    # 9. Generated files (last)
    if is_gen:
        return 1000.0, "Generated file"

    # 8. Tests (only if requested)
    if is_test:
        if asks_about_tests:
            return 300000.0, "Test file (requested)"
        else:
            return 10000.0, "Test file"

    # 4. Production source
    if weight >= 1.0:
        return 700000.0, "Production source file"

    # 5. Architecture file
    if is_arch:
        return 600000.0, "Referenced by architecture graph"

    # 6. Documentation
    if weight >= 0.5:
        return 500000.0, "Documentation file"

    # 7. Configuration
    if weight >= 0.1:
        return 400000.0, "Configuration file"

    return 700000.0, "Production source file"


def calculate_chunk_confidence(
    file_path: str,
    raw_distance: float,
    is_exact_path: bool,
    is_exact_filename: bool,
    is_exact_symbol: bool,
    is_arch: bool,
) -> int:
    """Compute the dynamic confidence score percentage (70 to 100)."""
    if is_exact_path:
        return 100
    if is_exact_filename:
        return 98
    if is_exact_symbol:
        return 96
    if is_arch:
        return 90
    if raw_distance < 0.5:
        return 85
    return 70


def populate_chunk_symbols_and_lines(
    chunk: Dict[str, Any], repo_name: str, question: str, symbol_service: Any
) -> None:
    """Populate line numbers and defined/matched symbols into chunk metadata."""
    meta = chunk.setdefault("metadata", {})
    file_path = meta.get("file_path", "")
    if not file_path:
        return

    # Find line numbers dynamically if not already populated
    start_line = meta.get("start_line")
    end_line = meta.get("end_line")
    if not start_line or not end_line:
        lines = find_chunk_line_numbers(file_path, chunk.get("content", ""))
        if lines:
            start_line, end_line = lines
            meta["start_line"] = start_line
            meta["end_line"] = end_line

    # Load and map symbols from symbol service
    symbols_in_chunk = []
    try:
        if symbol_service:
            index = symbol_service.load(repo_name)
            if index and index.symbols:
                norm_file_path = file_path.replace("\\", "/").lower()
                file_symbols = [
                    s
                    for s in index.symbols
                    if s.file_path.replace("\\", "/").lower() == norm_file_path
                ]

                words = set(re.findall(r"[a-zA-Z_]\w*", question))
                for s in file_symbols:
                    in_range = False
                    if start_line and end_line:
                        if start_line <= s.line_number <= end_line:
                            in_range = True

                    in_question = s.name in words

                    if in_range or in_question:
                        type_str = f" ({s.type})" if s.type else ""
                        symbols_in_chunk.append(f"{s.name}{type_str}")
    except Exception as e:
        logger.warning("Error populating chunk symbols: %s", e)

    if symbols_in_chunk:
        seen = set()
        deduped = []
        for s in symbols_in_chunk:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        meta["matched_symbols"] = ", ".join(deduped)


def intelligent_retrieve(
    question: str,
    repo_name: str,
    embedding_service,
    chroma_store,
    top_k_initial: int = 15,
    top_k_final: int = 5,
    symbol_service=None,
    conversation_context=None,
    conversation_settings=None,
    disable_previous_boosts: bool = False,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Full retrieval pipeline with File-Aware layer, dynamic confidence, contextual ranking, and tier tracking."""
    t_total = time.perf_counter()
    metrics: Dict[str, Any] = {
        "initial_retrieved": 0,
        "after_exclusion": 0,
        "after_dedup": 0,
        "final_returned": 0,
        "embed_ms": 0.0,
        "search_ms": 0.0,
        "rerank_ms": 0.0,
        "total_ms": 0.0,
        "confidence": 70,
    }

    # 1. Fetch unique file paths for this repo
    file_paths = get_unique_file_paths(repo_name, chroma_store)

    # Check for deterministic retrieval match first
    det_match = None
    if file_paths:
        det_match = detect_deterministic_retrieval(
            question=question,
            repo_name=repo_name,
            chroma_store=chroma_store,
            symbol_service=symbol_service,
        )

    if det_match:
        matched_file_path = det_match["matched_file"]
        confidence = det_match["confidence"]
        match_type = det_match["match_type"]
        clarification_needed = det_match["clarification_needed"]

        if clarification_needed:
            elapsed_ms = (time.perf_counter() - t_total) * 1000
            metrics = {
                "initial_retrieved": 0,
                "after_exclusion": 0,
                "after_dedup": 0,
                "final_returned": 0,
                "embed_ms": 0.0,
                "search_ms": 0.0,
                "rerank_ms": 0.0,
                "total_ms": elapsed_ms,
                "confidence": confidence,
                "matched_file": None,
                "deterministic": True,
                "semantic_search": False,
                "clarification_needed": True,
                "choices": det_match["choices"],
                "candidate": det_match["candidate"],
            }
            return [], metrics

        # Retrieve all chunks belonging to that file
        try:
            if callable(getattr(type(chroma_store), "get_file_chunks", None)):
                res_chunks = chroma_store.get_file_chunks(repo_name, matched_file_path)
            else:
                res_chunks = chroma_store.collection.get(
                    where={
                        "$and": [{"repo_name": repo_name}, {"file_path": matched_file_path}]
                    },
                    include=["documents", "metadatas"],
                )
            chunks = []
            if res_chunks and res_chunks.get("documents"):
                docs = res_chunks["documents"]
                metas = res_chunks["metadatas"] or [{}] * len(docs)
                ids = res_chunks["ids"]
                for cid, doc, meta in zip(ids, docs, metas):
                    chunks.append(
                        {
                            "id": cid,
                            "content": doc,
                            "metadata": meta or {},
                        }
                    )
        except Exception as exc:
            logger.warning(
                "Failed to retrieve chunks for file %s: %s", matched_file_path, exc
            )
            chunks = []

        # Sort by chunk_id
        chunks.sort(key=lambda c: int(c.get("metadata", {}).get("chunk_id", 0)))

        why_labels = {
            "path": "Matched exact path",
            "filename": "Matched exact filename",
            "symbol": "Contains requested symbol",
        }
        why_label = why_labels.get(match_type, "Matched deterministic file")

        for c in chunks:
            meta = c.setdefault("metadata", {})
            meta["why_this_file"] = why_label
            meta["confidence"] = confidence
            populate_chunk_symbols_and_lines(c, repo_name, question, symbol_service)

        elapsed_ms = (time.perf_counter() - t_total) * 1000
        logger.info(
            "DETERMINISTIC_FILE_RETRIEVAL query=%s matched_file=%s chunks=%d elapsed_ms=%.2f semantic_search=False",
            question,
            matched_file_path,
            len(chunks),
            elapsed_ms,
        )

        metrics = {
            "initial_retrieved": len(chunks),
            "after_exclusion": len(chunks),
            "after_dedup": len(chunks),
            "final_returned": len(chunks),
            "embed_ms": 0.0,
            "search_ms": 0.0,
            "rerank_ms": 0.0,
            "total_ms": elapsed_ms,
            "confidence": confidence,
            "matched_file": matched_file_path,
            "deterministic": True,
            "semantic_search": False,
        }
        return chunks, metrics

    # 2. Extract explicit file references and find matched symbols
    candidates = extract_file_candidates(question)
    asks_about_tests = any(
        w in question.lower() for w in ["test", "testing", "spec", "mock", "fixture"]
    )

    matched_symbols_by_file = {}
    if symbol_service:
        matched_symbols_by_file = find_matched_symbols(
            question, repo_name, symbol_service
        )

    # 3. Direct lookup of files that match candidates or symbols (unless excluded)
    matched_files = set()
    for path in file_paths:
        if is_file_excluded(path, candidates, asks_about_tests):
            continue

        p_clean = path.replace("\\", "/").lower()
        filename = os.path.basename(p_clean)
        filename_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename

        is_matched = False
        for cand in candidates:
            cand_lower = cand.lower().replace("\\", "/")
            cand_filename = os.path.basename(cand_lower)
            cand_filename_no_ext = (
                cand_filename.rsplit(".", 1)[0]
                if "." in cand_filename
                else cand_filename
            )
            if (
                p_clean == cand_lower
                or p_clean.endswith("/" + cand_lower)
                or filename == cand_filename
                or filename_no_ext == cand_filename_no_ext
            ):
                is_matched = True
                break

        if is_matched or p_clean in matched_symbols_by_file:
            matched_files.add(path)

    direct_chunks = []
    for f in matched_files:
        try:
            if callable(getattr(type(chroma_store), "get_file_chunks", None)):
                res_chunks = chroma_store.get_file_chunks(repo_name, f)
            else:
                res_chunks = chroma_store.collection.get(
                    where={"$and": [{"repo_name": repo_name}, {"file_path": f}]},
                    include=["documents", "metadatas"],
                )
            if res_chunks and res_chunks.get("documents"):
                docs = res_chunks["documents"]
                metas = res_chunks["metadatas"]
                ids = res_chunks["ids"]
                for doc, meta, cid in zip(docs, metas, ids):
                    direct_chunks.append(
                        {
                            "id": cid,
                            "content": doc,
                            "metadata": meta or {},
                            "distance": 0.05,  # High similarity for direct matches
                        }
                    )
        except Exception as exc:
            logger.warning("Failed direct lookup for %s: %s", f, exc)

    # 4. Semantic Search
    t0 = time.perf_counter()
    query_text = build_query_text(question)
    query_embedding = embedding_service.generate_embedding(query_text)
    metrics["embed_ms"] = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    raw_semantic_chunks = chroma_store.search_repository(
        repo_name=repo_name,
        query_embedding=query_embedding,
        limit=top_k_initial,
    )
    metrics["search_ms"] = (time.perf_counter() - t0) * 1000
    metrics["initial_retrieved"] = len(raw_semantic_chunks)

    # 5. Pool direct and semantic chunks, deduplicating by ID
    pool = []
    seen_ids = set()
    for chunk in direct_chunks:
        cid = chunk.get("id")
        if cid not in seen_ids:
            seen_ids.add(cid)
            pool.append(chunk)

    for chunk in raw_semantic_chunks:
        cid = chunk.get("id")
        if cid not in seen_ids:
            seen_ids.add(cid)
            pool.append(chunk)

    # 6. Score and rank all chunks in the pool
    t0 = time.perf_counter()
    scored_chunks = []
    for chunk in pool:
        meta = chunk.setdefault("metadata", {})
        path = meta.get("file_path", "")
        if not path:
            continue

        if is_file_excluded(path, candidates, asks_about_tests):
            continue

        base_score, why_this_file = determine_ranking_category(
            path=path,
            question=question,
            candidates=candidates,
            matched_symbols_by_file=matched_symbols_by_file,
            asks_about_tests=asks_about_tests,
        )

        distance = chunk.get("distance", 0.2)
        similarity = 1.0 / (1.0 + distance)
        overlap = _token_overlap_score(question, chunk.get("content", ""))

        total_score = (
            base_score
            + (10000.0 * similarity)
            + (5000.0 * overlap)
            + (1000.0 / (len(path) + 1))
        )

        # Contextual ranking boosts (disabled when explicit entity is present to prevent previous topic stickiness)
        if not disable_previous_boosts and conversation_context and conversation_context.topic_confidence >= getattr(conversation_settings, "topic_threshold", 0.35):
            p_clean = path.replace("\\", "/").lower()
            cur_f = conversation_context.current_file.replace("\\", "/").lower() if conversation_context.current_file else None
            c_boost = getattr(conversation_settings, "current_file_boost", 50.0)
            s_boost = getattr(conversation_settings, "current_symbol_boost", 35.0)
            m_boost = getattr(conversation_settings, "current_module_boost", 20.0)
            r_boost = getattr(conversation_settings, "recent_file_boost", 10.0)

            if cur_f and (p_clean == cur_f or p_clean.endswith("/" + cur_f) or cur_f.endswith("/" + os.path.basename(p_clean))):
                total_score += c_boost * 1000.0
                why_this_file = "Contextual Current File"

            if conversation_context.current_symbol and conversation_context.current_symbol.lower() in chunk.get("content", "").lower():
                total_score += s_boost * 1000.0

            if conversation_context.current_module and conversation_context.current_module.lower() in p_clean:
                total_score += m_boost * 1000.0

            for rf in conversation_context.recently_discussed_files:
                rf_norm = rf.replace("\\", "/").lower()
                if p_clean == rf_norm or p_clean.endswith("/" + rf_norm):
                    total_score += r_boost * 1000.0
                    break

        # Penalize test files slightly to break ties
        if is_test_file(path):
            total_score -= 100.0

        is_exact_path = why_this_file == "Matched exact path"
        is_exact_filename = why_this_file == "Matched exact filename"
        is_exact_symbol = why_this_file == "Contains requested symbol"
        is_arch = why_this_file == "Referenced by architecture graph"

        confidence = calculate_chunk_confidence(
            file_path=path,
            raw_distance=distance,
            is_exact_path=is_exact_path,
            is_exact_filename=is_exact_filename,
            is_exact_symbol=is_exact_symbol,
            is_arch=is_arch,
        )

        chunk["_rerank_score"] = total_score
        chunk["_similarity"] = round(similarity, 4)
        chunk["_token_overlap"] = round(overlap, 4)
        meta["why_this_file"] = why_this_file
        meta["confidence"] = confidence

        scored_chunks.append(chunk)

    metrics["after_exclusion"] = len(scored_chunks)

    # 7. Sort by score descending and deduplicate by content hash
    scored_chunks.sort(key=lambda c: c["_rerank_score"], reverse=True)

    # Refine "why_this_file" for semantic matches
    if scored_chunks:
        top_chunk = scored_chunks[0]
        top_why = top_chunk.setdefault("metadata", {}).get("why_this_file", "")
        if top_why in (
            "Production source file",
            "Documentation file",
            "Configuration file",
            "Test file",
        ):
            top_chunk["metadata"]["why_this_file"] = "Highest semantic similarity"

        for chunk in scored_chunks[1:]:
            why = chunk.setdefault("metadata", {}).get("why_this_file", "")
            if why in (
                "Production source file",
                "Documentation file",
                "Configuration file",
                "Test file",
            ):
                chunk["metadata"]["why_this_file"] = "Semantic similarity match"

    final_chunks = []
    seen_hashes = set()
    for chunk in scored_chunks:
        h = _content_hash(chunk["content"])
        if h not in seen_hashes:
            seen_hashes.add(h)
            populate_chunk_symbols_and_lines(chunk, repo_name, question, symbol_service)
            final_chunks.append(chunk)
            if len(final_chunks) >= top_k_final:
                break

    metrics["after_dedup"] = len(final_chunks)
    metrics["rerank_ms"] = (time.perf_counter() - t0) * 1000
    metrics["final_returned"] = len(final_chunks)

    # Determine maximum confidence
    max_confidence = 70
    if final_chunks:
        max_confidence = max(
            c.get("metadata", {}).get("confidence", 70) for c in final_chunks
        )
    metrics["confidence"] = max_confidence

    metrics["total_ms"] = (time.perf_counter() - t_total) * 1000

    # Logging matching details
    log_lines = [
        f"Detected file query: {candidates if candidates else 'none'}",
        "Ranking:",
    ]
    for c in final_chunks[:5]:
        meta = c.get("metadata", {})
        log_lines.append(
            f"  {meta.get('file_path')} score={c.get('_rerank_score', 0.0):.1f} why='{meta.get('why_this_file')}'"
        )
    logger.info("\n" + "\n".join(log_lines))

    return final_chunks, metrics


def should_skip_indexing(file_path: str) -> bool:
    """Return True if a file should never be embedded/indexed.

    Called during repository indexing to prevent lockfiles and generated
    code from polluting the vector store.
    """
    return _get_tier_weight(file_path) == 0.0
