"""Conversation Manager implementing ConversationManagerPort."""

from typing import Dict, Optional

from ria.domain.knowledge.entities import ConversationContext
from ria.domain.knowledge.value_objects import ConversationId, ConversationTurn
from ria.ports.knowledge.conversation import ConversationManagerPort


class ConversationManager(ConversationManagerPort):
    """In-memory manager tracking conversation turns by ConversationId."""

    def __init__(self) -> None:
        self._conversations: Dict[str, list[ConversationTurn]] = {}

    def get_conversation(
        self,
        conversation_id: ConversationId,
    ) -> Optional[ConversationContext]:
        turns = self._conversations.get(conversation_id.value)
        if turns is None:
            return None
        return ConversationContext(conversation_id=conversation_id, turns=tuple(turns))

    def add_turn(
        self,
        conversation_id: ConversationId,
        turn: ConversationTurn,
    ) -> ConversationContext:
        cid_val = conversation_id.value
        if cid_val not in self._conversations:
            self._conversations[cid_val] = []
        self._conversations[cid_val].append(turn)
        return ConversationContext(conversation_id=conversation_id, turns=tuple(self._conversations[cid_val]))

    def clear_conversation(
        self,
        conversation_id: ConversationId,
    ) -> None:
        self._conversations.pop(conversation_id.value, None)
