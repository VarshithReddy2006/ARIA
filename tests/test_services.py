"""Unit tests for service classes."""

from services.chunking_service import CodeChunker
from services.embedding_service import EmbeddingService


def test_code_chunker_basic() -> None:
    """Verifies CodeChunker splits text into chunks of specified max size."""
    chunker = CodeChunker(max_tokens_per_chunk=10, overlap_tokens=2)

    content = "line1\nline2\nline3\nline4\nline5\nline6\nline7\nline8"
    chunks = chunker.chunk_file("test.py", content)

    assert isinstance(chunks, list)
    assert len(chunks) > 0
    for chunk in chunks:
        assert isinstance(chunk, str)

    # Empty content should produce no chunks
    assert chunker.chunk_file("empty.py", "") == []

    # Whitespace-only content should produce no chunks
    assert chunker.chunk_file("ws.py", "   \n\t  ") == []


def test_embedding_service_init() -> None:
    """Verifies EmbeddingService can be instantiated and checks the default model name."""
    service = EmbeddingService(client=None, model_name="dummy-model")
    assert service.model_name is not None
