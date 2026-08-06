"""Hashing Port abstraction."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from ria.domain.index.value_objects import ContentHash
from ria.ports.index.filesystem import FilesystemPort


@runtime_checkable
class HashingPort(Protocol):
    """Protocol for computing cryptographic hashes of data bytes and files.

    Preconditions: Data bytes must be non-null.
    Postconditions: Returns immutable ContentHash value object.
    """

    def hash_bytes(self, data: bytes) -> ContentHash:
        """Compute SHA-256 hash of byte sequence."""
        ...

    def hash_file(self, path: Path, fs: FilesystemPort) -> ContentHash:
        """Read file using FilesystemPort and compute SHA-256 hash."""
        ...
