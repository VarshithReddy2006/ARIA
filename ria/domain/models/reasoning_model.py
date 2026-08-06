"""Reasoning model and provider value objects.

Defines ProviderConfiguration, ModelRequest, ModelResponse, PromptTemplate,
PromptExecution, StreamingChunk, and StreamingSession.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

__all__ = [
    "ProviderConfiguration",
    "ModelRequest",
    "ModelResponse",
    "PromptTemplate",
    "PromptExecution",
    "StreamingChunk",
    "StreamingSession",
]


@dataclass(frozen=True)
class ProviderConfiguration:
    """Configuration for an LLM Provider.

    Attributes:
        provider_name: Name of provider (e.g. 'openai', 'anthropic', 'google', 'local').
        model_name: Specific model moniker (e.g. 'gpt-4o', 'claude-3-5-sonnet', 'gemini-1.5-pro').
        temperature: Sampling temperature in [0.0, 2.0].
        max_tokens: Max output tokens limit.
        api_key: Optional API key string.
    """

    provider_name: str
    model_name: str
    temperature: float = 0.2
    max_tokens: int = 4096
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature must be within [0.0, 2.0], got {self.temperature}"
            )
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")


@dataclass(frozen=True)
class ModelRequest:
    """Unified provider-independent model execution request.

    Attributes:
        prompt_text: Input prompt text body.
        system_prompt: Optional system prompt instructions.
        temperature: Temperature parameter.
        max_tokens: Max response tokens.
    """

    prompt_text: str
    system_prompt: str = ""
    temperature: float = 0.2
    max_tokens: int = 4096


@dataclass(frozen=True)
class ModelResponse:
    """Unified provider-independent model execution response.

    Attributes:
        raw_text: Generated raw response text.
        model_name: Executing model name.
        token_count: Generated response token count.
        finish_reason: Termination reason ('stop', 'length', 'content_filter').
    """

    raw_text: str
    model_name: str
    token_count: int = 0
    finish_reason: str = "stop"


@dataclass(frozen=True)
class PromptTemplate:
    """Template for formatting prompt context.

    Attributes:
        name: Unique template name.
        template_text: Template raw string.
        version: Version moniker.
    """

    name: str
    template_text: str
    version: str = "1.0.0"


@dataclass(frozen=True)
class PromptExecution:
    """Record of a single prompt template rendering and execution.

    Attributes:
        template_name: Rendered template name.
        rendered_prompt: Final rendered prompt string.
        execution_time_seconds: Execution latency in seconds.
    """

    template_name: str
    rendered_prompt: str
    execution_time_seconds: float = 0.0


@dataclass(frozen=True)
class StreamingChunk:
    """A single token delta chunk in a streaming session.

    Attributes:
        session_id: Streaming session identifier.
        chunk_index: 0-indexed chunk sequence number.
        text_delta: Incremental text delta string.
        is_final: True if final chunk in stream.
    """

    session_id: str
    chunk_index: int
    text_delta: str
    is_final: bool = False

    def __post_init__(self) -> None:
        if self.chunk_index < 0:
            raise ValueError(
                f"chunk_index must be non-negative, got {self.chunk_index}"
            )


@dataclass(frozen=True)
class StreamingSession:
    """Metadata representing an active streaming session.

    Attributes:
        session_id: Session identifier.
        model_name: Active model name.
        created_at_iso: UTC creation timestamp.
    """

    session_id: str
    model_name: str
    created_at_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
