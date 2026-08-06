"""Language Resolvers Package."""

from ria.resolution.language.javascript import JavaScriptLanguageResolver
from ria.resolution.language.python import PythonLanguageResolver
from ria.resolution.language.typescript import TypeScriptLanguageResolver

__all__ = [
    "PythonLanguageResolver",
    "TypeScriptLanguageResolver",
    "JavaScriptLanguageResolver",
]
