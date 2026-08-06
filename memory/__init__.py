"""Memory package for the Repo Intelligence Agent.

Contains vector embeddings storage (ChromaDB).
"""

from .chroma_store import ChromaStore

__all__ = [
    "ChromaStore",
]
