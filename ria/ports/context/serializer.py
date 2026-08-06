"""Serializer Port Protocol."""

from typing import Protocol, runtime_checkable

from ria.domain.context.entities import ContextPackage


@runtime_checkable
class SerializerPort(Protocol):
    """Protocol for serializing ContextPackage into target string formats."""

    def serialize_json(self, package: ContextPackage) -> str:
        """Serialize package into JSON format."""
        ...

    def serialize_markdown(self, package: ContextPackage) -> str:
        """Serialize package into Markdown format."""
        ...

    def serialize_text(self, package: ContextPackage) -> str:
        """Serialize package into Plain Text format."""
        ...
