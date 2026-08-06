"""Code Chunking Service module.

Splits source code into logical, overlapping segments while preserving context
and metadata.
"""

import os
from typing import Dict, List, Any


class CodeChunker:
    """Helper to split code and documents into logical snippets."""

    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        *,
        max_tokens_per_chunk: int | None = None,
        overlap_tokens: int | None = None,
    ) -> None:
        """Initialize the chunker with current or legacy size parameter names.

        ``max_tokens_per_chunk`` and ``overlap_tokens`` are retained as
        compatibility aliases for the character-based current settings. Calls
        using those legacy names also retain their historical string output.
        """
        self._legacy_string_output = (
            max_tokens_per_chunk is not None or overlap_tokens is not None
        )
        self.chunk_size = (
            max_tokens_per_chunk
            if max_tokens_per_chunk is not None
            else chunk_size
        )
        self.chunk_overlap = (
            overlap_tokens if overlap_tokens is not None else chunk_overlap
        )

    def _format_chunks(
        self, chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]] | List[str]:
        """Return the historical text-only shape only for legacy calls."""
        if self._legacy_string_output:
            return [chunk["content"] for chunk in chunks]
        return chunks

    def detect_language(self, file_path: str) -> str:
        """Identifies language based on file suffix.

        Args:
            file_path: Path to the file.

        Returns:
            The language identifier string (e.g. 'python', 'javascript').
        """
        ext = os.path.splitext(file_path)[1].lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".html": "html",
            ".css": "css",
            ".md": "markdown",
            ".json": "json",
            ".sh": "bash",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".c": "c",
            ".h": "c",
            ".cs": "csharp",
            ".sql": "sql",
        }
        return mapping.get(ext, "text")

    def chunk_file(
        self, file_path: str, content: str
    ) -> List[Dict[str, Any]] | List[str]:
        """Splits the file content into chunks.

        Ensures chunks align with line boundaries and include metadata.

        Args:
            file_path: Relative file path.
            content: Raw text content of the file.

        Returns:
            A list of dictionary records containing path, chunk_id, content, and language.
        """
        language = self.detect_language(file_path)

        # Empty or whitespace-only file: return no chunks
        if not content or not content.strip():
            return []

        # Very short file: single chunk
        if len(content) <= self.chunk_size:
            return self._format_chunks(
                [
                    {
                        "path": file_path,
                        "chunk_id": 1,
                        "content": content,
                        "language": language,
                    }
                ]
            )

        chunks = []
        lines = content.splitlines()

        current_chunk_lines = []
        current_chunk_size = 0
        chunk_id = 1

        for line in lines:
            line_len = len(line) + 1  # +1 for newline character

            # If a single line exceeds chunk size, chunk it separately or add it
            if line_len > self.chunk_size:
                # Flush the current chunk if it has any contents
                if current_chunk_lines:
                    chunks.append(
                        {
                            "path": file_path,
                            "chunk_id": chunk_id,
                            "content": "\n".join(current_chunk_lines),
                            "language": language,
                        }
                    )
                    chunk_id += 1
                    current_chunk_lines = []
                    current_chunk_size = 0

                # Add this long line as its own chunk
                chunks.append(
                    {
                        "path": file_path,
                        "chunk_id": chunk_id,
                        "content": line,
                        "language": language,
                    }
                )
                chunk_id += 1
                continue

            # Check if adding this line exceeds the target chunk size
            if current_chunk_size + line_len > self.chunk_size:
                # Flush current chunk
                chunks.append(
                    {
                        "path": file_path,
                        "chunk_id": chunk_id,
                        "content": "\n".join(current_chunk_lines),
                        "language": language,
                    }
                )
                chunk_id += 1

                # Compute overlap: keep last few lines that fit in the overlap window
                overlap_lines = []
                overlap_size = 0
                for old_line in reversed(current_chunk_lines):
                    old_line_len = len(old_line) + 1
                    if overlap_size + old_line_len > self.chunk_overlap:
                        break
                    overlap_lines.insert(0, old_line)
                    overlap_size += old_line_len

                current_chunk_lines = overlap_lines
                current_chunk_size = overlap_size

            current_chunk_lines.append(line)
            current_chunk_size += line_len

        # Add any remaining text
        if current_chunk_lines:
            chunks.append(
                {
                    "path": file_path,
                    "chunk_id": chunk_id,
                    "content": "\n".join(current_chunk_lines),
                    "language": language,
                }
            )

        return self._format_chunks(chunks)
