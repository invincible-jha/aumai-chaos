"""Decorator utilities for injecting chaos into arbitrary Python functions."""

from __future__ import annotations

import functools
from typing import Any, Callable, TypeVar

from aumai_chaos.core import FaultInjector
from aumai_chaos.models import FaultConfig, FaultType

F = TypeVar("F", bound=Callable[..., Any])


def chaos_monkey(
    fault_type: FaultType = FaultType.latency,
    probability: float = 0.1,
    duration_ms: int = 500,
    error_code: int = 500,
    error_message: str = "Chaos monkey error",
    affected_components: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator that randomly injects a fault each time the wrapped function is called.

    Args:
        fault_type:          The type of fault to inject.
        probability:         Probability (0–1) that a fault fires on each call.
        duration_ms:         Duration for latency/timeout faults (milliseconds).
        error_code:          HTTP-style error code for error faults.
        error_message:       Error message for error/partial_failure faults.
        affected_components: Optional component labels for observability.

    Example::

        @chaos_monkey(fault_type=FaultType.latency, probability=0.2, duration_ms=300)
        def call_tool(payload: dict) -> dict:
            ...
    """
    fault_config = FaultConfig(
        fault_type=fault_type,
        probability=probability,
        duration_ms=duration_ms,
        error_code=error_code,
        error_message=error_message,
        affected_components=affected_components or [],
    )
    injector = FaultInjector()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            injector.inject(fault_config)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def resilience_test(
    faults: list[FaultConfig],
) -> Callable[[F], F]:
    """Decorator that subjects the wrapped function to a list of faults on every call.

    All faults are evaluated in sequence.  Any fault whose probability check
    passes will be injected before the function body executes.

    Example::

        @resilience_test(faults=[
            FaultConfig(fault_type=FaultType.latency, probability=0.5, duration_ms=200),
            FaultConfig(fault_type=FaultType.error, probability=0.1, error_code=503),
        ])
        def fetch_context(query: str) -> str:
            ...
    """
    injector = FaultInjector()

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            for fault in faults:
                injector.inject(fault)
            return func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["chaos_monkey", "resilience_test"]
