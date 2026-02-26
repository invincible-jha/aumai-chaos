"""aumai-chaos: Fault injection framework for testing agent resilience."""

from aumai_chaos.core import (
    ChaosError,
    ChaosTimeoutError,
    DataCorruptionError,
    FaultInjector,
    ResourceExhaustedError,
)
from aumai_chaos.decorators import chaos_monkey, resilience_test
from aumai_chaos.models import (
    ChaosExperiment,
    ExperimentResult,
    ExperimentStatus,
    FaultConfig,
    FaultType,
    ObservationPoint,
)
from aumai_chaos.observer import ExperimentObserver
from aumai_chaos.scheduler import ExperimentScheduler

__version__ = "0.1.0"

__all__ = [
    "ChaosError",
    "ChaosExperiment",
    "ChaosTimeoutError",
    "DataCorruptionError",
    "ExperimentObserver",
    "ExperimentResult",
    "ExperimentScheduler",
    "ExperimentStatus",
    "FaultConfig",
    "FaultInjector",
    "FaultType",
    "ObservationPoint",
    "ResourceExhaustedError",
    "chaos_monkey",
    "resilience_test",
]
