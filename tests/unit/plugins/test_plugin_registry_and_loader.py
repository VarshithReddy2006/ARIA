"""Unit tests for PluginRegistry and PluginLoader."""

from ria.domain.index.value_objects import Language
from ria.plugins import (
    JavaScriptTreeSitterPlugin,
    PluginHealthStatus,
    PluginLoader,
    PluginRegistry,
    PythonTreeSitterPlugin,
    TypeScriptTreeSitterPlugin,
)


def test_plugin_registry_registration_and_lookup() -> None:
    registry = PluginRegistry()
    py_plugin = PythonTreeSitterPlugin()

    registry.register_parser(Language.PYTHON, py_plugin)

    assert registry.get_parser(Language.PYTHON) is py_plugin
    assert Language.PYTHON in registry.supported_languages()

    # Unregister
    assert registry.remove_parser(Language.PYTHON)
    assert registry.get_parser(Language.PYTHON) is None


def test_plugin_registry_enable_disable() -> None:
    registry = PluginRegistry()
    ts_plugin = TypeScriptTreeSitterPlugin()

    registry.register_parser(Language.TYPESCRIPT, ts_plugin)
    assert registry.get_parser(Language.TYPESCRIPT) is ts_plugin

    # Disable
    assert registry.disable_plugin("tree_sitter_typescript")
    assert registry.get_parser(Language.TYPESCRIPT) is None

    # Enable
    assert registry.enable_plugin("tree_sitter_typescript")
    assert registry.get_parser(Language.TYPESCRIPT) is ts_plugin


def test_plugin_registry_health_checks() -> None:
    registry = PluginRegistry()
    js_plugin = JavaScriptTreeSitterPlugin()

    registry.register_parser(Language.JAVASCRIPT, js_plugin)
    health = registry.check_all_health()
    assert len(health) == 1
    assert health[0].status == PluginHealthStatus.HEALTHY
    assert health[0].plugin_id == "tree_sitter_javascript"


def test_plugin_loader() -> None:
    registry = PluginRegistry()
    loader = PluginLoader(registry)

    loader.load_plugin_class(PythonTreeSitterPlugin)
    loader.load_plugin_class(TypeScriptTreeSitterPlugin)

    assert Language.PYTHON in registry.supported_languages()
    assert Language.TYPESCRIPT in registry.supported_languages()
