"""Context Serializer implementing SerializerPort."""

import json

from ria.domain.context.entities import ContextPackage
from ria.ports.context.serializer import SerializerPort


class ContextSerializer(SerializerPort):
    """Serializer converting ContextPackage into JSON, Markdown, or Plain Text string formats."""

    def serialize_json(self, package: ContextPackage) -> str:
        data = {
            "package_id": package.package_id,
            "question": package.question,
            "metadata": {
                "total_sections": package.metadata.total_sections,
                "total_snippets": package.metadata.total_snippets,
                "total_tokens": package.metadata.total_tokens,
                "token_budget": package.metadata.token_budget,
            },
            "sections": [
                {
                    "title": sec.title,
                    "snippets": [
                        {
                            "snippet_id": snip.snippet_id,
                            "content": snip.content,
                            "citation": {
                                "repo": snip.citation.repo_name,
                                "commit": snip.citation.commit_sha,
                                "file": snip.citation.file_path.relative_path,
                                "symbol": snip.citation.symbol_moniker.value,
                                "start_line": snip.citation.start_line,
                                "end_line": snip.citation.end_line,
                            },
                            "score": snip.score.score_value,
                            "category": snip.score.category,
                        }
                        for snip in sec.snippets
                    ],
                }
                for sec in package.sections
            ],
        }
        return json.dumps(data, indent=2)

    def serialize_markdown(self, package: ContextPackage) -> str:
        lines: list[str] = [
            f"# Context Package ({package.package_id})",
            f"**Question:** {package.question}",
            f"**Tokens:** {package.metadata.total_tokens} / {package.metadata.token_budget}",
            "",
        ]
        for sec in package.sections:
            lines.append(f"## {sec.title}")
            for snip in sec.snippets:
                lines.append(
                    f"- [{snip.score.category}] {snip.content} "
                    f"*(file: {snip.citation.file_path.relative_path}:L{snip.citation.start_line})*"
                )
            lines.append("")
        return "\n".join(lines)

    def serialize_text(self, package: ContextPackage) -> str:
        lines: list[str] = [
            f"Context Package: {package.package_id}",
            f"Question: {package.question}",
            f"Tokens: {package.metadata.total_tokens} / {package.metadata.token_budget}",
            "---",
        ]
        for sec in package.sections:
            lines.append(f"=== {sec.title} ===")
            for snip in sec.snippets:
                lines.append(f"[{snip.score.category}] {snip.content} ({snip.citation.file_path.relative_path}:L{snip.citation.start_line})")
            lines.append("")
        return "\n".join(lines)
