"""REST API Pydantic/Data Schemas."""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class RegisterRepositoryRequest:
    remote_url: str
    name: str


@dataclass
class UpdateRepositoryRequest:
    repo_id: str


@dataclass
class SearchRequest:
    repo_id: str
    query_text: str
    query_type: str = "prefix"


@dataclass
class QueryRequest:
    repo_id: str
    query_type: str
    symbol_moniker: Optional[str] = None
    file_path: Optional[str] = None


@dataclass
class ContextRequestSchema:
    repo_id: str
    question: str
    max_tokens: int = 4000
    format: str = "json"


@dataclass
class AskQuestionRequest:
    repo_id: str
    question: str
    conversation_id: Optional[str] = None
    provider_name: str = "mock"


@dataclass
class APIResponse:
    is_success: bool
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
