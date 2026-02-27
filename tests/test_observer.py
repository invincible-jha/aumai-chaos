"""Tests for aumai_chaos.observer — ExperimentObserver."""

from __future__ import annotations

import pytest

from aumai_chaos.core import ChaosError
from aumai_chaos.models import ObservationPoint
from aumai_chaos.observer import ExperimentObserver

# ---------------------------------------------------------------------------
# Basic observe / get_observations / clear
# ---------------------------------------------------------------------------


class TestObserve:
    def test_observe_adds_entry(self, observer: ExperimentObserver) -> None:
        observer.observe("llm", "call_started")
        points = observer.get_observations()
        assert len(points) == 1

    def test_observation_fields_correct(self, observer: ExperimentObserver) -> None:
        observer.observe("db", "query_start", {"sql": "SELECT 1"})
        point = observer.get_observations()[0]
        assert point.component == "db"
        assert point.event == "query_start"
        assert point.details["sql"] == "SELECT 1"

    def test_timestamp_is_utc_aware(self, observer: ExperimentObserver) -> None:
        observer.observe("net", "timeout")
        point = observer.get_observations()[0]
        assert point.timestamp.tzinfo is not None

    def test_multiple_observations_ordered(self, observer: ExperimentObserver) -> None:
        for i in range(5):
            observer.observe("comp", f"event_{i}")
        points = observer.get_observations()
        assert len(points) == 5
        events = [p.event for p in points]
        assert events == [f"event_{i}" for i in range(5)]

    def test_details_defaults_to_empty_dict(self, observer: ExperimentObserver) -> None:
        observer.observe("x", "y")
        assert observer.get_observations()[0].details == {}

    def test_details_none_becomes_empty_dict(
        self, observer: ExperimentObserver
    ) -> None:
        observer.observe("x", "y", None)
        assert observer.get_observations()[0].details == {}


class TestGetObservations:
    def test_returns_list_of_observation_points(
        self, observer: ExperimentObserver
    ) -> None:
        observer.observe("a", "b")
        result = observer.get_observations()
        assert isinstance(result, list)
        assert isinstance(result[0], ObservationPoint)

    def test_returns_shallow_copy(self, observer: ExperimentObserver) -> None:
        observer.observe("a", "b")
        first_call = observer.get_observations()
        second_call = observer.get_observations()
        # Different list objects
        assert first_call is not second_call
        # But same content
        assert first_call[0] == second_call[0]

    def test_mutation_of_returned_list_does_not_affect_internal_state(
        self, observer: ExperimentObserver
    ) -> None:
        observer.observe("a", "b")
        copy = observer.get_observations()
        copy.clear()
        # Internal state unchanged
        assert len(observer.get_observations()) == 1

    def test_empty_when_no_observations(self, observer: ExperimentObserver) -> None:
        assert observer.get_observations() == []


class TestClear:
    def test_clear_removes_all_observations(self, observer: ExperimentObserver) -> None:
        observer.observe("x", "y")
        observer.observe("a", "b")
        observer.clear()
        assert observer.get_observations() == []

    def test_clear_on_empty_observer_is_noop(
        self, observer: ExperimentObserver
    ) -> None:
        observer.clear()  # Should not raise
        assert observer.get_observations() == []

    def test_observe_after_clear_works(self, observer: ExperimentObserver) -> None:
        observer.observe("x", "y")
        observer.clear()
        observer.observe("new", "event")
        points = observer.get_observations()
        assert len(points) == 1
        assert points[0].component == "new"


# ---------------------------------------------------------------------------
# scope context manager
# ---------------------------------------------------------------------------


class TestScope:
    def test_scope_records_start_and_end(self, observer: ExperimentObserver) -> None:
        with observer.scope("database", "query"):
            pass
        events = [p.event for p in observer.get_observations()]
        assert "query_start" in events
        assert "query_end" in events

    def test_scope_records_start_and_error_on_exception(
        self, observer: ExperimentObserver
    ) -> None:
        with pytest.raises(ValueError):
            with observer.scope("cache", "lookup"):
                raise ValueError("cache miss")
        events = [p.event for p in observer.get_observations()]
        assert "lookup_start" in events
        assert "lookup_error" in events
        assert "lookup_end" not in events

    def test_scope_error_observation_contains_exception_details(
        self, observer: ExperimentObserver
    ) -> None:
        with pytest.raises(RuntimeError):
            with observer.scope("net", "fetch"):
                raise RuntimeError("network down")
        error_point = next(
            p for p in observer.get_observations() if "error" in p.event
        )
        assert error_point.details["exception_type"] == "RuntimeError"
        assert "network down" in error_point.details["message"]  # type: ignore[operator]

    def test_scope_reraises_exception(self, observer: ExperimentObserver) -> None:
        original = ChaosError(503, "chaos")
        with pytest.raises(ChaosError) as exc_info:
            with observer.scope("svc", "call"):
                raise original
        assert exc_info.value is original

    def test_scope_without_event_prefix(self, observer: ExperimentObserver) -> None:
        with observer.scope("svc"):
            pass
        events = [p.event for p in observer.get_observations()]
        assert "start" in events
        assert "end" in events

    def test_scope_component_recorded_correctly(
        self, observer: ExperimentObserver
    ) -> None:
        with observer.scope("my_component", "op"):
            pass
        for point in observer.get_observations():
            assert point.component == "my_component"

    def test_nested_scopes_accumulate_observations(
        self, observer: ExperimentObserver
    ) -> None:
        with observer.scope("outer", "outer_op"):
            with observer.scope("inner", "inner_op"):
                pass
        points = observer.get_observations()
        # 2 from outer (start, end), 2 from inner (start, end) — inner fires first end
        assert len(points) == 4

    def test_scope_yields_none(self, observer: ExperimentObserver) -> None:
        with observer.scope("x", "op") as value:
            assert value is None


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_observe_does_not_corrupt_state(self) -> None:
        """Many threads appending observations concurrently must not drop or
        corrupt entries — verifying the threading.Lock protects the list."""
        import threading

        observer = ExperimentObserver()
        n_threads = 50
        observations_per_thread = 20

        def append_observations() -> None:
            for i in range(observations_per_thread):
                observer.observe("thread", f"event_{i}")

        threads = [threading.Thread(target=append_observations) for _ in range(n_threads)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        points = observer.get_observations()
        assert len(points) == n_threads * observations_per_thread

    def test_get_observations_during_concurrent_writes_returns_snapshot(self) -> None:
        """get_observations() must return a consistent snapshot even while
        another thread is appending — no RuntimeError from list mutation."""
        import threading

        observer = ExperimentObserver()
        stop_event = threading.Event()
        errors: list[Exception] = []

        def writer() -> None:
            while not stop_event.is_set():
                observer.observe("writer", "tick")

        def reader() -> None:
            for _ in range(200):
                try:
                    snapshot = observer.get_observations()
                    assert isinstance(snapshot, list)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

        writer_thread = threading.Thread(target=writer, daemon=True)
        reader_thread = threading.Thread(target=reader)
        writer_thread.start()
        reader_thread.start()
        reader_thread.join(timeout=5.0)
        stop_event.set()
        writer_thread.join(timeout=1.0)

        assert errors == [], f"Reader thread raised during concurrent write: {errors}"
