"""Tests for the ``ria`` implementation of the foundation specifications.

Layout mirrors the architecture under test:

``unit/``
    Pure tests of the domain and application layers. No filesystem, no database,
    no subprocess. Every collaborator is a fake from :mod:`tests.ria.fakes`.
``integration/``
    Tests that exercise real adapters: SQLite, the filesystem blob store, the git
    subprocess client, and the composition root.

Unit tests run in milliseconds because the domain layer imports nothing outside
the standard library, which is the practical dividend of the dependency rule in
SDD section 2.3.
"""
