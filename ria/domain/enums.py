"""Enumerations and lifecycle transition tables.

Every lifecycle described in Twin Spec section 3.2 is encoded here as a
transition table adjacent to its enumeration. Transitions are validated through
:func:`assert_transition`, which makes an illegal state change raise rather than
silently corrupt the timeline.

Design note
-----------
The transition tables are data, not code branches. Adding a state means editing
one mapping; no ``if`` chain elsewhere needs to change. This is the same
table-driven approach SDD section 3 (L1) mandates for language classification.
"""

from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Mapping, Optional

from ria.domain.errors import IllegalStateTransitionError

__all__ = [
    "RepositoryStatus",
    "CommitIndexState",
    "ParseStatus",
    "FileClassification",
    "LanguageTier",
    "ResolutionMethod",
    "Facet",
    "BranchCadence",
    "ChangeKind",
    "IngestionStage",
    "JobKind",
    "JobState",
    "assert_transition",
    "REPOSITORY_TRANSITIONS",
    "COMMIT_INDEX_TRANSITIONS",
    "JOB_TRANSITIONS",
    "ScopeKind",
    "ReferenceKind",
    "InheritanceKind",
    "SemanticCapability",
    "NodeKind",
    "EdgeKind",
    "TwinState",
    "RepositoryHealth",
]


class _StrEnum(str, Enum):
    """String-valued enum with a stable ``str`` representation.

    ``str``-derived so that persistence adapters and log formatters can use the
    member directly without conversion, while comparisons against raw strings
    from the database remain correct.
    """

    def __str__(self) -> str:  # pragma: no cover - trivial
        return str(self.value)


class RepositoryStatus(_StrEnum):
    """Lifecycle state of a registered repository.

    Implements the lifecycle of Twin Spec section 3.2, entity ``Repository``::

        registered -> first_index -> active <-> degraded <-> paused -> archived

    ``REGISTERED`` is present because the specification's lifecycle string begins
    at ``registered`` while its field enumeration omits it; the state is required
    to represent a repository between registration and its first index build.
    ``INDEXING`` is the specification's ``first_index`` state, generalised to
    every build because subsequent builds occupy the same state.

    Purging is a hard delete performed by the persistence adapter and therefore
    has no representable state.
    """

    REGISTERED = "registered"
    INDEXING = "indexing"
    ACTIVE = "active"
    DEGRADED = "degraded"
    PAUSED = "paused"
    ARCHIVED = "archived"


#: Permitted repository transitions. ``ARCHIVED`` is terminal.
REPOSITORY_TRANSITIONS: Mapping[RepositoryStatus, FrozenSet[RepositoryStatus]] = {
    RepositoryStatus.REGISTERED: frozenset(
        {RepositoryStatus.INDEXING, RepositoryStatus.PAUSED, RepositoryStatus.ARCHIVED}
    ),
    RepositoryStatus.INDEXING: frozenset(
        {
            RepositoryStatus.ACTIVE,
            RepositoryStatus.DEGRADED,
            RepositoryStatus.PAUSED,
            RepositoryStatus.ARCHIVED,
        }
    ),
    RepositoryStatus.ACTIVE: frozenset(
        {
            RepositoryStatus.INDEXING,
            RepositoryStatus.DEGRADED,
            RepositoryStatus.PAUSED,
            RepositoryStatus.ARCHIVED,
        }
    ),
    RepositoryStatus.DEGRADED: frozenset(
        {
            RepositoryStatus.INDEXING,
            RepositoryStatus.ACTIVE,
            RepositoryStatus.PAUSED,
            RepositoryStatus.ARCHIVED,
        }
    ),
    RepositoryStatus.PAUSED: frozenset(
        {RepositoryStatus.INDEXING, RepositoryStatus.ACTIVE, RepositoryStatus.ARCHIVED}
    ),
    RepositoryStatus.ARCHIVED: frozenset(),
}


class CommitIndexState(_StrEnum):
    """Index lifecycle of a single commit.

    Implements Twin Spec section 3.2, entity ``Commit``::

        discovered -> pending -> indexing -> queryable   (terminal, immutable)
                                          -> failed      (retryable)
        queryable  -> orphaned                           (history rewrite)

    ``QUERYABLE`` is the atomic visibility boundary of SDD section 5.1 step 9: a
    commit is invisible to queries until it reaches this state, and visible
    immediately afterwards. There is no observable intermediate state.
    """

    DISCOVERED = "discovered"
    PENDING = "pending"
    INDEXING = "indexing"
    QUERYABLE = "queryable"
    FAILED = "failed"
    ORPHANED = "orphaned"

    @property
    def is_queryable(self) -> bool:
        """Whether facts for this commit may be served to consumers."""
        return self is CommitIndexState.QUERYABLE

    @property
    def facts_are_frozen(self) -> bool:
        """Whether the commit's factual fields may no longer change.

        Facts freeze once a commit becomes queryable. The index state itself may
        still move to ``ORPHANED``; nothing else may change.
        """
        return self in (CommitIndexState.QUERYABLE, CommitIndexState.ORPHANED)


#: Permitted commit index transitions. ``ORPHANED`` is terminal.
COMMIT_INDEX_TRANSITIONS: Mapping[CommitIndexState, FrozenSet[CommitIndexState]] = {
    CommitIndexState.DISCOVERED: frozenset(
        {CommitIndexState.PENDING, CommitIndexState.FAILED}
    ),
    CommitIndexState.PENDING: frozenset(
        {CommitIndexState.INDEXING, CommitIndexState.FAILED}
    ),
    CommitIndexState.INDEXING: frozenset(
        {CommitIndexState.QUERYABLE, CommitIndexState.FAILED}
    ),
    CommitIndexState.QUERYABLE: frozenset({CommitIndexState.ORPHANED}),
    CommitIndexState.FAILED: frozenset(
        {CommitIndexState.PENDING, CommitIndexState.ORPHANED}
    ),
    CommitIndexState.ORPHANED: frozenset(),
}


class ParseStatus(_StrEnum):
    """Parse outcome for a file unit.

    Twin Spec section 3.2, entity ``FileUnit``, enumerates ``parsed``,
    ``partial``, ``unparseable`` and ``skipped``. ``PENDING`` is added because a
    file unit is created during ingestion (Milestone 1) before any parser exists
    (Milestone 3); without it, an unparsed file would have to be recorded as
    ``skipped``, which is a false statement about coverage and would violate
    PRD principle P11.
    """

    PENDING = "pending"
    PARSED = "parsed"
    PARTIAL = "partial"
    UNPARSEABLE = "unparseable"
    SKIPPED = "skipped"

    @property
    def contributes_to_coverage(self) -> bool:
        """Whether this status counts as parsed when computing coverage."""
        return self in (ParseStatus.PARSED, ParseStatus.PARTIAL)


class FileClassification(_StrEnum):
    """Role of a file within the repository.

    Load-bearing rather than cosmetic: Twin Spec section 3.2 requires that
    generated and vendored code be excluded from health metrics, hotspot
    analysis and agent context while remaining available to dependency
    resolution. :attr:`counts_toward_metrics` expresses that single rule once.
    """

    SOURCE = "source"
    TEST = "test"
    CONFIG = "config"
    DOC = "doc"
    GENERATED = "generated"
    VENDORED = "vendored"
    BINARY = "binary"
    UNKNOWN = "unknown"

    @property
    def counts_toward_metrics(self) -> bool:
        """Whether the file participates in health, churn and hotspot metrics."""
        return self in (FileClassification.SOURCE, FileClassification.TEST)

    @property
    def is_parseable_candidate(self) -> bool:
        """Whether the parser layer should attempt extraction on this file."""
        return self in (
            FileClassification.SOURCE,
            FileClassification.TEST,
            FileClassification.GENERATED,
            FileClassification.VENDORED,
        )


class LanguageTier(_StrEnum):
    """Extraction tier available for a language.

    Implements the two-tier parser model of SDD section 3 (L2). The tier
    determines the best achievable :class:`ResolutionMethod` for relations
    derived from a file: ``TIER_A`` cannot produce ``EXACT`` relations.
    """

    #: Syntax only, via tree-sitter. Breadth without cross-file semantics.
    TIER_A = "tier_a"
    #: Resolved semantics via a SCIP or LSP indexer. Cross-file monikers.
    TIER_B = "tier_b"
    #: Recognised file type with no extractor.
    NONE = "none"

    @property
    def best_resolution_method(self) -> "ResolutionMethod":
        """Highest resolution method achievable from this tier."""
        if self is LanguageTier.TIER_B:
            return ResolutionMethod.EXACT
        if self is LanguageTier.TIER_A:
            return ResolutionMethod.HEURISTIC
        return ResolutionMethod.HEURISTIC


class ResolutionMethod(_StrEnum):
    """How a relation or symbol attribute was determined.

    One third of the mandatory provenance triple of Twin Spec section 3.2
    (``method``, ``confidence``, ``provenance``). Defined in Milestone 1 because
    the language catalogue must declare the ceiling each tier can reach; it is
    consumed by Milestone 4.
    """

    EXACT = "exact"
    INFERRED = "inferred"
    HEURISTIC = "heuristic"

    @property
    def rank(self) -> int:
        """Ordinal strength, higher is stronger. Used when merging tiers."""
        return {"heuristic": 0, "inferred": 1, "exact": 2}[self.value]


class Facet(_StrEnum):
    """The five facets of the Repository Digital Twin.

    Defined by Twin Spec section 1.2 and section 6.2. Declared in Milestone 1
    because :class:`~ria.domain.models.repository.IndexPolicy` selects facets at
    registration time.
    """

    STRUCTURE = "structure"
    HISTORY = "history"
    RUNTIME = "runtime"
    INTENT = "intent"
    SOCIAL = "social"


class BranchCadence(_StrEnum):
    """Snapshot cadence for a class of branches.

    Implements the snapshot cadence policy table of Twin Spec section 6.3.
    """

    #: Index every commit reachable on the branch.
    EVERY_COMMIT = "every_commit"
    #: Index only the branch head, refreshed on push.
    HEAD_ONLY = "head_only"
    #: Index only commits with more than one parent.
    MERGE_ONLY = "merge_only"
    #: Do not index.
    NEVER = "never"


def assert_transition(
    entity: str,
    current: _StrEnum,
    requested: _StrEnum,
    table: Mapping[_StrEnum, FrozenSet[_StrEnum]],
) -> None:
    """Validate a lifecycle transition against its table.

    A transition to the current state is always permitted and is a no-op, which
    keeps idempotent retries from raising.

    Args:
        entity: Entity name used in the error message, for example ``"Commit"``.
        current: State the entity is in.
        requested: State the entity should move to.
        table: Transition table for the entity's state enumeration.

    Raises:
        IllegalStateTransitionError: If the transition is not permitted.
    """
    if current is requested:
        return
    if requested not in table.get(current, frozenset()):
        raise IllegalStateTransitionError(entity, str(current), str(requested))


# ---------------------------------------------------------------------------
# Milestone 2 — ingestion
# ---------------------------------------------------------------------------


class ChangeKind(_StrEnum):
    """How one path differs between two commits.

    Produced by :func:`ria.domain.diff.compute_change_set`. ``RENAMED`` is a
    distinct kind rather than a delete plus an add because the two paths share a
    content hash, which means the parse result is reusable and only the path
    identity changed. Collapsing a rename into a delete and an add would discard
    that and force a needless reparse.
    """

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"

    @property
    def requires_reparse(self) -> bool:
        """Whether the change invalidates a cached parse result for the content.

        A rename does not: the bytes are unchanged, so the parse cache entry keyed
        by content hash remains valid (Twin Spec section 6.4).
        """
        return self in (ChangeKind.ADDED, ChangeKind.MODIFIED)


class IngestionStage(_StrEnum):
    """Named stage of the ingestion pipeline.

    Reported through :class:`~ria.ports.progress.ProgressSink` so that a long
    ingestion is observable rather than opaque. Ordering matches the pipeline of
    SDD section 5.1, which is why the members carry an explicit :attr:`order`
    rather than relying on declaration position.
    """

    ACQUIRE = "acquire"
    RESOLVE = "resolve"
    DISCOVER = "discover"
    ENUMERATE = "enumerate"
    HASH = "hash"
    STORE = "store"
    DETECT_CHANGES = "detect_changes"
    PARSE = "parse"
    RESOLVE_SEMANTICS = "resolve_semantics"
    PERSIST = "persist"
    FINALISE = "finalise"

    @property
    def order(self) -> int:
        """Position of the stage in the pipeline, starting at one."""
        return _INGESTION_STAGE_ORDER[self]


#: Pipeline position of each stage. A mapping rather than enum ordering, so that
#: inserting a stage in a later milestone is an explicit edit here.
_INGESTION_STAGE_ORDER: Mapping["IngestionStage", int] = {
    IngestionStage.ACQUIRE: 1,
    IngestionStage.RESOLVE: 2,
    IngestionStage.DISCOVER: 3,
    IngestionStage.ENUMERATE: 4,
    IngestionStage.HASH: 5,
    IngestionStage.STORE: 6,
    IngestionStage.DETECT_CHANGES: 7,
    IngestionStage.PARSE: 8,
    IngestionStage.RESOLVE_SEMANTICS: 9,
    IngestionStage.PERSIST: 10,
    IngestionStage.FINALISE: 11,
}


class JobKind(_StrEnum):
    """Unit of background work.

    Deliberately coarse. One job per commit rather than one per file, because a
    job carries lease and retry overhead that would dominate at file granularity,
    and because a commit is the unit whose visibility must be atomic (SDD section
    5.1). Later milestones add kinds; they do not subdivide these.
    """

    #: Clone or fetch a repository's mirror.
    ACQUIRE_REPOSITORY = "acquire_repository"
    #: Discover commits and branches, and enqueue ingestion work.
    DISCOVER_COMMITS = "discover_commits"
    #: Enumerate, hash, store and persist one commit's tree.
    INGEST_COMMIT = "ingest_commit"


class JobState(_StrEnum):
    """Lifecycle of a queued job.

    Implements the durable queue of SDD section 4::

        queued -> leased -> succeeded
                         -> failed -> queued     (retry, attempts remain)
                                   -> dead       (attempts exhausted)
                  leased -> queued               (lease expired)
        queued | leased -> cancelled

    ``LEASED`` rather than ``running`` because the state records a claim with an
    expiry, not an assumption about a live process. A worker that dies leaves an
    expired lease that another worker reclaims; a state called ``running`` would
    have to be reconciled against process liveness we cannot observe.
    """

    QUEUED = "queued"
    LEASED = "leased"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD = "dead"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Whether the runner will advance this job no further.

        ``DEAD`` is terminal in this sense but is deliberately still requeueable by
        an operator: a job that exhausted its attempts because of an outage should
        be replayable without being recreated, which would lose its history.
        """
        return self in (JobState.SUCCEEDED, JobState.DEAD, JobState.CANCELLED)

    @property
    def is_claimable(self) -> bool:
        """Whether a worker may lease a job in this state."""
        return self is JobState.QUEUED


#: Permitted job transitions. ``FAILED`` is transient: the runner immediately
#: moves a failed job to ``QUEUED`` or ``DEAD`` depending on remaining attempts,
#: so it is observable in a query but is not a resting state.
JOB_TRANSITIONS: Mapping[JobState, FrozenSet[JobState]] = {
    JobState.QUEUED: frozenset({JobState.LEASED, JobState.CANCELLED}),
    JobState.LEASED: frozenset(
        {
            JobState.SUCCEEDED,
            JobState.FAILED,
            JobState.QUEUED,
            JobState.CANCELLED,
        }
    ),
    JobState.FAILED: frozenset({JobState.QUEUED, JobState.DEAD, JobState.CANCELLED}),
    JobState.SUCCEEDED: frozenset(),
    JobState.DEAD: frozenset({JobState.QUEUED}),
    JobState.CANCELLED: frozenset(),
}


# ---------------------------------------------------------------------------
# Milestone 3 — parser layer
# ---------------------------------------------------------------------------


class DeclarationKind(_StrEnum):
    """Syntactic category of a declaration found in a source file.

    Deliberately *not* the same vocabulary as Twin Spec section 3.2's ``Symbol``
    kind, even where the words coincide. A ``Symbol`` is a resolved entity with a
    moniker, a container and a binding; a declaration is a syntactic form observed
    at a span with no claim about what it refers to. Milestone 4 maps declarations
    onto symbols, and keeping the vocabularies separate is what stops that mapping
    from being assumed rather than performed.

    Every member is a form a parser can recognise from syntax alone. Nothing here
    requires knowing another file exists.
    """

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    ENUM_MEMBER = "enum_member"
    STRUCT = "struct"
    TRAIT = "trait"
    NAMESPACE = "namespace"
    MODULE = "module"
    TYPE_ALIAS = "type_alias"
    VARIABLE = "variable"
    CONSTANT = "constant"
    FIELD = "field"
    PROPERTY = "property"
    PARAMETER = "parameter"

    @property
    def is_callable(self) -> bool:
        """Whether the form introduces something invocable.

        Used by extractors to decide whether a parameter list is expected, and by
        Milestone 4 to decide which declarations can originate a call edge.
        """
        return self in (DeclarationKind.FUNCTION, DeclarationKind.METHOD)

    @property
    def is_type(self) -> bool:
        """Whether the form introduces a type."""
        return self in (
            DeclarationKind.CLASS,
            DeclarationKind.INTERFACE,
            DeclarationKind.ENUM,
            DeclarationKind.STRUCT,
            DeclarationKind.TRAIT,
            DeclarationKind.TYPE_ALIAS,
        )

    @property
    def is_container(self) -> bool:
        """Whether the form can lexically contain other declarations.

        A container's children are nested declarations, which is why extraction is a
        tree walk rather than a flat scan: a method exists only inside a class, and
        recording it without its container would lose the only structural
        information available without resolution.
        """
        return self in (
            DeclarationKind.CLASS,
            DeclarationKind.INTERFACE,
            DeclarationKind.ENUM,
            DeclarationKind.STRUCT,
            DeclarationKind.TRAIT,
            DeclarationKind.NAMESPACE,
            DeclarationKind.MODULE,
            DeclarationKind.FUNCTION,
            DeclarationKind.METHOD,
        )


class Visibility(_StrEnum):
    """Declared visibility of a declaration.

    ``INFERRED`` exists because most languages do not state visibility explicitly
    and instead rely on convention — a leading underscore in Python, a lowercase
    initial in Go. A convention-derived value is a weaker claim than a keyword, and
    conflating the two would let Milestone 4's API surface classification treat a
    guess as a declaration. Twin Spec section 3.2 gives ``Symbol`` an explicit
    ``visibility`` field; this is the syntactic input to it, not the conclusion.
    """

    PUBLIC = "public"
    PROTECTED = "protected"
    PRIVATE = "private"
    INTERNAL = "internal"
    PACKAGE = "package"
    #: No visibility keyword was present; the value was derived from a naming
    #: convention declared by the language plugin.
    INFERRED = "inferred"
    #: The language has no visibility concept for this form.
    NOT_APPLICABLE = "not_applicable"

    @property
    def is_explicit(self) -> bool:
        """Whether the value came from a keyword in the source.

        Consumers that must not act on a guess filter on this.
        """
        return self in (
            Visibility.PUBLIC,
            Visibility.PROTECTED,
            Visibility.PRIVATE,
            Visibility.INTERNAL,
            Visibility.PACKAGE,
        )


class DiagnosticSeverity(_StrEnum):
    """Severity of a diagnostic produced while parsing.

    A parser diagnostic is never fatal to a build. SDD section 3 (L2 failure modes)
    requires that a file with a syntax error yield whatever parsed, with the error
    recorded, because "one bad file must not fail a build". Severity therefore
    describes how much of the file is trustworthy, not whether to proceed.
    """

    #: The file parsed cleanly; the note is informational.
    INFO = "info"
    #: Part of the file did not parse. Extraction results are incomplete.
    WARNING = "warning"
    #: The file could not be parsed usefully at all.
    ERROR = "error"

    @property
    def degrades_coverage(self) -> bool:
        """Whether the diagnostic means the file's extraction is incomplete.

        Feeds the coverage self-report of Twin Spec section 9: a file that parsed
        partially must not be counted as fully understood.
        """
        return self in (DiagnosticSeverity.WARNING, DiagnosticSeverity.ERROR)


class ParserCapability(_StrEnum):
    """A syntactic capability a language plugin declares.

    Declared per language rather than assumed, because grammar coverage is uneven: a
    plugin may recognise functions and imports long before it recognises decorators.
    A consumer asks the capability registry what is available instead of discovering
    an empty result and guessing whether the language has no functions or the parser
    has no query for them — two situations that look identical in the output and
    mean opposite things.

    Every member is syntactic. There is deliberately no capability describing
    resolution, types, references or call edges: those belong to Milestone 4, and a
    capability enum that could express them would invite a plugin to claim them.
    """

    PARSE = "parse"
    PRODUCE_AST = "produce_ast"
    INCREMENTAL_PARSE = "incremental_parse"
    EXTRACT_FUNCTIONS = "extract_functions"
    EXTRACT_METHODS = "extract_methods"
    EXTRACT_CLASSES = "extract_classes"
    EXTRACT_INTERFACES = "extract_interfaces"
    EXTRACT_ENUMS = "extract_enums"
    EXTRACT_STRUCTS = "extract_structs"
    EXTRACT_NAMESPACES = "extract_namespaces"
    EXTRACT_TYPE_ALIASES = "extract_type_aliases"
    EXTRACT_VARIABLES = "extract_variables"
    EXTRACT_CONSTANTS = "extract_constants"
    EXTRACT_FIELDS = "extract_fields"
    EXTRACT_PROPERTIES = "extract_properties"
    EXTRACT_PARAMETERS = "extract_parameters"
    EXTRACT_IMPORTS = "extract_imports"
    EXTRACT_EXPORTS = "extract_exports"
    EXTRACT_ANNOTATIONS = "extract_annotations"
    EXTRACT_DECORATORS = "extract_decorators"
    EXTRACT_COMMENTS = "extract_comments"
    EXTRACT_DOCUMENTATION = "extract_documentation"
    EXTRACT_VISIBILITY = "extract_visibility"

    @property
    def is_extraction(self) -> bool:
        """Whether the capability concerns extraction rather than parsing."""
        return self.value.startswith("extract_")

    @property
    def declaration_kind(self) -> "Optional[DeclarationKind]":
        """The declaration kind this capability governs, if it governs one.

        Lets the capability registry answer "can this plugin find classes" from a
        :class:`DeclarationKind` without a second mapping table that could drift out
        of step with this enum.
        """
        return _CAPABILITY_DECLARATION_KINDS.get(self)


#: Capability to declaration kind, for the capabilities that govern one. Capabilities
#: describing parsing, comments, documentation or visibility are absent because they
#: govern no single kind.
_CAPABILITY_DECLARATION_KINDS: Mapping["ParserCapability", "DeclarationKind"] = {
    ParserCapability.EXTRACT_FUNCTIONS: DeclarationKind.FUNCTION,
    ParserCapability.EXTRACT_METHODS: DeclarationKind.METHOD,
    ParserCapability.EXTRACT_CLASSES: DeclarationKind.CLASS,
    ParserCapability.EXTRACT_INTERFACES: DeclarationKind.INTERFACE,
    ParserCapability.EXTRACT_ENUMS: DeclarationKind.ENUM,
    ParserCapability.EXTRACT_STRUCTS: DeclarationKind.STRUCT,
    ParserCapability.EXTRACT_NAMESPACES: DeclarationKind.NAMESPACE,
    ParserCapability.EXTRACT_TYPE_ALIASES: DeclarationKind.TYPE_ALIAS,
    ParserCapability.EXTRACT_VARIABLES: DeclarationKind.VARIABLE,
    ParserCapability.EXTRACT_CONSTANTS: DeclarationKind.CONSTANT,
    ParserCapability.EXTRACT_FIELDS: DeclarationKind.FIELD,
    ParserCapability.EXTRACT_PROPERTIES: DeclarationKind.PROPERTY,
    ParserCapability.EXTRACT_PARAMETERS: DeclarationKind.PARAMETER,
}

#: Capabilities every plugin must declare to be usable at all. A plugin that cannot
#: parse and cannot produce a tree has nothing to contribute, and admitting it would
#: put a permanently empty extractor in the registry.
MINIMUM_PARSER_CAPABILITIES: FrozenSet[ParserCapability] = frozenset(
    {ParserCapability.PARSE, ParserCapability.PRODUCE_AST}
)


# ---------------------------------------------------------------------------
# Milestone 4 — semantic resolution layer
# ---------------------------------------------------------------------------


class ScopeKind(_StrEnum):
    """Category of a lexical scope."""

    MODULE = "module"
    NAMESPACE = "namespace"
    PACKAGE = "package"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    STRUCT = "struct"
    FUNCTION = "function"
    METHOD = "method"
    LAMBDA = "lambda"
    BLOCK = "block"
    COMPREHENSION = "comprehension"

    @property
    def is_type_scope(self) -> bool:
        """Whether this scope introduces a type definition boundary."""
        return self in (
            ScopeKind.CLASS,
            ScopeKind.INTERFACE,
            ScopeKind.ENUM,
            ScopeKind.STRUCT,
        )

    @property
    def is_callable_scope(self) -> bool:
        """Whether this scope introduces a callable execution boundary."""
        return self in (ScopeKind.FUNCTION, ScopeKind.METHOD, ScopeKind.LAMBDA)


class ReferenceKind(_StrEnum):
    """Syntactic and semantic role of a symbol reference."""

    READ = "read"
    WRITE = "write"
    CALL = "call"
    IMPORT = "import"
    EXPORT = "export"
    INHERIT = "inherit"
    TYPE_USE = "type_use"
    UNKNOWN = "unknown"


class InheritanceKind(_StrEnum):
    """Form of inheritance or subtype relationship between types."""

    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    INHERITS = "inherits"
    MIXIN = "mixin"
    TRAIT = "trait"


class SemanticCapability(_StrEnum):
    """Capabilities provided by a semantic resolver."""

    RESOLVE_SCOPES = "resolve_scopes"
    RESOLVE_SYMBOLS = "resolve_symbols"
    RESOLVE_IMPORTS = "resolve_imports"
    RESOLVE_EXPORTS = "resolve_exports"
    RESOLVE_REFERENCES = "resolve_references"
    RESOLVE_CROSS_FILE = "resolve_cross_file"
    RESOLVE_INHERITANCE = "resolve_inheritance"


# ---------------------------------------------------------------------------
# Milestone 5 — repository knowledge graph
# ---------------------------------------------------------------------------


class NodeKind(_StrEnum):
    """Category of a graph node in the Repository Knowledge Graph."""

    REPOSITORY = "repository"
    COMMIT = "commit"
    BRANCH = "branch"
    MODULE = "module"
    NAMESPACE = "namespace"
    PACKAGE = "package"
    FILE = "file"
    CLASS = "class"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    FUNCTION = "function"
    METHOD = "method"
    FIELD = "field"
    VARIABLE = "variable"
    PARAMETER = "parameter"
    SYMBOL = "symbol"
    SCOPE = "scope"

    @property
    def is_type_node(self) -> bool:
        """Whether this node represents a type declaration."""
        return self in (
            NodeKind.CLASS,
            NodeKind.INTERFACE,
            NodeKind.STRUCT,
            NodeKind.ENUM,
        )

    @property
    def is_callable_node(self) -> bool:
        """Whether this node represents a callable symbol."""
        return self in (NodeKind.FUNCTION, NodeKind.METHOD)


class EdgeKind(_StrEnum):
    """Category of a directed graph edge in the Repository Knowledge Graph."""

    DECLARES = "declares"
    CONTAINS = "contains"
    OWNS = "owns"
    IMPORTS = "imports"
    EXPORTS = "exports"
    CALLS = "calls"
    REFERENCES = "references"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    OVERRIDES = "overrides"
    BELONGS_TO = "belongs_to"
    DEFINED_IN = "defined_in"
    USES = "uses"

    @property
    def is_hierarchy_edge(self) -> bool:
        """Whether this edge represents structural containment or ownership."""
        return self in (
            EdgeKind.CONTAINS,
            EdgeKind.OWNS,
            EdgeKind.DECLARES,
            EdgeKind.BELONGS_TO,
            EdgeKind.DEFINED_IN,
        )

    @property
    def is_type_relation(self) -> bool:
        """Whether this edge represents subtyping or inheritance."""
        return self in (
            EdgeKind.EXTENDS,
            EdgeKind.IMPLEMENTS,
            EdgeKind.OVERRIDES,
        )


# ---------------------------------------------------------------------------
# Milestone 6 — repository digital twin
# ---------------------------------------------------------------------------


class TwinState(_StrEnum):
    """Lifecycle state of a Repository Digital Twin."""

    INITIALIZING = "initializing"
    SYNCHRONIZED = "synchronized"
    DEGRADED = "degraded"
    OUT_OF_DATE = "out_of_date"
    STALE = "stale"
    ARCHIVED = "archived"


class RepositoryHealth(_StrEnum):
    """Health classification of a Repository Digital Twin."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
