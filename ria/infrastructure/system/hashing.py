"""Hashlib Hashing Adapter implementing HashingPort."""

import hashlib
from pathlib import Path

from ria.domain.index.value_objects import ContentHash
from ria.infrastructure.exceptions import FilesystemError
from ria.ports.index.filesystem import FilesystemPort
from ria.ports.index.hashing import HashingPort


class HashlibHashingAdapter(HashingPort):
    """Hashlib SHA-256 adapter for byte arrays and filesystem stream hashing."""

    def hash_bytes(self, data: bytes) -> ContentHash:
        """Compute SHA-256 hex digest of data bytes."""
        digest = hashlib.sha256(data).hexdigest()
        return ContentHash(sha256_hex=digest)

    def hash_file(self, path: Path, fs: FilesystemPort) -> ContentHash:
        """Read file contents using FilesystemPort and return SHA-256 digest."""
        try:
            content = fs.read_bytes(path)
            return self.hash_bytes(content)
        except Exception as err:
            raise FilesystemError(f"Failed to read file '{path}' for hashing: {err}") from err
