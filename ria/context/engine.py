"""Context Engine entry point."""

from ria.domain.context.entities import ContextPackage
from ria.domain.context.value_objects import ContextRequest
from ria.domain.sync.value_objects import CommitReference, RepositoryIdentity
from ria.ports.context.builder import ContextBuilderPort
from ria.ports.context.serializer import SerializerPort
from ria.ports.query.engine import QueryEnginePort
from ria.ports.search.engine import SearchEnginePort
from ria.ports.storage.fact_store import FactStorePort


class ContextEngine:
    """Core ContextEngine coordinating ContextBuilderPort and SerializerPort."""

    def __init__(
        self,
        builder: ContextBuilderPort,
        serializer: SerializerPort,
    ) -> None:
        self._builder = builder
        self._serializer = serializer

    def assemble_and_serialize(
        self,
        request: ContextRequest,
        search_engine: SearchEnginePort,
        query_engine: QueryEnginePort,
        fact_store: FactStorePort,
        repo_id: RepositoryIdentity,
        commit: CommitReference,
        fmt: str = "json",
    ) -> tuple[ContextPackage, str]:
        package = self._builder.build_context(request, search_engine, query_engine, fact_store, repo_id, commit)

        if fmt.lower() == "markdown":
            formatted = self._serializer.serialize_markdown(package)
        elif fmt.lower() == "text":
            formatted = self._serializer.serialize_text(package)
        else:
            formatted = self._serializer.serialize_json(package)

        return package, formatted
