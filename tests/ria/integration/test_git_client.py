"""Integration tests for the git client, against real repositories on disk.

SDD section 3 (L1) makes git the system of record: "we never own the truth". These
tests therefore pin the adapter against the reference implementation rather than
against a mock, because the operations that matter — recursive tree listing, tag
peeling, binary detection — are exactly where pure-Python git libraries diverge, and
a divergence there yields a silently wrong index rather than an error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ria.config.settings import GitSettings
from ria.domain.errors import GitCommandError, GitUnavailableError, RefNotFoundError
from ria.infrastructure.git.subprocess_git_client import SubprocessGitClient
from ria.observability.metrics import InMemoryMetricsSink
from ria.ports.git_client import GitClient
from tests.ria.conftest import commit_files, head_sha, requires_git, run_git

pytestmark = requires_git


class TestPortConformance:
    """Structural conformance and availability reporting."""

    def test_satisfies_the_port(self, git_client: SubprocessGitClient) -> None:
        """The adapter is structurally a :class:`GitClient`."""
        assert isinstance(git_client, GitClient)

    def test_reports_the_executable_version(
        self, git_client: SubprocessGitClient
    ) -> None:
        """Version is parsed into components and retains the raw string.

        Provenance records the version because git's rename detection and tree
        listing have changed across releases, and a reproducibility investigation
        needs to know which produced an observation.
        """
        version = git_client.version()
        assert version.major >= 2
        assert "git version" in version.raw

    def test_version_is_cached(self, git_client: SubprocessGitClient) -> None:
        """Version is invoked once, since it is a constant for the process."""
        first = git_client.version()
        second = git_client.version()
        assert first is second

    def test_reports_a_missing_executable(self, metrics: InMemoryMetricsSink) -> None:
        """An absent git binary fails fast with an actionable error."""
        client = SubprocessGitClient(
            GitSettings(executable="git-that-does-not-exist"), metrics
        )
        with pytest.raises(GitUnavailableError):
            client.version()


class TestRefResolution:
    """Resolving ref expressions to full object names."""

    def test_resolves_a_branch(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A branch name resolves to its head commit."""
        repository = make_git_repo()
        assert git_client.resolve_ref(repository, "main") == head_sha(repository)

    def test_resolves_head(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """``HEAD`` resolves like any other expression."""
        repository = make_git_repo()
        assert git_client.resolve_ref(repository, "HEAD") == head_sha(repository)

    def test_expands_an_abbreviated_sha(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """An abbreviation is expanded, so no ambiguous identity enters the domain."""
        repository = make_git_repo()
        full = head_sha(repository)
        assert git_client.resolve_ref(repository, full[:8]) == full

    def test_resolves_a_full_sha_to_itself(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A complete object name is idempotent under resolution."""
        repository = make_git_repo()
        full = head_sha(repository)
        assert git_client.resolve_ref(repository, full) == full

    def test_peels_a_lightweight_tag(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A tag resolves to the commit it names."""
        repository = make_git_repo()
        run_git(repository, "tag", "v1.0.0")
        assert git_client.resolve_ref(repository, "v1.0.0") == head_sha(repository)

    def test_peels_an_annotated_tag_to_its_commit(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """An annotated tag resolves to a commit, not to the tag object.

        Without the commit peel, the returned object name would not be a commit and
        every downstream query would fail confusingly.
        """
        repository = make_git_repo()
        run_git(repository, "tag", "-a", "v2.0.0", "-m", "release")
        resolved = git_client.resolve_ref(repository, "v2.0.0")
        assert resolved == head_sha(repository)
        assert resolved != run_git(repository, "rev-parse", "v2.0.0")

    def test_resolves_a_relative_expression(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Any expression git accepts is accepted here."""
        repository = make_git_repo()
        first = head_sha(repository)
        commit_files(repository, {"src/a.py": "x = 1\n"}, "second")
        assert git_client.resolve_ref(repository, "HEAD~1") == first

    def test_raises_for_an_unknown_ref(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """An unresolvable ref raises a typed error carrying git's stderr."""
        repository = make_git_repo()
        with pytest.raises(RefNotFoundError) as caught:
            git_client.resolve_ref(repository, "no-such-branch")
        assert caught.value.context["ref"] == "no-such-branch"

    @pytest.mark.parametrize("ref", ["", "   "])
    def test_rejects_an_empty_ref(
        self, git_client: SubprocessGitClient, make_git_repo, ref: str
    ) -> None:
        """An empty expression is refused without invoking git."""
        repository = make_git_repo()
        with pytest.raises(RefNotFoundError):
            git_client.resolve_ref(repository, ref)

    def test_a_ref_beginning_with_a_hyphen_is_not_an_option(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A hostile ref name cannot become a git option.

        ``--end-of-options`` is what makes this safe; without it a crafted ref could
        change the meaning of the command.
        """
        repository = make_git_repo()
        with pytest.raises(RefNotFoundError):
            git_client.resolve_ref(repository, "--upload-pack=touch /tmp/x")


class TestCommitReading:
    """Reading commit metadata."""

    def test_reads_a_root_commit(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A first commit has no parents and a resolvable tree."""
        repository = make_git_repo()
        commit = git_client.read_commit(repository, head_sha(repository))
        assert commit.sha == head_sha(repository)
        assert commit.parent_shas == ()
        assert commit.tree_sha

    def test_reads_signatures_and_timestamps(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Author and committer signatures are read with aware UTC timestamps.

        Naive timestamps would silently corrupt every duration computed from them,
        and durations drive staleness and retention.
        """
        repository = make_git_repo()
        commit = git_client.read_commit(repository, head_sha(repository))
        assert commit.author.name == "Ada Lovelace"
        assert commit.author.email == "ada@example.com"
        assert commit.author.timestamp.tzinfo is not None
        assert commit.author.timestamp.utcoffset().total_seconds() == 0

    def test_preserves_a_multi_line_message(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A message body survives intact.

        The unit-separator format exists for this: a newline-delimited format would
        truncate every commit that has a body.
        """
        repository = make_git_repo()
        run_git(
            repository,
            "commit",
            "--allow-empty",
            "--quiet",
            "-m",
            "subject\n\nbody line",
        )
        commit = git_client.read_commit(repository, head_sha(repository))
        assert commit.message.startswith("subject")
        assert "body line" in commit.message

    def test_preserves_a_message_containing_a_tab(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A tab in a message is data, not a field separator."""
        repository = make_git_repo()
        run_git(repository, "commit", "--allow-empty", "--quiet", "-m", "a\tb")
        commit = git_client.read_commit(repository, head_sha(repository))
        assert "\t" in commit.message

    def test_reads_a_linear_parent(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A subsequent commit records its single parent."""
        repository = make_git_repo()
        first = head_sha(repository)
        second = commit_files(repository, {"src/a.py": "x = 1\n"}, "second")
        commit = git_client.read_commit(repository, second)
        assert commit.parent_shas == (first,)

    def test_reads_every_parent_of_a_merge(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Merge parents are reported in git order, which defines the mainline."""
        repository = make_git_repo()
        base = head_sha(repository)
        run_git(repository, "checkout", "--quiet", "-b", "feature")
        feature = commit_files(repository, {"src/f.py": "f = 1\n"}, "feature work")
        run_git(repository, "checkout", "--quiet", "main")
        mainline = commit_files(repository, {"src/m.py": "m = 1\n"}, "main work")
        run_git(
            repository, "merge", "--no-ff", "--quiet", "-m", "merge feature", "feature"
        )

        commit = git_client.read_commit(repository, head_sha(repository))
        assert commit.parent_shas == (mainline, feature)
        assert base not in commit.parent_shas

    def test_raises_for_an_unknown_commit(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A missing object raises rather than returning an empty record."""
        repository = make_git_repo()
        with pytest.raises(RefNotFoundError):
            git_client.read_commit(repository, "0" * 40)


class TestBranchEnumeration:
    """Listing branches and identifying the default."""

    def test_lists_local_branches(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Every local branch is reported with its head pointer."""
        repository = make_git_repo()
        run_git(repository, "branch", "feature/x")
        names = {branch.name for branch in git_client.list_branches(repository)}
        assert names == {"main", "feature/x"}

    def test_flags_the_default_branch(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Exactly one branch is flagged as the default."""
        repository = make_git_repo()
        run_git(repository, "branch", "feature/x")
        defaults = [
            branch.name
            for branch in git_client.list_branches(repository)
            if branch.is_default
        ]
        assert defaults == ["main"]

    def test_reports_branch_heads_and_timestamps(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Head pointers and commit times support staleness decisions."""
        repository = make_git_repo()
        branches = {
            branch.name: branch for branch in git_client.list_branches(repository)
        }
        assert branches["main"].head_sha == head_sha(repository)
        assert branches["main"].last_commit_at is not None
        assert branches["main"].last_commit_at.tzinfo is not None

    def test_handles_a_slash_in_a_branch_name(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A namespaced branch name is reported without its ref prefix."""
        repository = make_git_repo()
        run_git(repository, "branch", "release/2026.1")
        names = {branch.name for branch in git_client.list_branches(repository)}
        assert "release/2026.1" in names

    def test_detects_the_default_branch(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """The default branch is derived from ``HEAD`` when no remote is configured."""
        repository = make_git_repo(default_branch="trunk")
        assert git_client.detect_default_branch(repository) == "trunk"

    def test_default_detection_prefers_the_remote_advertisement(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A configured remote head outranks the local symbolic ref.

        The remote is the more authoritative statement of what the repository's
        default branch is; the local checkout may simply be on another branch.
        """
        repository = make_git_repo()
        run_git(repository, "branch", "release")
        run_git(repository, "remote", "add", "origin", str(repository))
        run_git(
            repository,
            "symbolic-ref",
            "refs/remotes/origin/HEAD",
            "refs/heads/release",
        )
        assert git_client.detect_default_branch(repository) == "release"


class TestTreeListing:
    """Recursive listing of a commit's blobs."""

    def test_lists_every_blob_recursively(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Nested files are reported with repository-relative forward-slash paths."""
        repository = make_git_repo(
            files={
                "README.md": "# fixture\n",
                "src/a.py": "a = 1\n",
                "src/deep/b.py": "b = 2\n",
            }
        )
        paths = {
            entry.path
            for entry in git_client.list_tree(repository, head_sha(repository))
        }
        assert paths == {"README.md", "src/a.py", "src/deep/b.py"}

    def test_reports_blob_sizes_and_object_names(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Sizes come from the listing, so no extra invocation is needed to learn them.

        This is what lets the ingestion pipeline enforce ``max_blob_bytes`` without
        a separate size probe per file.
        """
        repository = make_git_repo(files={"src/a.py": "a = 1\n"})
        entry = git_client.list_tree(repository, head_sha(repository))[0]
        assert entry.size_bytes == len("a = 1\n")
        assert len(entry.blob_sha) in (40, 64)

    def test_excludes_directories(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Only blobs are returned; a tree carries no content."""
        repository = make_git_repo(files={"src/deep/b.py": "b = 2\n"})
        entries = git_client.list_tree(repository, head_sha(repository))
        assert [entry.path for entry in entries] == ["src/deep/b.py"]

    def test_reports_the_executable_bit(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """File mode is preserved, which distinguishes scripts and symlinks."""
        repository = make_git_repo(files={"run.sh": "#!/bin/sh\necho hi\n"})
        run_git(repository, "update-index", "--chmod=+x", "run.sh")
        run_git(repository, "commit", "--quiet", "-m", "make executable")
        entry = git_client.list_tree(repository, head_sha(repository))[0]
        assert entry.is_executable is True
        assert entry.is_symlink is False

    def test_lists_a_historical_commit(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A tree is readable at any commit, which is what commit addressing needs."""
        repository = make_git_repo(files={"README.md": "# fixture\n"})
        first = head_sha(repository)
        commit_files(repository, {"src/added.py": "x = 1\n"}, "add a file")
        historical = {entry.path for entry in git_client.list_tree(repository, first)}
        current = {
            entry.path
            for entry in git_client.list_tree(repository, head_sha(repository))
        }
        assert historical == {"README.md"}
        assert current == {"README.md", "src/added.py"}

    def test_handles_a_path_containing_a_space(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A space in a path is not a field separator.

        NUL-delimited output is what makes this safe; a line- or space-oriented
        parse would split one path into two entries.
        """
        repository = make_git_repo(files={"docs/design notes.md": "notes\n"})
        paths = {
            entry.path
            for entry in git_client.list_tree(repository, head_sha(repository))
        }
        assert "docs/design notes.md" in paths

    def test_raises_for_an_unknown_commit(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Listing a missing commit raises rather than returning an empty tree.

        An empty tree would be indistinguishable from a real empty commit and would
        silently produce a manifest describing no files.
        """
        repository = make_git_repo()
        with pytest.raises(RefNotFoundError):
            git_client.list_tree(repository, "0" * 40)


class TestBlobReading:
    """Reading blob content."""

    def test_reads_exact_bytes(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Content round-trips byte for byte, including line endings.

        Any normalisation would change the content hash and break parse reuse.
        """
        payload = "def handler():\n    return 200\n"
        repository = make_git_repo(files={"src/a.py": payload})
        entry = git_client.list_tree(repository, head_sha(repository))[0]
        assert git_client.read_blob(repository, entry.blob_sha) == payload.encode()

    def test_reads_binary_content(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """Binary content is returned unaltered."""
        payload = bytes([0, 1, 2, 253, 254, 255])
        repository = make_git_repo(files={"logo.png": payload})
        entry = git_client.list_tree(repository, head_sha(repository))[0]
        assert git_client.read_blob(repository, entry.blob_sha) == payload

    def test_raises_for_an_unknown_blob(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """A missing object raises a typed error."""
        repository = make_git_repo()
        with pytest.raises(GitCommandError):
            git_client.read_blob(repository, "0" * 40)


class TestLineCounting:
    """Git's own binary heuristic and line counting."""

    @pytest.mark.parametrize(
        "data,expected",
        [
            (b"", 0),
            (b"one\n", 1),
            (b"one\ntwo\n", 2),
            (b"one\ntwo", 2),
            (b"\n", 1),
            (b"\n\n", 2),
        ],
    )
    def test_counts_lines(
        self, git_client: SubprocessGitClient, data: bytes, expected: int
    ) -> None:
        """A final line without a trailing newline counts, matching an editor's view."""
        assert git_client.count_lines(data) == expected

    def test_reports_none_for_binary_content(
        self, git_client: SubprocessGitClient
    ) -> None:
        """Binary content has no line count, which is distinct from zero."""
        assert git_client.count_lines(b"text\x00more") is None

    def test_applies_the_heuristic_within_the_first_block(
        self, git_client: SubprocessGitClient
    ) -> None:
        """Git inspects only the leading bytes, and so does this.

        Reusing git's definition avoids a second, divergent notion of "binary"
        appearing in the system.
        """
        late_nul = b"a" * 9000 + b"\x00"
        assert git_client.count_lines(late_nul) is not None
        early_nul = b"a" * 100 + b"\x00" + b"a" * 9000
        assert git_client.count_lines(early_nul) is None


class TestObservability:
    """Metrics emitted by the adapter."""

    def test_counts_and_times_each_operation(
        self,
        git_client: SubprocessGitClient,
        make_git_repo,
        metrics: InMemoryMetricsSink,
    ) -> None:
        """Every invocation is counted and timed under its logical operation."""
        repository = make_git_repo()
        git_client.resolve_ref(repository, "main")
        assert (
            metrics.counter_value("ria_git_command_total", {"operation": "resolve_ref"})
            == 1
        )
        assert (
            metrics.distribution(
                "ria_git_command_seconds",
                {"operation": "resolve_ref", "outcome": "success"},
            )
            is not None
        )

    def test_counts_failures_with_a_reason(
        self,
        git_client: SubprocessGitClient,
        make_git_repo,
        metrics: InMemoryMetricsSink,
    ) -> None:
        """A failed invocation is distinguishable from a successful one."""
        repository = make_git_repo()
        with pytest.raises(RefNotFoundError):
            git_client.resolve_ref(repository, "no-such-branch")
        assert (
            metrics.counter_value(
                "ria_git_command_failures_total",
                {"operation": "resolve_ref", "reason": "exit_code"},
            )
            == 1
        )


class TestStatelessness:
    """One instance serving many repositories."""

    def test_one_client_serves_several_repositories(
        self, git_client: SubprocessGitClient, make_git_repo
    ) -> None:
        """The adapter holds no per-repository state.

        Holding any would prevent one process from serving many repositories, which
        is the deployment shape of SDD section 6.3.
        """
        first = make_git_repo("alpha", files={"a.py": "a = 1\n"})
        second = make_git_repo("beta", files={"b.py": "b = 2\n"})
        assert git_client.resolve_ref(first, "main") != git_client.resolve_ref(
            second, "main"
        )
        assert {
            entry.path for entry in git_client.list_tree(first, head_sha(first))
        } == {"a.py"}

    def test_rejects_a_path_that_is_not_a_repository(
        self, git_client: SubprocessGitClient, tmp_path: Path
    ) -> None:
        """A non-repository path fails rather than being treated as empty."""
        directory = tmp_path / "not-a-repo"
        directory.mkdir()
        with pytest.raises(RefNotFoundError):
            git_client.resolve_ref(directory, "main")
