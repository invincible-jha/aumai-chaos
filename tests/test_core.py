"""Tests for aumai_chaos.core — FaultInjector and custom exceptions."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from aumai_chaos.core import (
    ChaosError,
    ChaosTimeoutError,
    DataCorruptionError,
    FaultInjector,
    ResourceExhaustedError,
)
from aumai_chaos.models import FaultConfig, FaultType

# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    def test_chaos_timeout_error_is_timeout_error(self) -> None:
        assert issubclass(ChaosTimeoutError, TimeoutError)

    def test_chaos_error_is_runtime_error(self) -> None:
        assert issubclass(ChaosError, RuntimeError)

    def test_resource_exhausted_is_runtime_error(self) -> None:
        assert issubclass(ResourceExhaustedError, RuntimeError)

    def test_data_corruption_is_value_error(self) -> None:
        assert issubclass(DataCorruptionError, ValueError)

    def test_chaos_error_stores_code(self) -> None:
        exc = ChaosError(503, "Service unavailable")
        assert exc.error_code == 503

    def test_chaos_error_message_format(self) -> None:
        exc = ChaosError(404, "Not found")
        assert "[404]" in str(exc)
        assert "Not found" in str(exc)


# ---------------------------------------------------------------------------
# FaultInjector.inject_latency
# ---------------------------------------------------------------------------


class TestInjectLatency:
    def test_latency_blocks_for_requested_duration(
        self, injector: FaultInjector
    ) -> None:
        start = time.monotonic()
        injector.inject_latency(100)
        elapsed_ms = (time.monotonic() - start) * 1000
        # Allow generous upper bound to avoid flakiness on slow CI
        assert elapsed_ms >= 90
        assert elapsed_ms < 500

    def test_zero_latency_returns_immediately(self, injector: FaultInjector) -> None:
        start = time.monotonic()
        injector.inject_latency(0)
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms < 100


# ---------------------------------------------------------------------------
# FaultInjector.inject_error
# ---------------------------------------------------------------------------


class TestInjectError:
    def test_raises_chaos_error(self, injector: FaultInjector) -> None:
        with pytest.raises(ChaosError):
            injector.inject_error(500, "boom")

    def test_error_code_preserved(self, injector: FaultInjector) -> None:
        with pytest.raises(ChaosError) as exc_info:
            injector.inject_error(503, "unavailable")
        assert exc_info.value.error_code == 503

    def test_error_message_preserved(self, injector: FaultInjector) -> None:
        with pytest.raises(ChaosError) as exc_info:
            injector.inject_error(503, "unavailable")
        assert "unavailable" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FaultInjector.inject_timeout
# ---------------------------------------------------------------------------


class TestInjectTimeout:
    def test_raises_chaos_timeout_error(self, injector: FaultInjector) -> None:
        with pytest.raises(ChaosTimeoutError):
            injector.inject_timeout()

    def test_message_mentions_simulated(self, injector: FaultInjector) -> None:
        with pytest.raises(ChaosTimeoutError) as exc_info:
            injector.inject_timeout()
        assert "timeout" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# FaultInjector.inject_partial_failure
# ---------------------------------------------------------------------------


class TestInjectPartialFailure:
    def test_raises_runtime_error(self, injector: FaultInjector) -> None:
        with pytest.raises(RuntimeError):
            injector.inject_partial_failure()

    def test_custom_message_included(self, injector: FaultInjector) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            injector.inject_partial_failure("DB degraded")
        assert "DB degraded" in str(exc_info.value)

    def test_default_message_used(self, injector: FaultInjector) -> None:
        with pytest.raises(RuntimeError) as exc_info:
            injector.inject_partial_failure()
        assert "partial_failure" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FaultInjector.inject_resource_exhaustion
# ---------------------------------------------------------------------------


class TestInjectResourceExhaustion:
    def test_raises_resource_exhausted_error(self, injector: FaultInjector) -> None:
        with pytest.raises(ResourceExhaustedError):
            injector.inject_resource_exhaustion()

    def test_custom_message_included(self, injector: FaultInjector) -> None:
        with pytest.raises(ResourceExhaustedError) as exc_info:
            injector.inject_resource_exhaustion("OOM")
        assert "OOM" in str(exc_info.value)

    def test_default_message_present(self, injector: FaultInjector) -> None:
        with pytest.raises(ResourceExhaustedError) as exc_info:
            injector.inject_resource_exhaustion()
        assert "resource_exhaustion" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FaultInjector.inject_data_corruption
# ---------------------------------------------------------------------------


class TestInjectDataCorruption:
    def test_raises_data_corruption_error(self, injector: FaultInjector) -> None:
        with pytest.raises(DataCorruptionError):
            injector.inject_data_corruption()

    def test_custom_message_included(self, injector: FaultInjector) -> None:
        with pytest.raises(DataCorruptionError) as exc_info:
            injector.inject_data_corruption("Checksum fail")
        assert "Checksum fail" in str(exc_info.value)

    def test_default_message_present(self, injector: FaultInjector) -> None:
        with pytest.raises(DataCorruptionError) as exc_info:
            injector.inject_data_corruption()
        assert "data_corruption" in str(exc_info.value)


# ---------------------------------------------------------------------------
# FaultInjector.should_inject
# ---------------------------------------------------------------------------


class TestShouldInject:
    def test_probability_one_always_true(self, injector: FaultInjector) -> None:
        results = [injector.should_inject(1.0) for _ in range(20)]
        assert all(results)

    def test_probability_zero_always_false(self, injector: FaultInjector) -> None:
        results = [injector.should_inject(0.0) for _ in range(20)]
        assert not any(results)

    def test_probability_half_is_stochastic(self, injector: FaultInjector) -> None:
        # With p=0.5 over 200 trials the probability of all-True or all-False
        # is astronomically small, so this is effectively deterministic.
        results = [injector.should_inject(0.5) for _ in range(200)]
        assert any(results)
        assert not all(results)


# ---------------------------------------------------------------------------
# FaultInjector.inject dispatch — probability respected
# ---------------------------------------------------------------------------


class TestInjectDispatch:
    def test_inject_latency_type(
        self, injector: FaultInjector, latency_config: FaultConfig
    ) -> None:
        # Should not raise; just sleep briefly
        injector.inject(latency_config)  # probability=1.0, duration_ms=50

    def test_inject_error_type(
        self, injector: FaultInjector, error_config: FaultConfig
    ) -> None:
        with pytest.raises(ChaosError):
            injector.inject(error_config)

    def test_inject_timeout_type(
        self, injector: FaultInjector, timeout_config: FaultConfig
    ) -> None:
        with pytest.raises(ChaosTimeoutError):
            injector.inject(timeout_config)

    def test_inject_partial_failure_type(
        self, injector: FaultInjector, partial_failure_config: FaultConfig
    ) -> None:
        with pytest.raises(RuntimeError):
            injector.inject(partial_failure_config)

    def test_inject_resource_exhaustion_type(
        self, injector: FaultInjector, resource_exhaustion_config: FaultConfig
    ) -> None:
        with pytest.raises(ResourceExhaustedError):
            injector.inject(resource_exhaustion_config)

    def test_inject_data_corruption_type(
        self, injector: FaultInjector, data_corruption_config: FaultConfig
    ) -> None:
        with pytest.raises(DataCorruptionError):
            injector.inject(data_corruption_config)

    def test_zero_probability_never_injects(
        self, injector: FaultInjector, zero_probability_config: FaultConfig
    ) -> None:
        # Run many times — should never raise
        for _ in range(50):
            injector.inject(zero_probability_config)

    def test_inject_latency_raises_when_duration_ms_is_none(
        self, injector: FaultInjector
    ) -> None:
        """Latency faults without duration_ms must raise ValueError rather than
        silently using a magic default — callers should supply the duration
        explicitly to avoid unintentional 500 ms blocking."""
        config = FaultConfig(
            fault_type=FaultType.latency, probability=1.0, duration_ms=None
        )
        with pytest.raises(ValueError, match="duration_ms"):
            injector.inject(config)

    def test_inject_error_raises_when_error_code_is_none(
        self, injector: FaultInjector
    ) -> None:
        """Error faults without error_code must raise ValueError rather than
        silently using a magic default code."""
        config = FaultConfig(
            fault_type=FaultType.error,
            probability=1.0,
            error_code=None,
            error_message=None,
        )
        with pytest.raises(ValueError, match="error_code"):
            injector.inject(config)

    def test_inject_error_uses_default_message_when_none(
        self, injector: FaultInjector
    ) -> None:
        config = FaultConfig(
            fault_type=FaultType.error,
            probability=1.0,
            error_code=500,
            error_message=None,
        )
        with pytest.raises(ChaosError) as exc_info:
            injector.inject(config)
        assert "Injected error" in str(exc_info.value)

    def test_inject_skips_when_rng_says_no(self, injector: FaultInjector) -> None:
        config = FaultConfig(
            fault_type=FaultType.error,
            probability=0.5,
            error_code=503,
            error_message="skipped",
        )
        with patch.object(injector, "should_inject", return_value=False):
            # Must not raise even though fault_type=error
            injector.inject(config)

    def test_inject_fires_when_rng_says_yes(self, injector: FaultInjector) -> None:
        config = FaultConfig(
            fault_type=FaultType.error,
            probability=0.5,
            error_code=503,
            error_message="Injected",
        )
        with patch.object(injector, "should_inject", return_value=True):
            with pytest.raises(ChaosError):
                injector.inject(config)
