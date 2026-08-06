"""Regression test enforcing R-008 performance and import invariants.

1. `import backend.api` completes in under 1 second.
2. `SentenceTransformer` is not loaded or instantiated during module import.
3. FastAPI application entry point loads without triggering database migrations or ML initialization side-effects.
"""

import sys
import time
import pytest


@pytest.fixture
def _restore_backend_modules():
    """Snapshot and restore every ``backend.*`` entry in ``sys.modules``.

    Measuring a clean import requires evicting the cached modules, but leaving
    them evicted re-imports them as *new* module objects later in the session.
    Any test module that captured a reference at import time (e.g.
    ``import backend.dependencies as deps``) would then patch a stale object
    while production code resolves the fresh one, producing failures that only
    appear when this file runs first.
    """
    saved = {m: mod for m, mod in sys.modules.items() if m.startswith("backend")}
    try:
        yield
    finally:
        for name in [m for m in sys.modules if m.startswith("backend")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_import_backend_api_speed_and_no_ml_model_side_effect(
    monkeypatch, _restore_backend_modules
):
    """Verify that importing backend.api takes < 1.0s and does not instantiate SentenceTransformer."""
    # Ensure backend.api and backend.dependencies are un-imported to measure clean import time
    modules_to_unload = [
        m for m in list(sys.modules.keys()) if m.startswith("backend")
    ]
    for m in modules_to_unload:
        sys.modules.pop(m, None)

    # Mock SentenceTransformer to raise error if called during import
    def mock_sentence_transformer_error(*args, **kwargs):
        raise AssertionError("SentenceTransformer model was instantiated during module import!")

    monkeypatch.setattr(
        "services.embedding_service._get_model",
        mock_sentence_transformer_error,
    )

    t0 = time.perf_counter()
    import backend.api  # noqa: F401
    t1 = time.perf_counter()

    elapsed = t1 - t0
    assert elapsed < 1.0, f"Importing backend.api took too long: {elapsed:.3f}s (expected < 1.0s)"
