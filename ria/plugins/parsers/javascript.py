"""JavaScript Tree-sitter Parser Plugin."""

import tree_sitter_javascript
from ria.domain.index.value_objects import Language
from ria.plugins.parsers.base import BaseTreeSitterPlugin
from ria.ports.index.parser_registry import PluginCapabilities, PluginMetadata


class JavaScriptTreeSitterPlugin(BaseTreeSitterPlugin):
    """Tree-sitter parser plugin implementation for JavaScript."""

    def __init__(self) -> None:
        super().__init__(
            language_ptr=tree_sitter_javascript.language(), language_name="javascript"
        )

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="tree_sitter_javascript",
            version="1.0.0",
            author="RIA Core Team",
            description="Official Tree-sitter parser plugin for JavaScript files.",
        )

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(supported_languages=(Language.JAVASCRIPT,))
