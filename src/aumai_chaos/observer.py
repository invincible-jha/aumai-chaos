"""Observation capture for chaos experiments."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Generator

from aumai_chaos.models import ObservationPoint


class ExperimentObserver:
    """Collect timestamped observation points during a chaos experiment.

    Designed to be thread-safe for use in concurrent experiments.  Each
    call to ``observe`` appends an :class:`ObservationPoint` with the
    current UTC timestamp.
    """

    def __init__(self) -> None:
        self._observations: list[ObservationPoint] = []

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
        self._observations.append(point)

    def get_observations(self) -> list[ObservationPoint]:
        """Return a shallow copy of all observations recorded so far."""
        return list(self._observations)

    def clear(self) -> None:
        """Discard all recorded observations."""
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
