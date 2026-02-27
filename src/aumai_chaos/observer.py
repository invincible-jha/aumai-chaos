"""Observation capture for chaos experiments."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime

from aumai_chaos.models import ObservationPoint


class ExperimentObserver:
    """Collect timestamped observation points during a chaos experiment.

    Designed to be thread-safe for use in concurrent experiments.  Each
    call to ``observe`` appends an :class:`ObservationPoint` with the
    current UTC timestamp.

    Thread safety is achieved via an explicit :class:`threading.Lock` that
    guards all mutations (``observe``, ``clear``) and snapshot reads
    (``get_observations``).  This is a stronger guarantee than relying on
    CPython's GIL, and correctly handles iteration-during-append scenarios
    that would otherwise cause ``RuntimeError`` under free-threaded Python.
    """

    def __init__(self) -> None:
        self._observations: list[ObservationPoint] = []
        self._lock: threading.Lock = threading.Lock()

    def observe(
        self,
        component: str,
        event: str,
        details: dict[str, object] | None = None,
    ) -> None:
        """Record a single observation.

        Args:
            component: The component being observed (e.g. ``"llm_tool_call"``).
            event:     A short event label (e.g. ``"latency_injected"``).
            details:   Optional free-form detail dict for structured logging.
        """
        point = ObservationPoint(
            timestamp=datetime.now(tz=UTC),
            component=component,
            event=event,
            details=details or {},
        )
        with self._lock:
            self._observations.append(point)

    def get_observations(self) -> list[ObservationPoint]:
        """Return a shallow copy of all observations recorded so far.

        The copy is taken under the lock to prevent a concurrent ``observe``
        or ``clear`` from modifying the list during iteration.
        """
        with self._lock:
            return list(self._observations)

    def clear(self) -> None:
        """Discard all recorded observations."""
        with self._lock:
            self._observations.clear()

    @contextmanager
    def scope(
        self, component: str, event_prefix: str = ""
    ) -> Generator[None, None, None]:
        """Context manager that records ``start`` and ``end`` (or ``error``) events.

        Example::

            with observer.scope("database", "query"):
                run_query()
        """
        prefix = f"{event_prefix}_" if event_prefix else ""
        self.observe(component, f"{prefix}start")
        try:
            yield
            self.observe(component, f"{prefix}end")
        except Exception as exc:
            self.observe(
                component,
                f"{prefix}error",
                {"exception_type": type(exc).__name__, "message": str(exc)},
            )
            raise


__all__ = ["ExperimentObserver"]
