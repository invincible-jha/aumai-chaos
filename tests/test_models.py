"""Tests for aumai_chaos.models — Pydantic data models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from aumai_chaos.models import (
    ChaosExperiment,
    ExperimentResult,
    ExperimentStatus,
    FaultConfig,
    FaultType,
    ObservationPoint,
)

# ---------------------------------------------------------------------------
# FaultType enum
# ---------------------------------------------------------------------------


class TestFaultType:
    def test_all_members_are_strings(self) -> None:
        for member in FaultType:
            assert isinstance(member.value, str)

    def test_expected_members_exist(self) -> None:
        expected = {
            "latency",
            "error",
            "timeout",
            "partial_failure",
            "resource_exhaustion",
            "data_corruption",
        }
        actual = {m.value for m in FaultType}
        assert actual == expected

    def test_str_enum_coercion(self) -> None:
        # Pydantic coerces plain strings to enum members
        config = FaultConfig(fault_type="latency", probability=1.0)  # type: ignore[arg-type]
        assert config.fault_type is FaultType.latency


# ---------------------------------------------------------------------------
# FaultConfig
# ---------------------------------------------------------------------------


class TestFaultConfig:
    def test_default_probability(self) -> None:
        config = FaultConfig(fault_type=FaultType.latency)
        assert config.probability == 1.0

    def test_probability_bounds_upper(self) -> None:
        with pytest.raises(ValidationError):
            FaultConfig(fault_type=FaultType.error, probability=1.01)

    def test_probability_bounds_lower(self) -> None:
        with pytest.raises(ValidationError):
            FaultConfig(fault_type=FaultType.error, probability=-0.01)

    def test_probability_boundary_zero(self) -> None:
        config = FaultConfig(fault_type=FaultType.error, probability=0.0)
        assert config.probability == 0.0

    def test_probability_boundary_one(self) -> None:
        config = FaultConfig(fault_type=FaultType.error, probability=1.0)
        assert config.probability == 1.0

    def test_duration_ms_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            FaultConfig(fault_type=FaultType.latency, duration_ms=-1)

    def test_duration_ms_zero_is_valid(self) -> None:
        config = FaultConfig(fault_type=FaultType.latency, duration_ms=0)
        assert config.duration_ms == 0

    def test_affected_components_default_empty(self) -> None:
        config = FaultConfig(fault_type=FaultType.timeout)
        assert config.affected_components == []

    def test_optional_fields_are_none_by_default(self) -> None:
        config = FaultConfig(fault_type=FaultType.latency)
        assert config.duration_ms is None
        assert config.error_code is None
        assert config.error_message is None

    def test_all_fault_types_accepted(self) -> None:
        for fault_type in FaultType:
            config = FaultConfig(fault_type=fault_type, probability=0.5)
            assert config.fault_type == fault_type

    def test_model_serialisation_round_trip(self) -> None:
        config = FaultConfig(
            fault_type=FaultType.error,
            probability=0.75,
            error_code=503,
            error_message="unavailable",
            affected_components=["api", "db"],
        )
        restored = FaultConfig.model_validate_json(config.model_dump_json())
        assert restored == config


# ---------------------------------------------------------------------------
# ChaosExperiment
# ---------------------------------------------------------------------------


class TestChaosExperiment:
    def test_duration_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            ChaosExperiment(
                experiment_id="x",
                name="bad",
                duration_seconds=0,
            )

    def test_duration_negative_invalid(self) -> None:
        with pytest.raises(ValidationError):
            ChaosExperiment(
                experiment_id="x",
                name="bad",
                duration_seconds=-10,
            )

    def test_default_description_is_empty(self) -> None:
        exp = ChaosExperiment(experiment_id="x", name="Test")
        assert exp.description == ""

    def test_default_faults_empty(self) -> None:
        exp = ChaosExperiment(experiment_id="x", name="Test")
        assert exp.faults == []

    def test_default_target_components_empty(self) -> None:
        exp = ChaosExperiment(experiment_id="x", name="Test")
        assert exp.target_components == []

    def test_faults_list_preserved(self) -> None:
        fault = FaultConfig(fault_type=FaultType.timeout, probability=1.0)
        exp = ChaosExperiment(
            experiment_id="x",
            name="Test",
            faults=[fault],
        )
        assert len(exp.faults) == 1
        assert exp.faults[0].fault_type == FaultType.timeout

    def test_model_copy_update(self) -> None:
        exp = ChaosExperiment(experiment_id="original", name="Test", duration_seconds=5)
        copy = exp.model_copy(update={"experiment_id": "updated"})
        assert copy.experiment_id == "updated"
        assert copy.name == "Test"


# ---------------------------------------------------------------------------
# ExperimentStatus
# ---------------------------------------------------------------------------


class TestExperimentStatus:
    def test_all_lifecycle_states_present(self) -> None:
        values = {s.value for s in ExperimentStatus}
        assert values == {"pending", "running", "completed", "aborted"}


# ---------------------------------------------------------------------------
# ObservationPoint
# ---------------------------------------------------------------------------


class TestObservationPoint:
    def test_required_fields(self) -> None:
        now = datetime.now(tz=UTC)
        point = ObservationPoint(
            timestamp=now,
            component="llm",
            event="fault_fired",
        )
        assert point.timestamp == now
        assert point.component == "llm"
        assert point.event == "fault_fired"
        assert point.details == {}

    def test_details_stored(self) -> None:
        point = ObservationPoint(
            timestamp=datetime.now(tz=UTC),
            component="db",
            event="error",
            details={"code": 503, "msg": "timeout"},
        )
        assert point.details["code"] == 503

    def test_serialisation_preserves_timezone(self) -> None:
        now = datetime.now(tz=UTC)
        point = ObservationPoint(timestamp=now, component="c", event="e")
        restored = ObservationPoint.model_validate_json(point.model_dump_json())
        assert restored.timestamp == now


# ---------------------------------------------------------------------------
# ExperimentResult
# ---------------------------------------------------------------------------


class TestExperimentResult:
    def test_end_time_optional(self) -> None:
        exp = ChaosExperiment(experiment_id="x", name="Test")
        result = ExperimentResult(
            experiment=exp,
            status=ExperimentStatus.running,
            start_time=datetime.now(tz=UTC),
        )
        assert result.end_time is None

    def test_observations_default_empty(self) -> None:
        exp = ChaosExperiment(experiment_id="x", name="Test")
        result = ExperimentResult(
            experiment=exp,
            status=ExperimentStatus.pending,
            start_time=datetime.now(tz=UTC),
        )
        assert result.observations == []

    def test_summary_default_empty(self) -> None:
        exp = ChaosExperiment(experiment_id="x", name="Test")
        result = ExperimentResult(
            experiment=exp,
            status=ExperimentStatus.completed,
            start_time=datetime.now(tz=UTC),
        )
        assert result.summary == {}
