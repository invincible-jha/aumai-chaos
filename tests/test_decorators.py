"""Tests for aumai_chaos.decorators — chaos_monkey and resilience_test."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from aumai_chaos.core import (
    ChaosError,
    ChaosTimeoutError,
    DataCorruptionError,
    FaultInjector,
    ResourceExhaustedError,
)
from aumai_chaos.decorators import chaos_monkey, resilience_test
from aumai_chaos.models import FaultConfig, FaultType

# ---------------------------------------------------------------------------
# chaos_monkey decorator
# ---------------------------------------------------------------------------


class TestChaosMonkeyDecorator:
    def test_wraps_preserves_function_name(self) -> None:
        @chaos_monkey(fault_type=FaultType.latency, probability=0.0)
        def my_function() -> str:
            return "ok"

        assert my_function.__name__ == "my_function"

    def test_wraps_preserves_docstring(self) -> None:
        @chaos_monkey(fault_type=FaultType.latency, probability=0.0)
        def documented() -> None:
            """My docstring."""

        assert documented.__doc__ == "My docstring."

    def test_zero_probability_never_injects(self) -> None:
        @chaos_monkey(fault_type=FaultType.error, probability=0.0)
        def safe_function() -> str:
            return "safe"

        for _ in range(20):
            assert safe_function() == "safe"

    def test_full_probability_injects_latency(self) -> None:
        @chaos_monkey(fault_type=FaultType.latency, probability=1.0, duration_ms=50)
        def slow_function() -> str:
            return "result"

        start = time.monotonic()
        result = slow_function()
        elapsed_ms = (time.monotonic() - start) * 1000
        assert result == "result"
        assert elapsed_ms >= 40

    def test_full_probability_injects_error(self) -> None:
        @chaos_monkey(
            fault_type=FaultType.error,
            probability=1.0,
            error_code=503,
            error_message="service down",
        )
        def failing_function() -> None:
            pass  # pragma: no cover

        with pytest.raises(ChaosError) as exc_info:
            failing_function()
        assert exc_info.value.error_code == 503

    def test_full_probability_injects_timeout(self) -> None:
        @chaos_monkey(fault_type=FaultType.timeout, probability=1.0)
        def timeout_function() -> None:
            pass  # pragma: no cover

        with pytest.raises(ChaosTimeoutError):
            timeout_function()

    def test_full_probability_injects_partial_failure(self) -> None:
        @chaos_monkey(fault_type=FaultType.partial_failure, probability=1.0)
        def degraded_function() -> None:
            pass  # pragma: no cover

        with pytest.raises(RuntimeError):
            degraded_function()

    def test_full_probability_injects_resource_exhaustion(self) -> None:
        @chaos_monkey(fault_type=FaultType.resource_exhaustion, probability=1.0)
        def oom_function() -> None:
            pass  # pragma: no cover

        with pytest.raises(ResourceExhaustedError):
            oom_function()

    def test_full_probability_injects_data_corruption(self) -> None:
        @chaos_monkey(fault_type=FaultType.data_corruption, probability=1.0)
        def corrupt_function() -> None:
            pass  # pragma: no cover

        with pytest.raises(DataCorruptionError):
            corrupt_function()

    def test_function_body_executes_after_latency(self) -> None:
        call_log: list[str] = []

        @chaos_monkey(fault_type=FaultType.latency, probability=1.0, duration_ms=10)
        def tracked() -> None:
            call_log.append("called")

        tracked()
        assert call_log == ["called"]

    def test_function_body_not_executed_when_error_raised(self) -> None:
        call_log: list[str] = []

        @chaos_monkey(fault_type=FaultType.error, probability=1.0)
        def body_skipped() -> None:
            call_log.append("should not reach")

        with pytest.raises(ChaosError):
            body_skipped()
        assert call_log == []

    def test_args_and_kwargs_forwarded(self) -> None:
        @chaos_monkey(fault_type=FaultType.latency, probability=0.0)
        def add(a: int, b: int = 0) -> int:
            return a + b

        assert add(3, b=4) == 7

    def test_affected_components_stored_in_fault_config(self) -> None:
        injector_mock = MagicMock(spec=FaultInjector)
        injector_mock.inject = MagicMock()

        with patch("aumai_chaos.decorators.FaultInjector", return_value=injector_mock):

            @chaos_monkey(
                fault_type=FaultType.error,
                probability=1.0,
                affected_components=["api", "cache"],
            )
            def some_fn() -> None:
                pass

            some_fn()

        call_args = injector_mock.inject.call_args[0][0]
        assert call_args.affected_components == ["api", "cache"]

    def test_default_affected_components_empty(self) -> None:
        injector_mock = MagicMock(spec=FaultInjector)
        injector_mock.inject = MagicMock()

        with patch("aumai_chaos.decorators.FaultInjector", return_value=injector_mock):

            @chaos_monkey(fault_type=FaultType.latency, probability=0.0)
            def fn() -> None:
                pass

            fn()

        call_args = injector_mock.inject.call_args[0][0]
        assert call_args.affected_components == []


# ---------------------------------------------------------------------------
# resilience_test decorator
# ---------------------------------------------------------------------------


class TestResilienceTestDecorator:
    def test_wraps_preserves_function_name(self) -> None:
        @resilience_test(faults=[])
        def my_fn() -> str:
            return "ok"

        assert my_fn.__name__ == "my_fn"

    def test_empty_faults_list_runs_function_normally(self) -> None:
        @resilience_test(faults=[])
        def no_chaos() -> int:
            return 42

        assert no_chaos() == 42

    def test_single_fault_zero_probability_does_not_fire(self) -> None:
        fault = FaultConfig(fault_type=FaultType.error, probability=0.0)

        @resilience_test(faults=[fault])
        def guarded() -> str:
            return "fine"

        for _ in range(20):
            assert guarded() == "fine"

    def test_single_error_fault_full_probability_raises(self) -> None:
        fault = FaultConfig(
            fault_type=FaultType.error,
            probability=1.0,
            error_code=400,
            error_message="bad request",
        )

        @resilience_test(faults=[fault])
        def bad_fn() -> None:
            pass  # pragma: no cover

        with pytest.raises(ChaosError) as exc_info:
            bad_fn()
        assert exc_info.value.error_code == 400

    def test_first_fault_raises_before_second_executes(self) -> None:
        call_order: list[str] = []

        injector_mock = MagicMock(spec=FaultInjector)

        def side_effect(config: FaultConfig) -> None:
            if config.error_message == "first":
                call_order.append("first")
                raise ChaosError(500, "first")
            call_order.append("second")

        injector_mock.inject.side_effect = side_effect

        fault_a = FaultConfig(
            fault_type=FaultType.error, probability=1.0, error_message="first"
        )
        fault_b = FaultConfig(
            fault_type=FaultType.error, probability=1.0, error_message="second"
        )

        with patch("aumai_chaos.decorators.FaultInjector", return_value=injector_mock):

            @resilience_test(faults=[fault_a, fault_b])
            def fn() -> None:
                pass

            with pytest.raises(ChaosError):
                fn()

        assert call_order == ["first"]

    def test_multiple_zero_probability_faults_all_pass(self) -> None:
        faults = [
            FaultConfig(fault_type=FaultType.error, probability=0.0),
            FaultConfig(fault_type=FaultType.timeout, probability=0.0),
            FaultConfig(fault_type=FaultType.data_corruption, probability=0.0),
        ]

        @resilience_test(faults=faults)
        def resilient() -> str:
            return "survived"

        assert resilient() == "survived"

    def test_latency_fault_slows_invocation(self) -> None:
        fault = FaultConfig(
            fault_type=FaultType.latency, probability=1.0, duration_ms=50
        )

        @resilience_test(faults=[fault])
        def timed_fn() -> str:
            return "done"

        start = time.monotonic()
        timed_fn()
        elapsed_ms = (time.monotonic() - start) * 1000
        assert elapsed_ms >= 40

    def test_each_call_re_evaluates_faults(self) -> None:
        """Fault evaluation happens every invocation, not once at decoration time."""
        results: list[bool] = []

        injector_mock = MagicMock(spec=FaultInjector)
        injector_mock.inject = MagicMock()

        with patch("aumai_chaos.decorators.FaultInjector", return_value=injector_mock):
            fault = FaultConfig(fault_type=FaultType.latency, probability=0.5)

            @resilience_test(faults=[fault])
            def fn() -> None:
                results.append(True)

            for _ in range(5):
                fn()

        assert injector_mock.inject.call_count == 5

    def test_args_and_kwargs_forwarded(self) -> None:
        @resilience_test(faults=[])
        def multiply(x: int, factor: int = 2) -> int:
            return x * factor

        assert multiply(5, factor=3) == 15

    def test_return_value_preserved(self) -> None:
        fault = FaultConfig(
            fault_type=FaultType.latency, probability=1.0, duration_ms=5
        )

        @resilience_test(faults=[fault])
        def produce() -> dict[str, int]:
            return {"answer": 42}

        assert produce() == {"answer": 42}
