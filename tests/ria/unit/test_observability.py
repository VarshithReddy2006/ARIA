"""Tests for the metrics sinks and the SQL statement splitter.

Both are small, pure components whose failures are disproportionately expensive.

A metrics sink that raises would turn an observability fault into an index-build
failure, which the port contract forbids. A statement splitter that is subtly wrong
corrupts a schema migration, and that defect is far cheaper to catch here than in a
deployment.
"""

from __future__ import annotations

import threading

import pytest

from ria.infrastructure.storage.sqlite.migrations import split_statements
from ria.observability.metrics import (
    Distribution,
    InMemoryMetricsSink,
    MetricKey,
    NullMetricsSink,
)
from ria.ports.metrics import MetricsSink


class TestMetricKey:
    """Series identity."""

    def test_label_order_does_not_change_identity(self) -> None:
        """The same labels supplied in a different order address one series.

        Without normalisation, two call sites emitting identical labels in different
        orders would produce two series and every aggregate would be halved.
        """
        first = MetricKey.of("m", {"a": "1", "b": "2"})
        second = MetricKey.of("m", {"b": "2", "a": "1"})
        assert first == second

    def test_absent_and_empty_labels_are_equivalent(self) -> None:
        """An empty mapping is the same series as no mapping."""
        assert MetricKey.of("m", None) == MetricKey.of("m", {})

    def test_label_values_are_coerced_to_strings(self) -> None:
        """Numeric label values do not create a distinct series from their text form."""
        assert MetricKey.of("m", {"n": 1}) == MetricKey.of("m", {"n": "1"})  # type: ignore[dict-item]

    def test_rendering_is_stable(self) -> None:
        """The rendered form is deterministic, which keeps failure output readable."""
        assert str(MetricKey.of("m", {"b": "2", "a": "1"})) == "m{a=1,b=2}"
        assert str(MetricKey.of("m", None)) == "m"


class TestDistribution:
    """Observation folding."""

    def test_accumulates_aggregates(self) -> None:
        """Count, total, minimum, maximum and mean track the observations."""
        distribution = Distribution()
        for value in (1.0, 3.0, 2.0):
            distribution.record(value)
        assert distribution.count == 3
        assert distribution.total == 6.0
        assert distribution.minimum == 1.0
        assert distribution.maximum == 3.0
        assert distribution.mean == 2.0

    def test_mean_is_none_before_any_observation(self) -> None:
        """An empty distribution has no mean rather than a zero."""
        assert Distribution().mean is None

    def test_retains_samples_up_to_the_limit_then_only_aggregates(self) -> None:
        """Memory is bounded while count and total stay exact.

        A long-running process must not accumulate unbounded samples, but its
        counters must remain correct, so the two are decoupled.
        """
        distribution = Distribution()
        for index in range(Distribution.RETENTION_LIMIT + 50):
            distribution.record(float(index))
        assert len(distribution.samples) == Distribution.RETENTION_LIMIT
        assert distribution.count == Distribution.RETENTION_LIMIT + 50


class TestInMemoryMetricsSink:
    """Behaviour of the default sink."""

    def test_satisfies_the_port(self) -> None:
        """The sink is structurally a :class:`~ria.ports.metrics.MetricsSink`."""
        assert isinstance(InMemoryMetricsSink(), MetricsSink)

    def test_counters_accumulate(self) -> None:
        """Increments add up per series."""
        sink = InMemoryMetricsSink()
        sink.increment("ria_test_total")
        sink.increment("ria_test_total", 4)
        assert sink.counter_value("ria_test_total") == 5

    def test_counters_are_separated_by_labels(self) -> None:
        """Distinct label sets are distinct series."""
        sink = InMemoryMetricsSink()
        sink.increment("ria_test_total", labels={"outcome": "ok"})
        sink.increment("ria_test_total", labels={"outcome": "error"})
        assert sink.counter_value("ria_test_total", {"outcome": "ok"}) == 1
        assert sink.counter_value("ria_test_total", {"outcome": "error"}) == 1

    def test_unknown_counter_reads_as_zero(self) -> None:
        """Reading an unrecorded counter does not raise."""
        assert InMemoryMetricsSink().counter_value("never_emitted") == 0

    def test_negative_increments_are_ignored_not_raised(self) -> None:
        """A counter cannot decrease, and a sink must never raise.

        Raising would let an observability mistake fail the work being observed.
        """
        sink = InMemoryMetricsSink()
        sink.increment("ria_test_total", -5)
        assert sink.counter_value("ria_test_total") == 0

    def test_gauges_replace_rather_than_accumulate(self) -> None:
        """A gauge records the latest value."""
        sink = InMemoryMetricsSink()
        sink.gauge("ria_test_gauge", 1.0)
        sink.gauge("ria_test_gauge", 7.5)
        assert sink.gauge_value("ria_test_gauge") == 7.5

    def test_unknown_gauge_reads_as_none(self) -> None:
        """An unrecorded gauge is absent, which is distinct from zero."""
        assert InMemoryMetricsSink().gauge_value("never_emitted") is None

    def test_observations_form_a_distribution(self) -> None:
        """Observations are folded into summary statistics."""
        sink = InMemoryMetricsSink()
        sink.observe("ria_test_seconds", 0.5)
        sink.observe("ria_test_seconds", 1.5)
        distribution = sink.distribution("ria_test_seconds")
        assert distribution is not None
        assert distribution.count == 2
        assert distribution.mean == 1.0

    def test_timer_records_a_success_outcome(self) -> None:
        """A completed block is labelled as a success."""
        sink = InMemoryMetricsSink()
        with sink.timer("ria_test_seconds", labels={"operation": "work"}):
            pass
        assert (
            sink.distribution(
                "ria_test_seconds", {"operation": "work", "outcome": "success"}
            )
            is not None
        )

    def test_timer_records_a_failure_outcome_and_reraises(self) -> None:
        """A raising block is still measured, and labelled as an error.

        Failure latency is often the interesting figure — a timeout looks nothing
        like a success — so it must not be discarded or merged with success.
        """
        sink = InMemoryMetricsSink()
        with pytest.raises(RuntimeError):
            with sink.timer("ria_test_seconds", labels={"operation": "work"}):
                raise RuntimeError("boom")
        assert (
            sink.distribution(
                "ria_test_seconds", {"operation": "work", "outcome": "error"}
            )
            is not None
        )
        assert (
            sink.distribution(
                "ria_test_seconds", {"operation": "work", "outcome": "success"}
            )
            is None
        )

    def test_timer_measures_a_non_negative_duration(self) -> None:
        """The observed duration is a real measurement."""
        sink = InMemoryMetricsSink()
        with sink.timer("ria_test_seconds"):
            pass
        distribution = sink.distribution("ria_test_seconds", {"outcome": "success"})
        assert distribution is not None
        assert distribution.minimum is not None
        assert distribution.minimum >= 0.0

    def test_snapshots_are_copies(self) -> None:
        """A snapshot cannot be used to mutate the sink."""
        sink = InMemoryMetricsSink()
        sink.increment("ria_test_total")
        snapshot = dict(sink.counters())
        snapshot.clear()
        assert sink.counter_value("ria_test_total") == 1

    def test_reset_discards_everything(self) -> None:
        """Reset clears counters, gauges and distributions."""
        sink = InMemoryMetricsSink()
        sink.increment("c")
        sink.gauge("g", 1.0)
        sink.observe("d", 1.0)
        sink.reset()
        assert sink.counters() == {}
        assert sink.gauges() == {}
        assert sink.distributions() == {}

    def test_is_thread_safe(self) -> None:
        """Concurrent increments do not lose updates.

        The ingestion worker pool of SDD section 6.3 emits from many threads, so a
        lost update here would silently understate throughput.
        """
        sink = InMemoryMetricsSink()
        iterations = 500

        def work() -> None:
            for _ in range(iterations):
                sink.increment("ria_concurrent_total")

        threads = [threading.Thread(target=work) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sink.counter_value("ria_concurrent_total") == iterations * 4


class TestNullMetricsSink:
    """Behaviour of the disabled sink."""

    def test_satisfies_the_port(self) -> None:
        """Disabling metrics substitutes a sink rather than adding conditionals."""
        assert isinstance(NullMetricsSink(), MetricsSink)

    def test_discards_every_measurement_without_raising(self) -> None:
        """Every operation is accepted and dropped."""
        sink = NullMetricsSink()
        sink.increment("c")
        sink.gauge("g", 1.0)
        sink.observe("d", 1.0)
        with sink.timer("t"):
            pass

    def test_timer_does_not_suppress_an_exception(self) -> None:
        """A null timer must not swallow a failure in the block it wraps."""
        with pytest.raises(RuntimeError):
            with NullMetricsSink().timer("t"):
                raise RuntimeError("boom")


class TestSplitStatements:
    """The SQL statement splitter used by the migration runner."""

    def test_splits_on_semicolons(self) -> None:
        """Statements are separated and stripped."""
        assert split_statements("SELECT 1; SELECT 2;") == ("SELECT 1", "SELECT 2")

    def test_ignores_a_trailing_separator(self) -> None:
        """A trailing semicolon does not produce an empty statement."""
        assert split_statements("SELECT 1;") == ("SELECT 1",)

    def test_accepts_a_final_statement_without_a_separator(self) -> None:
        """A script need not end with a semicolon."""
        assert split_statements("SELECT 1") == ("SELECT 1",)

    def test_ignores_empty_statements(self) -> None:
        """Consecutive separators and whitespace produce nothing."""
        assert split_statements(";;\n  \n;") == ()

    def test_does_not_split_inside_a_string_literal(self) -> None:
        """A semicolon inside a literal is data, not a separator.

        Splitting here would produce two syntactically invalid fragments and corrupt
        the migration.
        """
        assert split_statements("INSERT INTO t VALUES ('a;b');") == (
            "INSERT INTO t VALUES ('a;b')",
        )

    def test_handles_an_escaped_quote_inside_a_literal(self) -> None:
        """A doubled quote is SQLite's escape form and does not end the literal."""
        statements = split_statements("INSERT INTO t VALUES ('it''s; fine'); SELECT 1;")
        assert statements == ("INSERT INTO t VALUES ('it''s; fine')", "SELECT 1")

    def test_does_not_split_inside_a_line_comment(self) -> None:
        """A semicolon in a comment is not a separator."""
        statements = split_statements("-- a; comment\nSELECT 1;")
        assert len(statements) == 1
        assert statements[0].endswith("SELECT 1")

    def test_a_comment_ends_at_the_newline(self) -> None:
        """Statements after a comment are still recognised."""
        statements = split_statements("-- note\nSELECT 1;\n-- note\nSELECT 2;")
        assert len(statements) == 2

    def test_preserves_a_multi_line_statement(self) -> None:
        """A statement spanning lines is returned intact."""
        script = "CREATE TABLE t (\n  a TEXT,\n  b TEXT\n);"
        statements = split_statements(script)
        assert len(statements) == 1
        assert "b TEXT" in statements[0]

    def test_handles_the_real_migration_shape(self) -> None:
        """A script mixing comments, checks and indexes splits as expected."""
        script = """
        -- comment; with a semicolon
        CREATE TABLE t (
            a TEXT NOT NULL,
            CHECK (a <> 'x;y')
        );

        CREATE INDEX ix_t_a ON t (a);
        """
        statements = split_statements(script)
        assert len(statements) == 2
        assert statements[0].rstrip().endswith(")")
        assert statements[1].startswith("CREATE INDEX")
