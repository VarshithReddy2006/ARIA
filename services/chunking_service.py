"""Code Chunking Service module.

Splits source code into logical, overlapping segments while preserving context
and enriched architectural metadata (category, source priority, language).
"""

import os
from typing import Dict, List, Any

from core.file_classifier import classify_file, CATEGORY_PRODUCTION, CATEGORY_GENERATED


class CodeChunker:
    """Helper to split code and documents into logical snippets with classification metadata."""

    def __init__(
        self,
        chunk_size: int = 1500,
        chunk_overlap: int = 200,
        *,
        max_tokens_per_chunk: int | None = None,
        overlap_tokens: int | None = None,
    ) -> None:
        """Initialize the chunker with current or legacy size parameter names."""
        self._legacy_string_output = (
            max_tokens_per_chunk is not None or overlap_tokens is not None
        )
        self.chunk_size = (
            max_tokens_per_chunk if max_tokens_per_chunk is not None else chunk_size
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
        """Identifies language based on file classification."""
        classification = classify_file(file_path)
        return classification.get("language", "text").lower()

    def chunk_file(
        self, file_path: str, content: str
    ) -> List[Dict[str, Any]] | List[str]:
        """Splits the file content into chunks with enriched metadata.

        Ensures chunks align with line boundaries and include metadata:
          - path: file path
          - chunk_id: index
          - content: chunk text
          - language: language name
          - category: "production" | "test" | "docs" | "example" | "config" | "generated"
          - source_priority: float
          - is_entry_point: bool
        """
        classification = classify_file(file_path)
        language = classification.get("language", "text").lower()
        category = classification.get("category", CATEGORY_PRODUCTION)
        source_priority = classification.get("source_priority", 1.0)

        # Skip clearly machine-generated artifacts (lockfiles, minified files, map files)
        if category == CATEGORY_GENERATED or source_priority == 0.0:
            return []

        # Candidate entry point check
        fn = os.path.basename(file_path).lower()
        is_entry = category == CATEGORY_PRODUCTION and fn in (
            "main.py",
            "__main__.py",
            "__init__.py",
            "app.py",
            "server.py",
            "index.ts",
            "index.js",
            "main.tsx",
            "main.go",
            "main.rs",
        )

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
                        "category": category,
                        "source_priority": source_priority,
                        "is_entry_point": is_entry,
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
                            "category": category,
                            "source_priority": source_priority,
                            "is_entry_point": is_entry,
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
                        "category": category,
                        "source_priority": source_priority,
                        "is_entry_point": is_entry,
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
                        "category": category,
                        "source_priority": source_priority,
                        "is_entry_point": is_entry,
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

        # Filter empty chunks and re-index chunk_id
        valid_chunks = []
        c_idx = 1
        for c in chunks:
            if c.get("content") and c["content"].strip():
                c["chunk_id"] = c_idx
                valid_chunks.append(c)
                c_idx += 1

        return self._format_chunks(valid_chunks)
