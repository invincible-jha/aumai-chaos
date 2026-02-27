"""Experiment scheduling and execution for aumai-chaos."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime

from aumai_chaos.core import FaultInjector
from aumai_chaos.models import (
    ChaosExperiment,
    ExperimentResult,
    ExperimentStatus,
)
from aumai_chaos.observer import ExperimentObserver


class ExperimentNotFoundError(KeyError):
    """Raised when an experiment_id is not found in the scheduler."""


class ExperimentScheduler:
    """Schedule, run, and abort chaos experiments.

    Each experiment is run synchronously in ``run`` unless the caller
    explicitly spawns a thread.  ``abort`` is thread-safe and signals a
    running experiment to stop early.
    """

    def __init__(self) -> None:
        self._experiments: dict[str, ChaosExperiment] = {}
        self._results: dict[str, ExperimentResult] = {}
        self._abort_flags: dict[str, threading.Event] = {}
        self._injector = FaultInjector()
        # Note: no shared _observer here — each run() creates its own
        # ExperimentObserver instance so that concurrent runs are fully
        # isolated.  See run() implementation below.

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(self, experiment: ChaosExperiment) -> str:
        """Register *experiment* and return its experiment_id.

        If the experiment already has an ID it is preserved; otherwise a
        new UUID is assigned.
        """
        experiment_id = experiment.experiment_id or str(uuid.uuid4())
        stored = experiment.model_copy(update={"experiment_id": experiment_id})
        self._experiments[experiment_id] = stored
        return experiment_id

    def run(self, experiment_id: str) -> ExperimentResult:
        """Execute the scheduled experiment synchronously.

        The experiment runs for ``duration_seconds``, injecting faults on each
        tick (1-second intervals) until the duration elapses or ``abort`` is
        called.

        Args:
            experiment_id: The ID returned by :meth:`schedule`.

        Returns:
            An :class:`ExperimentResult` with status, observations, and summary.

        Raises:
            ExperimentNotFoundError: if *experiment_id* was not scheduled.
        """
        if experiment_id not in self._experiments:
            raise ExperimentNotFoundError(experiment_id)

        experiment = self._experiments[experiment_id]
        abort_flag = threading.Event()
        self._abort_flags[experiment_id] = abort_flag

        # Create a fresh, isolated observer for this run.  A shared observer
        # would be cleared on each run() call, which corrupts observations for
        # any concurrently executing experiment on the same scheduler instance.
        observer = ExperimentObserver()
        start_time = datetime.now(tz=UTC)

        result = ExperimentResult(
            experiment=experiment,
            status=ExperimentStatus.running,
            start_time=start_time,
        )
        self._results[experiment_id] = result

        observer.observe(
            "scheduler",
            "experiment_started",
            {"experiment_id": experiment_id, "name": experiment.name},
        )

        fault_counts: dict[str, int] = {}
        error_counts: dict[str, int] = {}

        deadline = time.monotonic() + experiment.duration_seconds
        while time.monotonic() < deadline:
            if abort_flag.is_set():
                break

            for fault in experiment.faults:
                for component in (
                    fault.affected_components or experiment.target_components or ["*"]
                ):
                    try:
                        self._injector.inject(fault)
                        observer.observe(
                            component,
                            f"{fault.fault_type.value}_injected",
                            {"probability": fault.probability},
                        )
                        fault_counts[fault.fault_type.value] = (
                            fault_counts.get(fault.fault_type.value, 0) + 1
                        )
                    except Exception as exc:  # noqa: BLE001
                        observer.observe(
                            component,
                            f"{fault.fault_type.value}_exception",
                            {"exception": str(exc)},
                        )
                        error_counts[fault.fault_type.value] = (
                            error_counts.get(fault.fault_type.value, 0) + 1
                        )

            time.sleep(1.0)

        end_time = datetime.now(tz=UTC)
        if abort_flag.is_set():
            final_status = ExperimentStatus.aborted
        else:
            final_status = ExperimentStatus.completed

        observer.observe(
            "scheduler",
            "experiment_ended",
            {"status": final_status.value},
        )

        summary: dict[str, object] = {
            "total_faults_fired": sum(fault_counts.values()),
            "faults_by_type": fault_counts,
            "errors_by_type": error_counts,
            "duration_seconds": (end_time - start_time).total_seconds(),
        }

        final_result = ExperimentResult(
            experiment=experiment,
            status=final_status,
            start_time=start_time,
            end_time=end_time,
            observations=observer.get_observations(),
            summary=summary,
        )
        self._results[experiment_id] = final_result
        return final_result

    def abort(self, experiment_id: str) -> None:
        """Signal the running experiment to stop at the next tick.

        Raises:
            ExperimentNotFoundError: if *experiment_id* is unknown.
        """
        if experiment_id not in self._experiments:
            raise ExperimentNotFoundError(experiment_id)
        flag = self._abort_flags.get(experiment_id)
        if flag:
            flag.set()

    def get_result(self, experiment_id: str) -> ExperimentResult | None:
        """Return the latest result for *experiment_id*, or None."""
        return self._results.get(experiment_id)


__all__ = ["ExperimentNotFoundError", "ExperimentScheduler"]
