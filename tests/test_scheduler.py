"""Tests for aumai_chaos.scheduler — ExperimentScheduler."""

from __future__ import annotations

import threading
import time
from unittest.mock import patch

import pytest

from aumai_chaos.models import (
    ChaosExperiment,
    ExperimentStatus,
    FaultConfig,
    FaultType,
)
from aumai_chaos.scheduler import ExperimentNotFoundError, ExperimentScheduler

# ---------------------------------------------------------------------------
# ExperimentNotFoundError
# ---------------------------------------------------------------------------


class TestExperimentNotFoundError:
    def test_is_subclass_of_key_error(self) -> None:
        assert issubclass(ExperimentNotFoundError, KeyError)

    def test_raised_with_missing_id(self) -> None:
        with pytest.raises(ExperimentNotFoundError):
            raise ExperimentNotFoundError("missing-id")


# ---------------------------------------------------------------------------
# ExperimentScheduler.schedule
# ---------------------------------------------------------------------------


class TestSchedule:
    def test_schedule_returns_experiment_id(
        self, scheduler: ExperimentScheduler
    ) -> None:
        experiment = ChaosExperiment(
            experiment_id="test-id", name="Test", duration_seconds=1
        )
        returned_id = scheduler.schedule(experiment)
        assert returned_id == "test-id"

    def test_schedule_preserves_existing_id(
        self, scheduler: ExperimentScheduler
    ) -> None:
        experiment = ChaosExperiment(
            experiment_id="my-fixed-id", name="Fixed", duration_seconds=1
        )
        assert scheduler.schedule(experiment) == "my-fixed-id"

    def test_schedule_multiple_experiments(
        self, scheduler: ExperimentScheduler
    ) -> None:
        ids = []
        for i in range(3):
            exp = ChaosExperiment(
                experiment_id=f"exp-{i}", name=f"Exp {i}", duration_seconds=1
            )
            ids.append(scheduler.schedule(exp))
        assert ids == ["exp-0", "exp-1", "exp-2"]

    def test_schedule_same_id_twice_overwrites(
        self, scheduler: ExperimentScheduler
    ) -> None:
        exp1 = ChaosExperiment(experiment_id="dup", name="First", duration_seconds=1)
        exp2 = ChaosExperiment(experiment_id="dup", name="Second", duration_seconds=2)
        scheduler.schedule(exp1)
        scheduler.schedule(exp2)
        # Run the second one — it should have duration=2 (meaning at least 2 ticks)
        # We just verify it does not raise
        with patch.object(scheduler, "_injector") as mock_injector:
            mock_injector.inject = lambda c: None  # no-op

            def run_briefly() -> None:
                # abort immediately after scheduling
                threading.Timer(
                    0.1, lambda: scheduler.abort("dup")
                ).start()
                scheduler.run("dup")

            run_briefly()


# ---------------------------------------------------------------------------
# ExperimentScheduler.run
# ---------------------------------------------------------------------------


class TestRun:
    def test_run_unknown_id_raises(self, scheduler: ExperimentScheduler) -> None:
        with pytest.raises(ExperimentNotFoundError):
            scheduler.run("does-not-exist")

    def test_run_returns_experiment_result(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        assert result.experiment.experiment_id == minimal_experiment.experiment_id

    def test_run_completes_with_completed_status(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        assert result.status == ExperimentStatus.completed

    def test_run_sets_start_time(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        assert result.start_time is not None

    def test_run_sets_end_time(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        assert result.end_time is not None

    def test_run_end_time_after_start_time(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        assert result.end_time >= result.start_time  # type: ignore[operator]

    def test_run_includes_observations(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        # At minimum: experiment_started and experiment_ended
        assert len(result.observations) >= 2

    def test_run_summary_contains_required_keys(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        assert "total_faults_fired" in result.summary
        assert "faults_by_type" in result.summary
        assert "errors_by_type" in result.summary
        assert "duration_seconds" in result.summary

    def test_run_fault_errors_counted_in_summary(
        self,
        scheduler: ExperimentScheduler,
        error_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(error_experiment)
        result = scheduler.run(error_experiment.experiment_id)
        # error faults with probability=1 should fire and raise
        errors_by_type: dict[str, int] = (
            result.summary["errors_by_type"]  # type: ignore[assignment]
        )
        assert errors_by_type.get("error", 0) >= 1

    def test_run_observations_include_experiment_started(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        events = [o.event for o in result.observations]
        assert "experiment_started" in events

    def test_run_observations_include_experiment_ended(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        events = [o.event for o in result.observations]
        assert "experiment_ended" in events

    def test_run_result_stored_and_retrievable(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        result = scheduler.run(minimal_experiment.experiment_id)
        retrieved = scheduler.get_result(minimal_experiment.experiment_id)
        assert retrieved is not None
        assert retrieved.status == result.status


# ---------------------------------------------------------------------------
# ExperimentScheduler.abort
# ---------------------------------------------------------------------------


class TestAbort:
    def test_abort_unknown_id_raises(self, scheduler: ExperimentScheduler) -> None:
        with pytest.raises(ExperimentNotFoundError):
            scheduler.abort("no-such-id")

    def test_abort_signals_running_experiment(self) -> None:
        """Aborting mid-run should yield status=aborted."""
        scheduler = ExperimentScheduler()
        experiment = ChaosExperiment(
            experiment_id="abort-test",
            name="Long Experiment",
            faults=[],
            duration_seconds=60,  # would run for 60s without abort
        )
        scheduler.schedule(experiment)

        result_holder: list[object] = []

        def run_experiment() -> None:
            result_holder.append(scheduler.run("abort-test"))

        thread = threading.Thread(target=run_experiment, daemon=True)
        thread.start()

        # Give the experiment time to start its first tick
        time.sleep(0.2)
        scheduler.abort("abort-test")
        thread.join(timeout=5.0)

        assert not thread.is_alive(), "Thread did not finish after abort"
        assert len(result_holder) == 1
        result = result_holder[0]
        from aumai_chaos.models import ExperimentResult
        assert isinstance(result, ExperimentResult)
        assert result.status == ExperimentStatus.aborted

    def test_abort_before_run_does_not_raise(
        self, scheduler: ExperimentScheduler
    ) -> None:
        experiment = ChaosExperiment(
            experiment_id="pre-abort",
            name="Pre-abort",
            faults=[],
            duration_seconds=1,
        )
        scheduler.schedule(experiment)
        # Abort before run — should not raise
        scheduler.abort("pre-abort")


# ---------------------------------------------------------------------------
# ExperimentScheduler.get_result
# ---------------------------------------------------------------------------


class TestGetResult:
    def test_get_result_returns_none_for_unrun_experiment(
        self, scheduler: ExperimentScheduler
    ) -> None:
        experiment = ChaosExperiment(
            experiment_id="unrun", name="Unrun", duration_seconds=1
        )
        scheduler.schedule(experiment)
        assert scheduler.get_result("unrun") is None

    def test_get_result_returns_none_for_unknown_id(
        self, scheduler: ExperimentScheduler
    ) -> None:
        assert scheduler.get_result("totally-unknown") is None

    def test_get_result_after_run_contains_experiment(
        self,
        scheduler: ExperimentScheduler,
        minimal_experiment: ChaosExperiment,
    ) -> None:
        scheduler.schedule(minimal_experiment)
        scheduler.run(minimal_experiment.experiment_id)
        result = scheduler.get_result(minimal_experiment.experiment_id)
        assert result is not None
        assert result.experiment.name == minimal_experiment.name


# ---------------------------------------------------------------------------
# Fault injection integration — latency fault via scheduler
# ---------------------------------------------------------------------------


class TestSchedulerLatencyIntegration:
    def test_latency_fault_fired_and_observation_recorded(self) -> None:
        scheduler = ExperimentScheduler()
        experiment = ChaosExperiment(
            experiment_id="lat-test",
            name="Latency Experiment",
            faults=[
                FaultConfig(
                    fault_type=FaultType.latency,
                    probability=1.0,
                    duration_ms=10,
                    affected_components=["agent"],
                )
            ],
            duration_seconds=1,
        )
        scheduler.schedule(experiment)
        result = scheduler.run("lat-test")

        # Check at least one latency_injected observation
        events = [o.event for o in result.observations]
        assert "latency_injected" in events

    def test_fault_counts_incremented_for_latency(self) -> None:
        scheduler = ExperimentScheduler()
        experiment = ChaosExperiment(
            experiment_id="lat-count",
            name="Latency Count",
            faults=[
                FaultConfig(
                    fault_type=FaultType.latency,
                    probability=1.0,
                    duration_ms=10,
                    affected_components=["svc"],
                )
            ],
            duration_seconds=1,
        )
        scheduler.schedule(experiment)
        result = scheduler.run("lat-count")
        faults_by_type: dict[str, int] = result.summary["faults_by_type"]  # type: ignore[assignment]
        assert faults_by_type.get("latency", 0) >= 1
        total: int = result.summary["total_faults_fired"]  # type: ignore[assignment]
        assert total >= 1


# ---------------------------------------------------------------------------
# Concurrent run isolation — CH-2 regression test
# ---------------------------------------------------------------------------


class TestConcurrentRunIsolation:
    def test_concurrent_runs_have_isolated_observations(self) -> None:
        """Two experiments running concurrently must not share observation
        state.  Before the fix, the single shared _observer was cleared at the
        start of each run(), causing one experiment to erase the other's data."""
        import threading

        scheduler = ExperimentScheduler()

        # Two short experiments with no faults so they complete quickly.
        exp_a = ChaosExperiment(
            experiment_id="concurrent-a",
            name="Concurrent A",
            faults=[],
            duration_seconds=2,
        )
        exp_b = ChaosExperiment(
            experiment_id="concurrent-b",
            name="Concurrent B",
            faults=[],
            duration_seconds=2,
        )
        scheduler.schedule(exp_a)
        scheduler.schedule(exp_b)

        results: dict[str, object] = {}
        errors: list[Exception] = []

        def run_experiment(experiment_id: str) -> None:
            try:
                result = scheduler.run(experiment_id)
                results[experiment_id] = result
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        thread_a = threading.Thread(target=run_experiment, args=("concurrent-a",))
        thread_b = threading.Thread(target=run_experiment, args=("concurrent-b",))

        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10.0)
        thread_b.join(timeout=10.0)

        assert errors == [], f"Concurrent runs raised: {errors}"
        assert "concurrent-a" in results, "Experiment A did not complete"
        assert "concurrent-b" in results, "Experiment B did not complete"

        from aumai_chaos.models import ExperimentResult

        result_a: ExperimentResult = results["concurrent-a"]  # type: ignore[assignment]
        result_b: ExperimentResult = results["concurrent-b"]  # type: ignore[assignment]

        # Each result must contain its own experiment's started/ended events,
        # not a mix from both.
        events_a = {o.event for o in result_a.observations}
        events_b = {o.event for o in result_b.observations}
        assert "experiment_started" in events_a, "Experiment A missing started event"
        assert "experiment_ended" in events_a, "Experiment A missing ended event"
        assert "experiment_started" in events_b, "Experiment B missing started event"
        assert "experiment_ended" in events_b, "Experiment B missing ended event"

        # Neither result should be empty (the shared-observer bug caused one
        # experiment to clear the other's observations, leaving an empty list).
        assert len(result_a.observations) >= 2, (
            f"Experiment A observations were cleared: {result_a.observations}"
        )
        assert len(result_b.observations) >= 2, (
            f"Experiment B observations were cleared: {result_b.observations}"
        )
