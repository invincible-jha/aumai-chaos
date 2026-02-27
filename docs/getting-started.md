# Getting Started with aumai-chaos

This guide takes you from installation through your first chaos experiment and the most
useful patterns for testing agent resilience.

---

## Prerequisites

- **Python 3.11 or later**
- For YAML experiment files: `pip install pyyaml`
- An agent or function-based system you want to test

---

## Installation

### From PyPI (recommended)

```bash
pip install aumai-chaos
```

Verify:

```bash
aumai-chaos --version
# aumai-chaos, version 0.1.0
```

### From source

```bash
git clone https://github.com/aumai/aumai-chaos.git
cd aumai-chaos
pip install -e .
```

### Development mode

```bash
git clone https://github.com/aumai/aumai-chaos.git
cd aumai-chaos
pip install -e ".[dev]"
make lint test
```

---

## Your First Fault Injection

### Step 1 — One-line injection with the `@chaos_monkey` decorator

The fastest way to start testing resilience is to decorate a function.

```python
# my_agent.py
from aumai_chaos import chaos_monkey, FaultType

@chaos_monkey(fault_type=FaultType.latency, probability=0.5, duration_ms=500)
def call_search_tool(query: str) -> list[str]:
    """A tool that will be slow 50% of the time."""
    # Simulate the real tool work
    return [f"Result for: {query}"]

# Test it manually
import time

slow_count = 0
for i in range(10):
    start = time.perf_counter()
    result = call_search_tool("test query")
    elapsed_ms = (time.perf_counter() - start) * 1000
    if elapsed_ms > 400:
        slow_count += 1

print(f"{slow_count}/10 calls were artificially slowed (expected ~5)")
```

### Step 2 — Catch a ChaosError

```python
from aumai_chaos import chaos_monkey, ChaosError, FaultType

@chaos_monkey(fault_type=FaultType.error, probability=0.3, error_code=503)
def call_llm_api(prompt: str) -> str:
    return "LLM response"

successes, failures = 0, 0
for _ in range(20):
    try:
        call_llm_api("Hello")
        successes += 1
    except ChaosError as exc:
        failures += 1
        print(f"  Caught ChaosError: code={exc.error_code}")

print(f"Successes: {successes}, Failures: {failures} (expected ~6 failures in 20)")
```

### Step 3 — Run a structured experiment from the CLI

Create an experiment file:

```bash
cat > /tmp/quick-experiment.yaml << 'EOF'
experiment_id: "quick-test"
name: "Quick latency test"
description: "5-second experiment injecting latency and errors"
duration_seconds: 5
target_components:
  - tool_executor
faults:
  - fault_type: latency
    probability: 0.5
    duration_ms: 100
    affected_components:
      - tool_executor
  - fault_type: error
    probability: 0.1
    error_code: 500
    error_message: "Simulated upstream failure"
    affected_components:
      - tool_executor
EOF
```

Run it:

```bash
aumai-chaos run --experiment /tmp/quick-experiment.yaml
```

Output:

```
Running experiment 'Quick latency test' (id=quick-test) for 5s...

Status    : completed
Start     : 2024-01-15T10:00:00.000000+00:00
End       : 2024-01-15T10:00:05.012345+00:00
Summary   :
  total_faults_fired: 5
  faults_by_type: {"latency": 3, "error": 1}  (approximately)
  errors_by_type: {"error": 1}
  duration_seconds: 5.012
Observations: 12 recorded
```

---

## Common Patterns

### Pattern 1 — Test timeout handling in your agent

Ensure your agent has proper timeout logic by injecting `ChaosTimeoutError`.

```python
import signal
from aumai_chaos import chaos_monkey, ChaosTimeoutError, FaultType

@chaos_monkey(fault_type=FaultType.timeout, probability=0.2)
def fetch_external_data(url: str) -> dict:
    """20% chance of simulated timeout."""
    # Real HTTP call here
    return {"data": "..."}


def agent_fetch_with_retry(url: str, max_retries: int = 3) -> dict | None:
    """Agent wrapper with retry logic — should handle timeouts gracefully."""
    for attempt in range(max_retries):
        try:
            return fetch_external_data(url)
        except ChaosTimeoutError:
            print(f"  Attempt {attempt + 1} timed out — retrying...")
    print("  All retries exhausted.")
    return None


# Verify the retry logic actually works under fault conditions
result = agent_fetch_with_retry("https://api.example.com/data")
print(f"Result: {result}")
```

### Pattern 2 — Multi-fault resilience testing with `@resilience_test`

Subject a function to a battery of faults simultaneously.

```python
from aumai_chaos import (
    resilience_test, FaultConfig, FaultType,
    ChaosError, ChaosTimeoutError, ResourceExhaustedError,
)

@resilience_test(faults=[
    FaultConfig(fault_type=FaultType.latency, probability=0.3, duration_ms=200),
    FaultConfig(fault_type=FaultType.error, probability=0.1, error_code=429,
                error_message="Rate limited"),
    FaultConfig(fault_type=FaultType.timeout, probability=0.05),
    FaultConfig(fault_type=FaultType.resource_exhaustion, probability=0.05),
])
def call_embedding_service(text: str) -> list[float]:
    """Embedding service call subjected to realistic fault conditions."""
    return [0.1, 0.2, 0.3]  # placeholder


def robust_embed(text: str) -> list[float] | None:
    """Demonstrate robust error handling around a fault-injected function."""
    try:
        return call_embedding_service(text)
    except ChaosError as exc:
        if exc.error_code == 429:
            print("  Rate limited — backing off")
        return None
    except (ChaosTimeoutError, ResourceExhaustedError):
        print("  Service unavailable — using fallback")
        return [0.0] * 3  # zero vector fallback
```

### Pattern 3 — Timed experiment with observation collection

Run a structured experiment and analyse the observations it produces.

```python
from aumai_chaos import (
    ChaosExperiment, ExperimentScheduler, ExperimentStatus,
    FaultConfig, FaultType,
)

experiment = ChaosExperiment(
    experiment_id="obs-test-001",
    name="Observation collection test",
    duration_seconds=5,
    target_components=["llm", "vector_db"],
    faults=[
        FaultConfig(
            fault_type=FaultType.latency,
            probability=0.4,
            duration_ms=150,
            affected_components=["llm"],
        ),
        FaultConfig(
            fault_type=FaultType.error,
            probability=0.15,
            error_code=503,
            error_message="Service degraded",
            affected_components=["vector_db"],
        ),
    ],
)

scheduler = ExperimentScheduler()
experiment_id = scheduler.schedule(experiment)
result = scheduler.run(experiment_id)

# Analyse the results
assert result.status == ExperimentStatus.completed
print(f"Total faults: {result.summary['total_faults_fired']}")
print(f"Faults by type: {result.summary['faults_by_type']}")
print(f"Errors by type: {result.summary['errors_by_type']}")

# Inspect individual observation points
for obs in result.observations[:5]:
    print(f"  [{obs.component}] {obs.event} at {obs.timestamp.isoformat()}")
```

### Pattern 4 — Use ExperimentObserver for custom instrumentation

Instrument your own code paths alongside chaos injection.

```python
from aumai_chaos import (
    ExperimentObserver, FaultInjector, FaultConfig, FaultType,
    ChaosError,
)

observer = ExperimentObserver()
injector = FaultInjector()

fault = FaultConfig(
    fault_type=FaultType.error,
    probability=0.25,
    error_code=500,
    error_message="Random failure",
)

def instrumented_tool_call(tool_name: str, payload: dict) -> dict | None:
    """Tool call with integrated observation and fault injection."""
    with observer.scope(tool_name, "tool_call"):
        try:
            injector.inject(fault)
            # Real tool invocation would go here
            result = {"output": f"{tool_name} succeeded"}
            observer.observe(tool_name, "result_received", {"output_keys": list(result.keys())})
            return result
        except ChaosError as exc:
            observer.observe(tool_name, "chaos_error", {"code": exc.error_code})
            return None


# Run several calls
for i in range(5):
    instrumented_tool_call("search_tool", {"query": f"query {i}"})

# Review observations
obs_list = observer.get_observations()
print(f"Recorded {len(obs_list)} observations:")
for obs in obs_list:
    print(f"  {obs.component} / {obs.event}: {obs.details}")
```

### Pattern 5 — Abort a long experiment from another thread

```python
import threading
import time
from aumai_chaos import (
    ChaosExperiment, ExperimentScheduler, ExperimentStatus,
    FaultConfig, FaultType,
)

long_experiment = ChaosExperiment(
    experiment_id="long-exp",
    name="Long experiment",
    duration_seconds=120,  # Would run for 2 minutes
    faults=[
        FaultConfig(fault_type=FaultType.latency, probability=0.3, duration_ms=200)
    ],
)

scheduler = ExperimentScheduler()
exp_id = scheduler.schedule(long_experiment)

# Run in a background thread
thread = threading.Thread(target=scheduler.run, args=(exp_id,), daemon=True)
thread.start()

# Abort after 3 seconds
time.sleep(3)
scheduler.abort(exp_id)
thread.join(timeout=5)

result = scheduler.get_result(exp_id)
print(f"Status: {result.status.value}")  # "aborted"
print(f"Ran for: {result.summary.get('duration_seconds', '?'):.1f}s")
```

---

## Troubleshooting FAQ

**Q: `aumai-chaos: command not found` after `pip install`**

A: Ensure your virtual environment's `bin/` directory is on your `PATH`. You can also
invoke the CLI with:

```bash
python -m aumai_chaos.cli --help
```

**Q: My `@chaos_monkey` decorator never fires even with `probability=1.0`**

A: Check that the import is from `aumai_chaos`, not a local module with the same name:

```python
from aumai_chaos import chaos_monkey  # correct
```

Also verify that `fault_type=FaultType.latency` is being passed, not a string. The
decorator accepts `FaultType` enum members, not raw strings.

**Q: `PyYAML required for YAML files` when running `aumai-chaos run`**

A: Install PyYAML:

```bash
pip install pyyaml
```

Or convert your experiment definition to JSON.

**Q: `ExperimentNotFoundError` from `scheduler.run(experiment_id)`**

A: You must call `scheduler.schedule(experiment)` before `scheduler.run(experiment_id)`.
The `schedule` call registers the experiment and returns its ID.

**Q: The experiment seems to run but zero faults are fired**

A: Check `FaultConfig.probability`. If it is `0.0`, faults will never fire. The
default is `1.0` (always fire). Also verify that `duration_seconds` is large enough
— if it is `1`, only one tick fires.

**Q: `ChaosTimeoutError` vs `TimeoutError` — which should I catch?**

A: `ChaosTimeoutError` is a subclass of `TimeoutError`. Catching `TimeoutError` will
also catch `ChaosTimeoutError`. Catching `ChaosTimeoutError` specifically will not
catch real `TimeoutError` exceptions from other sources. For testing that your agent
handles both real and simulated timeouts, catch `TimeoutError`.

**Q: Can I run multiple experiments concurrently on the same `ExperimentScheduler`?**

A: Yes. Each call to `scheduler.run(experiment_id)` creates its own isolated
`ExperimentObserver`. The abort flags are keyed by experiment ID so aborting one
experiment does not affect others. However, `run()` is synchronous — you need to
call it from separate threads for concurrent execution.

**Q: The `report` command exits with an error**

A: The `report` command notes that results are in-process only. The scheduler does
not persist results to disk. To save results, use:

```bash
aumai-chaos run --experiment my-exp.yaml --json-output > result.json
```

**Q: How do I seed the PRNG for reproducible fault injection in tests?**

A: Use `random.seed()` before calling code that exercises `FaultInjector.inject`:

```python
import random

def test_resilience_with_known_seed():
    random.seed(42)  # Makes should_inject() deterministic
    # ... run your test
```
