"""Core fault injection engine for aumai-chaos."""

from __future__ import annotations

import random
import time

from aumai_chaos.models import FaultConfig, FaultType


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class ChaosTimeoutError(TimeoutError):
    """Simulated timeout injected by :class:`FaultInjector`."""


class ChaosError(RuntimeError):
    """Simulated application error injected by :class:`FaultInjector`."""

    def __init__(self, error_code: int, message: str) -> None:
        super().__init__(f"[{error_code}] {message}")
        self.error_code = error_code


class ResourceExhaustedError(RuntimeError):
    """Simulated resource exhaustion injected by :class:`FaultInjector`."""


class DataCorruptionError(ValueError):
    """Simulated data corruption injected by :class:`FaultInjector`."""


# ---------------------------------------------------------------------------
# FaultInjector
# ---------------------------------------------------------------------------

class FaultInjector:
    """Dispatch and apply individual fault types.

    All injection methods are synchronous.  For async callers, wrap the
    synchronous call in ``asyncio.to_thread`` or use
    ``await asyncio.sleep(duration_ms / 1000)`` directly for latency.
    """

    def inject_latency(self, duration_ms: int) -> None:
        """Block the current thread for *duration_ms* milliseconds."""
        time.sleep(duration_ms / 1000.0)

    def inject_error(self, error_code: int, message: str) -> None:
        """Raise a :class:`ChaosError` with *error_code* and *message*."""
        raise ChaosError(error_code, message)

    def inject_timeout(self) -> None:
        """Raise a :class:`ChaosTimeoutError` to simulate a hung operation."""
        raise ChaosTimeoutError("Simulated timeout injected by chaos framework.")

    def inject_partial_failure(self, message: str = "Partial failure") -> None:
        """Raise a RuntimeError representing a partial service degradation."""
        raise RuntimeError(f"[partial_failure] {message}")

    def inject_resource_exhaustion(self, message: str = "Resource exhausted") -> None:
        """Raise a :class:`ResourceExhaustedError`."""
        raise ResourceExhaustedError(f"[resource_exhaustion] {message}")

    def inject_data_corruption(self, message: str = "Data corrupted") -> None:
        """Raise a :class:`DataCorruptionError`."""
        raise DataCorruptionError(f"[data_corruption] {message}")

    def should_inject(self, probability: float) -> bool:
        """Return True with *probability* using the module-level RNG."""
        return random.random() < probability  # noqa: S311

    def inject(self, config: FaultConfig) -> None:
        """Dispatch to the appropriate injection method based on *config*.

        Respects *config.probability* — if the RNG decides not to fire,
        this method returns without raising or sleeping.
        """
        if not self.should_inject(config.probability):
            return

        if config.fault_type == FaultType.latency:
            duration = config.duration_ms if config.duration_ms is not None else 500
            self.inject_latency(duration)

        elif config.fault_type == FaultType.error:
            code = config.error_code if config.error_code is not None else 500
            msg = config.error_message or "Injected error"
            self.inject_error(code, msg)

        elif config.fault_type == FaultType.timeout:
            self.inject_timeout()

        elif config.fault_type == FaultType.partial_failure:
            msg = config.error_message or "Partial failure"
            self.inject_partial_failure(msg)

        elif config.fault_type == FaultType.resource_exhaustion:
            msg = config.error_message or "Resource exhausted"
            self.inject_resource_exhaustion(msg)

        elif config.fault_type == FaultType.data_corruption:
            msg = config.error_message or "Data corrupted"
            self.inject_data_corruption(msg)


__all__ = [
    "ChaosError",
    "ChaosTimeoutError",
    "DataCorruptionError",
    "FaultInjector",
    "ResourceExhaustedError",
]
