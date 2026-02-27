"""Shared pytest fixtures for aumai-chaos test suite."""

from __future__ import annotations

import pytest

from aumai_chaos.core import FaultInjector
from aumai_chaos.models import (
    ChaosExperiment,
    FaultConfig,
    FaultType,
)
from aumai_chaos.observer import ExperimentObserver
from aumai_chaos.scheduler import ExperimentScheduler

# ---------------------------------------------------------------------------
# FaultConfig fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def latency_config() -> FaultConfig:
    """FaultConfig that always injects a 50 ms latency."""
    return FaultConfig(
        fault_type=FaultType.latency,
        probability=1.0,
        duration_ms=50,
    )


@pytest.fixture()
def error_config() -> FaultConfig:
    """FaultConfig that always injects a ChaosError with code 503."""
    return FaultConfig(
        fault_type=FaultType.error,
        probability=1.0,
        error_code=503,
        error_message="Service unavailable",
    )


@pytest.fixture()
def timeout_config() -> FaultConfig:
    """FaultConfig that always injects a ChaosTimeoutError."""
    return FaultConfig(
        fault_type=FaultType.timeout,
        probability=1.0,
    )


@pytest.fixture()
def partial_failure_config() -> FaultConfig:
    """FaultConfig that always injects a partial failure."""
    return FaultConfig(
        fault_type=FaultType.partial_failure,
        probability=1.0,
        error_message="Downstream degraded",
    )


@pytest.fixture()
def resource_exhaustion_config() -> FaultConfig:
    """FaultConfig that always injects a ResourceExhaustedError."""
    return FaultConfig(
        fault_type=FaultType.resource_exhaustion,
        probability=1.0,
        error_message="OOM",
    )


@pytest.fixture()
def data_corruption_config() -> FaultConfig:
    """FaultConfig that always injects a DataCorruptionError."""
    return FaultConfig(
        fault_type=FaultType.data_corruption,
        probability=1.0,
        error_message="Checksum mismatch",
    )


@pytest.fixture()
def zero_probability_config() -> FaultConfig:
    """FaultConfig that never fires (probability=0)."""
    return FaultConfig(
        fault_type=FaultType.error,
        probability=0.0,
        error_code=500,
        error_message="Should never fire",
    )


# ---------------------------------------------------------------------------
# Core object fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def injector() -> FaultInjector:
    """A fresh FaultInjector instance."""
    return FaultInjector()


@pytest.fixture()
def observer() -> ExperimentObserver:
    """A fresh ExperimentObserver instance."""
    return ExperimentObserver()


@pytest.fixture()
def scheduler() -> ExperimentScheduler:
    """A fresh ExperimentScheduler instance."""
    return ExperimentScheduler()


# ---------------------------------------------------------------------------
# ChaosExperiment fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_experiment() -> ChaosExperiment:
    """A valid experiment with no faults and a 1-second duration."""
    return ChaosExperiment(
        experiment_id="exp-minimal",
        name="Minimal Experiment",
        description="No faults; used to verify happy-path scheduling.",
        faults=[],
        duration_seconds=1,
        target_components=["agent"],
    )


@pytest.fixture()
def error_experiment() -> ChaosExperiment:
    """An experiment that always fires an error fault, with 1-second duration."""
    return ChaosExperiment(
        experiment_id="exp-error",
        name="Error Experiment",
        faults=[
            FaultConfig(
                fault_type=FaultType.error,
                probability=1.0,
                error_code=500,
                error_message="Simulated error",
                affected_components=["llm"],
            )
        ],
        duration_seconds=1,
        target_components=["llm"],
    )
