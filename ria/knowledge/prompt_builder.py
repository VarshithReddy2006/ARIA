"""Prompt Builder implementing PromptBuilderPort."""

from ria.domain.context.entities import ContextPackage
from ria.domain.knowledge.value_objects import IntentType, PromptPackage
from ria.ports.knowledge.prompt import PromptBuilderPort


class PromptBuilder(PromptBuilderPort):
    """Builder rendering deterministic system and user prompts incorporating ContextPackage facts."""

    def build_prompt(
        self,
        question: str,
        context: ContextPackage,
        intent: IntentType,
    ) -> PromptPackage:
        sys_prompt = (
            f"You are the Repository Intelligence Agent (RIA) v2. "
            f"Answer the user's question accurately using ONLY the provided semantic context snippets. "
            f"Target Intent: {intent.value}. "
            f"Cite every file and symbol referenced in your answer."
        )

        context_lines: list[str] = [f"Context for question: '{question}'"]
        for sec in context.sections:
            context_lines.append(f"Section: {sec.title}")
            for snip in sec.snippets:
                context_lines.append(
                    f"[{snip.citation.symbol_moniker.value}] {snip.content} "
                    f"({snip.citation.file_path.relative_path}:L{snip.citation.start_line})"
                )

        usr_prompt = f"Question: {question}\n\n" + "\n".join(context_lines)

        return PromptPackage(
            system_prompt=sys_prompt,
            user_prompt=usr_prompt,
        )
