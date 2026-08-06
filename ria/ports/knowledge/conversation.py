"""Conversation Manager Port Protocol."""

from typing import Optional, Protocol, runtime_checkable

from ria.domain.knowledge.entities import ConversationContext
from ria.domain.knowledge.value_objects import ConversationId, ConversationTurn


@runtime_checkable
class ConversationManagerPort(Protocol):
    """Protocol for managing session conversation history."""

    def get_conversation(
        self,
        conversation_id: ConversationId,
    ) -> Optional[ConversationContext]:
        """Retrieve ConversationContext for conversation_id."""
        ...

    def add_turn(
        self,
        conversation_id: ConversationId,
        turn: ConversationTurn,
    ) -> ConversationContext:
        """Append turn to conversation history."""
        ...

    def clear_conversation(
        self,
        conversation_id: ConversationId,
    ) -> None:
        """Clear conversation history on repository version change."""
        ...
