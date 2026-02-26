"""Pydantic models for aumai-chaos."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FaultType(str, Enum):
    """Categories of injectable faults."""

    latency = "latency"
    error = "error"
    timeout = "timeout"
    partial_failure = "partial_failure"
    resource_exhaustion = "resource_exhaustion"
    data_corruption = "data_corruption"


class FaultConfig(BaseModel):
    """Declarative specification for a single injectable fault."""

    fault_type: FaultType
    probability: float = Field(default=1.0, ge=0.0, le=1.0)
    duration_ms: int | None = Field(default=None, ge=0)
    error_code: int | None = None
    error_message: str | None = None
    affected_components: list[str] = Field(default_factory=list)


class ChaosExperiment(BaseModel):
    """A named collection of faults to be run against target components."""

    experiment_id: str
    name: str
    description: str = ""
    faults: list[FaultConfig] = Field(default_factory=list)
    duration_seconds: int = Field(default=60, gt=0)
    target_components: list[str] = Field(default_factory=list)


class ExperimentStatus(str, Enum):
    """Lifecycle state of a chaos experiment."""

    pending = "pending"
    running = "running"
    completed = "completed"
    aborted = "aborted"


class ObservationPoint(BaseModel):
    """A single timestamped observation captured during an experiment."""

    timestamp: datetime
    component: str
    event: str
    details: dict[str, object] = Field(default_factory=dict)


class ExperimentResult(BaseModel):
    """Complete record of a chaos experiment run."""

    experiment: ChaosExperiment
    status: ExperimentStatus
    start_time: datetime
    end_time: datetime | None = None
    observations: list[ObservationPoint] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)


__all__ = [
    "ChaosExperiment",
    "ExperimentResult",
    "ExperimentStatus",
    "FaultConfig",
    "FaultType",
    "ObservationPoint",
]
