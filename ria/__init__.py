"""ARIA — implementation of the foundation specifications.

This package implements the layered architecture defined in
``docs/foundation/02-SDD.md`` and the entity model defined in
``docs/foundation/03-DIGITAL-TWIN-SPEC.md``.

Package layout mirrors the architectural layers. The dependency rule from
SDD section 2.3 is absolute and CI-enforceable:

    application  ->  ports  ->  domain
    infrastructure -> ports  ->  domain
    container    ->  everything

``ria.domain`` imports nothing outside the standard library. No module inside
``ria`` may import from a delivery package (``backend``, ``frontend``).
"""

from __future__ import annotations

__all__ = ["__version__"]

#: Version of the ``ria`` implementation, independent of the legacy distribution
#: version declared in ``pyproject.toml``.
__version__ = "0.1.0"
