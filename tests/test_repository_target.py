"""Tests for AnalysisTarget identity model and path normalization (Phase 1)."""

from core.repository_target import (
    AnalysisTarget,
    get_canonical_repo_id,
    get_repository_lock_path,
    normalize_ref,
    normalize_ref_for_path,
    normalize_repository_name,
)


def test_normalize_repository_name():
    """Verify owner and repo extraction and lowercasing from various formats."""
    assert normalize_repository_name("VarshithReddy2006/ARIA") == (
        "varshithreddy2006",
        "aria",
    )
    assert normalize_repository_name("https://github.com/Google/Guava.git") == (
        "google",
        "guava",
    )
    assert normalize_repository_name("git@github.com:Vercel/Next.js.git") == (
        "vercel",
        "next.js",
    )
    assert normalize_repository_name("standalone-repo") == ("owner", "standalone-repo")
    assert get_canonical_repo_id("VarshithReddy2006/ARIA") == "varshithreddy2006/aria"


def test_normalize_ref():
    """Verify default branch fallback and whitespace trimming."""
    assert normalize_ref(None) == "main"
    assert normalize_ref("") == "main"
    assert normalize_ref("   ") == "main"
    assert normalize_ref("dev") == "dev"
    assert normalize_ref("feature/auth-v2") == "feature/auth-v2"


def test_normalize_ref_for_path_standard_and_slash():
    """Verify standard branches and slash-containing refs."""
    assert normalize_ref_for_path("main") == "main"
    assert normalize_ref_for_path("dev") == "dev"
    assert normalize_ref_for_path("release-1.0") == "release-1.0"
    assert normalize_ref_for_path("feature/auth-v2") == "feature_auth-v2"
    assert normalize_ref_for_path("refs/pull/101/head") == "refs_pull_101_head"
    assert normalize_ref_for_path("refs/tags/v2.1.0") == "refs_tags_v2.1.0"


def test_normalize_ref_for_path_traversal_and_special_chars():
    """Verify path traversal prevention and illegal character stripping."""
    res = normalize_ref_for_path("../../../etc/passwd")
    assert ".." not in res
    assert "/" not in res
    assert "\\" not in res

    res_special = normalize_ref_for_path("feat:test*name?<>|")
    assert ":" not in res_special
    assert "*" not in res_special
    assert "?" not in res_special
    assert "<" not in res_special
    assert ">" not in res_special
    assert "|" not in res_special


def test_normalize_ref_for_path_collision_resistance():
    """Verify that distinct refs that would sanitize similarly receive deterministic hashes."""
    ref_a = "feat/auth:v1"
    ref_b = "feat/auth_v1"
    norm_a = normalize_ref_for_path(ref_a)
    norm_b = normalize_ref_for_path(ref_b)
    assert norm_a != norm_b, f"Expected distinct path names for {ref_a} and {ref_b}"


def test_analysis_target_model():
    """Verify AnalysisTarget properties and deterministic keys."""
    target_main = AnalysisTarget.from_url_and_branch("VarshithReddy2006/ARIA", "main")
    target_dev = AnalysisTarget.from_url_and_branch(
        "https://github.com/VarshithReddy2006/ARIA.git", "dev"
    )

    assert target_main.repo_id == "varshithreddy2006/aria"
    assert target_main.safe_repo_dir == "varshithreddy2006_aria"
    assert target_main.safe_ref_dir == "main"
    assert target_main.target_key == "varshithreddy2006/aria::main"

    assert target_dev.safe_ref_dir == "dev"
    assert target_dev.target_key == "varshithreddy2006/aria::dev"
    assert target_main.target_key != target_dev.target_key

    # Lock paths are distinct
    lock_main = get_repository_lock_path("VarshithReddy2006/ARIA", "main")
    lock_dev = get_repository_lock_path("VarshithReddy2006/ARIA", "dev")
    assert lock_main != lock_dev
    assert "varshithreddy2006_aria_main.lock" in lock_main
    assert "varshithreddy2006_aria_dev.lock" in lock_dev
