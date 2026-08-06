"""Python Tree-sitter Parser Plugin."""

import tree_sitter_python
from ria.domain.index.value_objects import Language
from ria.plugins.parsers.base import BaseTreeSitterPlugin
from ria.ports.index.parser_registry import PluginCapabilities, PluginMetadata


class PythonTreeSitterPlugin(BaseTreeSitterPlugin):
    """Tree-sitter parser plugin implementation for Python."""

    def __init__(self) -> None:
        super().__init__(
            language_ptr=tree_sitter_python.language(), language_name="python"
        )

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="tree_sitter_python",
            version="1.0.0",
            author="RIA Core Team",
            description="Official Tree-sitter parser plugin for Python files.",
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(supported_languages=(Language.PYTHON,))
