"""aumai-chaos quickstart — working demonstrations of all major features.

Run this file directly to verify your installation:

    python examples/quickstart.py

Each demo is self-contained and shows a different aspect of fault injection.
All demos use short durations so the file runs in under 30 seconds total.
"""

from __future__ import annotations

import random
import time

from aumai_chaos import (
    ChaosError,
    ChaosExperiment,
    ChaosTimeoutError,
    DataCorruptionError,
    ExperimentObserver,
    ExperimentScheduler,
    ExperimentStatus,
    FaultConfig,
    FaultInjector,
    FaultType,
    ResourceExhaustedError,
    chaos_monkey,
    resilience_test,
)


# ---------------------------------------------------------------------------
# Demo 1 — Direct fault injection with FaultInjector
# ---------------------------------------------------------------------------

def demo_direct_injection() -> None:
    """Show each fault type being injected and caught directly."""

    print("\n=== Demo 1: Direct Fault Injection ===")

    injector = FaultInjector()

    # Latency: blocks the thread, returns normally
    start = time.perf_counter()
    injector.inject_latency(duration_ms=100)
    elapsed_ms = (time.perf_counter() - start) * 1000
    print(f"  inject_latency(100ms): slept {elapsed_ms:.0f}ms")
    assert elapsed_ms >= 90, "Expected at least 90ms sleep"

    # Error: raises ChaosError with the provided code
    try:
        injector.inject_error(error_code=503, message="Service unavailable")
    except ChaosError as exc:
        print(f"  inject_error: caught ChaosError code={exc.error_code}, msg='{exc}'")
        assert exc.error_code == 503

    # Timeout: raises ChaosTimeoutError (subclass of TimeoutError)
    try:
        injector.inject_timeout()
    except ChaosTimeoutError as exc:
        print(f"  inject_timeout: caught ChaosTimeoutError (also TimeoutError): {exc}")
    except TimeoutError:
        print("  inject_timeout: caught as TimeoutError (base class catch works too)")

    # Resource exhaustion
    try:
        injector.inject_resource_exhaustion("OOM simulated")
    except ResourceExhaustedError as exc:
        print(f"  inject_resource_exhaustion: {exc}")

    # Data corruption
    try:
        injector.inject_data_corruption("Checksum mismatch")
    except DataCorruptionError as exc:
        print(f"  inject_data_corruption: {exc}")

    # Partial failure
    try:
        injector.inject_partial_failure("Degraded response")
    except RuntimeError as exc:
        print(f"  inject_partial_failure: {exc}")

    print("  Demo 1 passed.")


# ---------------------------------------------------------------------------
# Demo 2 — Probabilistic injection via FaultConfig
# ---------------------------------------------------------------------------

def demo_probabilistic_injection() -> None:
    """Show that faults fire at approximately the configured probability."""

    print("\n=== Demo 2: Probabilistic Fault Injection ===")

    random.seed(42)  # Seed for reproducibility in tests

    injector = FaultInjector()
    config = FaultConfig(
        fault_type=FaultType.error,
        probability=0.3,
        error_code=500,
        error_message="Probabilistic error",
    )

    fires = 0
    trials = 50
    for _ in range(trials):
        try:
            injector.inject(config)
        except ChaosError:
            fires += 1

    rate = fires / trials
    print(f"  Fired {fires}/{trials} times — rate={rate:.2f} (expected ~0.30)")
    # Allow generous tolerance since probability is random
    assert 0.10 <= rate <= 0.55, f"Rate {rate} outside expected range 0.10-0.55"

    print("  Demo 2 passed.")


# ---------------------------------------------------------------------------
# Demo 3 — @chaos_monkey decorator
# ---------------------------------------------------------------------------

def demo_chaos_monkey_decorator() -> None:
    """Demonstrate @chaos_monkey on a simulated tool call function."""

    print("\n=== Demo 3: @chaos_monkey Decorator ===")

    random.seed(0)  # Reproducible

    @chaos_monkey(fault_type=FaultType.latency, probability=0.5, duration_ms=50)
    def search_tool(query: str) -> list[str]:
        """A search tool that sometimes runs slowly."""
        return [f"result for '{query}'"]

    slow_calls = 0
    for i in range(10):
        start = time.perf_counter()
        results = search_tool(f"query {i}")
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms > 30:
            slow_calls += 1

    print(f"  {slow_calls}/10 calls were artificially slowed (expected ~5)")
    # Generous assertion — any non-zero count confirms injection is working
    assert slow_calls >= 1, "Expected at least 1 slow call with probability=0.5"

    print("  Demo 3 passed.")


# ---------------------------------------------------------------------------
# Demo 4 — @resilience_test decorator with multiple fault types
# ---------------------------------------------------------------------------

def demo_resilience_test_decorator() -> None:
    """Show @resilience_test applying multiple faults to a function."""

    print("\n=== Demo 4: @resilience_test Decorator ===")

    random.seed(7)  # Reproducible sequence

    @resilience_test(faults=[
        FaultConfig(fault_type=FaultType.latency, probability=0.4, duration_ms=30),
        FaultConfig(fault_type=FaultType.error, probability=0.2, error_code=429,
                    error_message="Rate limited"),
    ])
    def embed_text(text: str) -> list[float]:
        """Embedding function subjected to latency and rate-limit faults."""
        return [0.1, 0.2, 0.3]

    successes, rate_limit_errors, slow_calls = 0, 0, 0
    for i in range(20):
        start = time.perf_counter()
        try:
            embed_text(f"text {i}")
            successes += 1
            if (time.perf_counter() - start) * 1000 > 20:
                slow_calls += 1
        except ChaosError as exc:
            if exc.error_code == 429:
                rate_limit_errors += 1

    print(f"  Successes: {successes}, Rate-limit errors: {rate_limit_errors}, "
          f"Slow calls: {slow_calls}")
    print("  Demo 4 passed.")


# ---------------------------------------------------------------------------
# Demo 5 — ExperimentObserver with scope context manager
# ---------------------------------------------------------------------------

def demo_experiment_observer() -> None:
    """Show how to record structured observations during code execution."""

    print("\n=== Demo 5: ExperimentObserver ===")

    observer = ExperimentObserver()

    # Manual observation
    observer.observe("agent", "session_start", {"user_id": "u-123"})

    # Scope context manager: records _start, _end (or _error)
    with observer.scope("vector_search", "embed"):
        time.sleep(0.01)  # simulate work
    # Recorded: "embed_start" and "embed_end"

    # Scope with an error
    try:
        with observer.scope("database", "query"):
            raise ValueError("Simulated DB error")
    except ValueError:
        pass  # Recorded: "start" and "error" (no prefix since event_prefix="")

    observer.observe("agent", "session_end", {"duration_ms": 150})

    observations = observer.get_observations()
    print(f"  Recorded {len(observations)} observations:")
    for obs in observations:
        print(f"    [{obs.component}] {obs.event}  details={obs.details}")

    assert len(observations) == 6  # start, end, end(err), error(detail), 2 manual
    assert any(obs.event == "embed_start" for obs in observations)
    assert any(obs.event == "embed_end" for obs in observations)
    assert any(obs.event == "error" and "exception_type" in obs.details for obs in observations)

    print("  Demo 5 passed.")


# ---------------------------------------------------------------------------
# Demo 6 — Structured experiment with ExperimentScheduler
# ---------------------------------------------------------------------------

def demo_experiment_scheduler() -> None:
    """Run a short structured ChaosExperiment and inspect the result."""

    print("\n=== Demo 6: ExperimentScheduler ===")

    experiment = ChaosExperiment(
        experiment_id="demo-exp-001",
        name="Short fault injection experiment",
        description="3 seconds of latency and error injection",
        duration_seconds=3,
        target_components=["mock_tool"],
        faults=[
            FaultConfig(
                fault_type=FaultType.latency,
                probability=0.6,
                duration_ms=50,
                affected_components=["mock_tool"],
            ),
            FaultConfig(
                fault_type=FaultType.error,
                probability=0.2,
                error_code=503,
                error_message="Mock upstream failure",
                affected_components=["mock_tool"],
            ),
        ],
    )

    scheduler = ExperimentScheduler()
    experiment_id = scheduler.schedule(experiment)
    print(f"  Scheduled experiment: {experiment_id}")

    result = scheduler.run(experiment_id)

    print(f"  Status: {result.status.value}")
    print(f"  Duration: {result.summary.get('duration_seconds', 0):.1f}s")
    print(f"  Total faults fired: {result.summary.get('total_faults_fired', 0)}")
    print(f"  Faults by type: {result.summary.get('faults_by_type', {})}")
    print(f"  Observations: {len(result.observations)}")

    assert result.status == ExperimentStatus.completed
    assert result.end_time is not None

    # Verify result is retrievable
    fetched = scheduler.get_result(experiment_id)
    assert fetched is not None
    assert fetched.experiment_id == experiment_id

    print("  Demo 6 passed.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all quickstart demos in sequence."""
    print("aumai-chaos quickstart demos")
    print("=" * 45)
    print("(Demo 6 runs for ~3 seconds — please wait)")

    demo_direct_injection()
    demo_probabilistic_injection()
    demo_chaos_monkey_decorator()
    demo_resilience_test_decorator()
    demo_experiment_observer()
    demo_experiment_scheduler()

    print("\n" + "=" * 45)
    print("All demos completed successfully.")


if __name__ == "__main__":
    main()
