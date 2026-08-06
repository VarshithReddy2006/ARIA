"""Executable enforcement of the architectural dependency rules.

SDD section 2.3 states the dependency rule and adds that it is "enforced in CI by
static import analysis — by our own product, once it can". Until the product can
analyse itself, this module is that enforcement.

These are the highest-leverage tests in the suite. Every other test verifies
behaviour, which a reviewer can also check by reading. These verify a property that
degrades silently: one convenient import from a domain module into an adapter costs
nothing today and makes the layer untestable and unswappable a year from now. The
previous architecture's ``services`` package importing ``backend.dependencies`` is
exactly that failure, arrived at one import at a time.

They also double as dogfooding: the rules encoded here are the rules the CI
architecture gate of PRD Phase 5 will offer to customers.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

import pytest

import ria

#: Root of the package under analysis.
PACKAGE_ROOT = Path(ria.__file__).parent

#: Top-level packages of the legacy application. Nothing in ``ria`` may import
#: them: the new implementation must be able to stand alone, and a single import
#: would tie its lifetime to code the foundation documents supersede.
LEGACY_PACKAGES = frozenset(
    {
        "backend",
        "services",
        "agents",
        "core",
        "models",
        "memory",
        "storage",
        "frontend",
        "web_dashboard",
        "scripts",
    }
)

#: Root module names of the declared third-party dependencies. Derived by hand
#: rather than from installed metadata so the rule holds in any environment,
#: including one where an extra package happens to be present.
THIRD_PARTY_ROOTS = frozenset(
    {
        "fastapi",
        "starlette",
        "uvicorn",
        "pydantic",
        "pydantic_settings",
        "dotenv",
        "httpx",
        "typer",
        "click",
        "networkx",
        "sentence_transformers",
        "torch",
        "transformers",
        "chromadb",
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_javascript",
        "tree_sitter_typescript",
        "google",
        "openai",
        "numpy",
        "prometheus_client",
    }
)


def python_modules() -> Iterator[Tuple[str, Path]]:
    """Yield every module in the package as a dotted name and a path.

    Yields:
        Tuples of dotted module name and file path.
    """
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        relative = path.relative_to(PACKAGE_ROOT.parent)
        parts = list(relative.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        yield ".".join(parts), path


def imported_roots(path: Path) -> Set[str]:
    """Collect the root module names a file imports.

    Relative imports are excluded: they cannot cross a package boundary and are
    therefore irrelevant to the rules being enforced.

    Args:
        path: File to analyse.

    Returns:
        The set of root module names imported, for example ``{"pydantic", "ria"}``.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                roots.add(node.module.split(".", 1)[0])
    return roots


def imported_modules(path: Path) -> Set[str]:
    """Collect the fully qualified module names a file imports.

    Args:
        path: File to analyse.

    Returns:
        The set of dotted module names imported.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            modules.add(node.module)
    return modules


@pytest.fixture(scope="module")
def module_imports() -> Dict[str, Set[str]]:
    """Fully qualified imports of every module, keyed by module name."""
    return {name: imported_modules(path) for name, path in python_modules()}


@pytest.fixture(scope="module")
def module_roots() -> Dict[str, Set[str]]:
    """Imported root module names of every module, keyed by module name."""
    return {name: imported_roots(path) for name, path in python_modules()}


def modules_in(layer: str, imports: Dict[str, Set[str]]) -> List[str]:
    """Select modules belonging to a layer.

    Args:
        layer: Dotted layer prefix, for example ``ria.domain``.
        imports: Mapping of module name to its imports.

    Returns:
        Names of modules in the layer.
    """
    return [name for name in imports if name == layer or name.startswith(layer + ".")]


class TestPackageDiscovery:
    """Sanity checks on the analysis itself."""

    def test_finds_every_layer(self, module_imports: Dict[str, Set[str]]) -> None:
        """The analysis covers all layers, so a rule cannot pass by finding nothing.

        Without this, a broken discovery helper would make every rule below
        vacuously true — the worst outcome for an architecture test.
        """
        for layer in (
            "ria.domain",
            "ria.ports",
            "ria.application",
            "ria.infrastructure",
            "ria.config",
            "ria.observability",
        ):
            assert modules_in(layer, module_imports), layer

    def test_every_module_parses(self, module_imports: Dict[str, Set[str]]) -> None:
        """Every file is syntactically valid Python."""
        assert len(module_imports) > 20


class TestLegacyIsolation:
    """The new implementation stands alone."""

    def test_no_module_imports_the_legacy_application(
        self, module_roots: Dict[str, Set[str]]
    ) -> None:
        """Nothing in ``ria`` may import a legacy top-level package.

        A single such import would tie the new implementation's lifetime to code the
        foundation documents supersede, and would make the eventual removal of that
        code a cross-cutting change rather than a deletion.
        """
        offenders = {
            name: sorted(roots & LEGACY_PACKAGES)
            for name, roots in module_roots.items()
            if roots & LEGACY_PACKAGES
        }
        assert offenders == {}


class TestDomainPurity:
    """The domain layer depends on nothing."""

    def test_domain_imports_only_itself(
        self, module_imports: Dict[str, Set[str]]
    ) -> None:
        """A domain module may import only the standard library and ``ria.domain``.

        This is what makes every invariant in the domain testable in microseconds and
        independent of infrastructure, and it is the property the whole layering
        exists to protect.
        """
        offenders: Dict[str, List[str]] = {}
        for name in modules_in("ria.domain", module_imports):
            forbidden = sorted(
                module
                for module in module_imports[name]
                if module.startswith("ria.") and not module.startswith("ria.domain")
            )
            if forbidden:
                offenders[name] = forbidden
        assert offenders == {}

    def test_domain_imports_no_third_party_package(
        self, module_roots: Dict[str, Set[str]]
    ) -> None:
        """The domain uses no third-party library, not even for validation.

        Pydantic in the domain would invert the dependency rule: the innermost layer
        would depend on a library chosen for a boundary concern, and swapping that
        library would become a domain change.
        """
        offenders = {
            name: sorted(module_roots[name] & THIRD_PARTY_ROOTS)
            for name in modules_in("ria.domain", module_roots)
            if module_roots[name] & THIRD_PARTY_ROOTS
        }
        assert offenders == {}


class TestPortPurity:
    """The ports layer declares interfaces over the domain only."""

    def test_ports_import_only_domain_and_ports(
        self, module_imports: Dict[str, Set[str]]
    ) -> None:
        """A port may reference the domain and other ports, nothing else.

        A port importing an adapter would make the interface depend on one of its
        implementations, which defeats the substitution the ports exist to enable.
        """
        offenders: Dict[str, List[str]] = {}
        for name in modules_in("ria.ports", module_imports):
            forbidden = sorted(
                module
                for module in module_imports[name]
                if module.startswith("ria.")
                and not module.startswith(("ria.domain", "ria.ports"))
            )
            if forbidden:
                offenders[name] = forbidden
        assert offenders == {}

    def test_ports_import_no_third_party_package(
        self, module_roots: Dict[str, Set[str]]
    ) -> None:
        """An interface must not name a vendor type in its signature."""
        offenders = {
            name: sorted(module_roots[name] & THIRD_PARTY_ROOTS)
            for name in modules_in("ria.ports", module_roots)
            if module_roots[name] & THIRD_PARTY_ROOTS
        }
        assert offenders == {}


class TestLayerDirection:
    """Dependencies point downward only."""

    def test_application_does_not_import_infrastructure(
        self, module_imports: Dict[str, Set[str]]
    ) -> None:
        """Use cases depend on ports, never on the adapters behind them.

        Otherwise a use case cannot be tested without a database, and the storage
        substitution contemplated in SDD open question T2 becomes a rewrite.
        """
        offenders = {
            name: sorted(
                module
                for module in module_imports[name]
                if module.startswith("ria.infrastructure")
            )
            for name in modules_in("ria.application", module_imports)
            if any(
                module.startswith("ria.infrastructure")
                for module in module_imports[name]
            )
        }
        assert offenders == {}

    def test_infrastructure_does_not_import_application(
        self, module_imports: Dict[str, Set[str]]
    ) -> None:
        """Adapters know nothing about the use cases that drive them."""
        offenders = {
            name: sorted(
                module
                for module in module_imports[name]
                if module.startswith("ria.application")
            )
            for name in modules_in("ria.infrastructure", module_imports)
            if any(
                module.startswith("ria.application") for module in module_imports[name]
            )
        }
        assert offenders == {}

    def test_nothing_imports_the_composition_root(
        self, module_imports: Dict[str, Set[str]]
    ) -> None:
        """The container is the outermost module and has no inbound dependency.

        An inward import of the container would recreate the global service-locator
        pattern that SDD section 7 rejects, in which any module can reach any
        collaborator and the graph becomes unanalysable.
        """
        offenders = {
            name: sorted(module_imports[name])
            for name in module_imports
            if name != "ria.container" and "ria.container" in module_imports[name]
        }
        assert offenders == {}

    def test_observability_does_not_import_upward(
        self, module_imports: Dict[str, Set[str]]
    ) -> None:
        """Cross-cutting observability sits below the layers that use it.

        Logging and metrics are called from every layer, so an upward import here
        would create a cycle with whichever layer it reached into.
        """
        offenders: Dict[str, List[str]] = {}
        for name in modules_in("ria.observability", module_imports):
            forbidden = sorted(
                module
                for module in module_imports[name]
                if module.startswith(
                    ("ria.application", "ria.infrastructure", "ria.container")
                )
            )
            if forbidden:
                offenders[name] = forbidden
        assert offenders == {}


class TestValidationLibraryContainment:
    """Third-party validation is confined to the configuration boundary."""

    def test_only_configuration_imports_pydantic(
        self, module_roots: Dict[str, Set[str]]
    ) -> None:
        """Pydantic appears in exactly one place: the settings adapter.

        Configuration is a boundary concern, so a validation library belongs there
        and nowhere else. Allowing it to spread is how a framework becomes load
        bearing in a domain model.
        """
        pydantic_users = sorted(
            name
            for name, roots in module_roots.items()
            if roots & {"pydantic", "pydantic_settings"}
        )
        assert pydantic_users == ["ria.config.settings"]


class TestNoModelCallsBelowReasoning:
    """PRD principle P2, enforced structurally.

    SDD section 2.1 draws a hard boundary: nothing below the reasoning layer calls a
    language model. No reasoning layer exists at Milestone 1, so the correct
    assertion is that no model client appears anywhere yet. The rule is encoded now
    rather than when the reasoning layer arrives, because it is far easier to keep a
    boundary than to reinstate one.
    """

    #: Root modules of language-model clients.
    MODEL_CLIENTS = frozenset(
        {"google", "openai", "anthropic", "sentence_transformers"}
    )

    def test_no_module_imports_a_model_client(
        self, module_roots: Dict[str, Set[str]]
    ) -> None:
        """No model or embedding client is imported anywhere in ``ria``."""
        offenders = {
            name: sorted(roots & self.MODEL_CLIENTS)
            for name, roots in module_roots.items()
            if roots & self.MODEL_CLIENTS
        }
        assert offenders == {}


class TestNoDeadImplementations:
    """The build brief forbids placeholder implementations.

    Rule 5 of the brief: no TODOs, no placeholder implementations, no incomplete
    classes; if something cannot be implemented yet, create the interface only. A
    stub that raises is exactly what the previous architecture shipped in
    ``agents/analyzer.py`` and ``agents/explainer.py``, and it is what
    ``ARCHITECTURE.md`` had to document as a defect.
    """

    def test_no_module_raises_not_implemented_outside_a_protocol(self) -> None:
        """``NotImplementedError`` appears nowhere in the implementation.

        Protocols use ``...`` as their body, so a genuine interface needs no raise.
        A raise therefore always indicates a stub masquerading as an implementation.
        """
        offenders: List[str] = []
        for name, path in python_modules():
            source = path.read_text(encoding="utf-8")
            if "NotImplementedError" in source:
                offenders.append(name)
        assert offenders == []

    def test_no_todo_markers(self) -> None:
        """No unfinished-work markers remain in the implementation."""
        offenders: List[str] = []
        for name, path in python_modules():
            source = path.read_text(encoding="utf-8")
            for marker in ("TODO", "FIXME", "XXX", "HACK"):
                if marker in source:
                    offenders.append(f"{name}: {marker}")
        assert offenders == []

    def test_no_module_is_empty(self) -> None:
        """Every module has content, including package initialisers.

        An empty ``__init__.py`` is a missing statement of what a package is for;
        the previous architecture's empty placeholder routers were registered and
        served nothing.
        """
        offenders = [
            name
            for name, path in python_modules()
            if not path.read_text(encoding="utf-8").strip()
        ]
        assert offenders == []
