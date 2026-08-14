"""Memory package for ARIA.

Contains vector embeddings storage (ChromaDB).
"""

from .chroma_store import ChromaStore

__all__ = [
    "ChromaStore",
]
