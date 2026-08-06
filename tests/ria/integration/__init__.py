"""Integration tests exercising real adapters.

These tests use a real SQLite database, a real filesystem blob store, real git
repositories created on disk, and the real composition root. Every artefact is
confined to a pytest temporary directory.

Tests requiring the git executable are marked with
:data:`tests.ria.conftest.requires_git` and skip cleanly where git is unavailable,
so the suite remains runnable in a minimal container.
"""
