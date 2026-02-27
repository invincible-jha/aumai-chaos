# API Reference — aumai-chaos

Complete reference for every public class, function, and Pydantic model.
All symbols are importable from the top-level package:

```python
from aumai_chaos import (
    FaultInjector, ExperimentScheduler, ExperimentObserver,
    chaos_monkey, resilience_test,
    ChaosError, ChaosTimeoutError, DataCorruptionError, ResourceExhaustedError,
    ChaosExperiment, ExperimentResult, ExperimentStatus,
    FaultConfig, FaultType, ObservationPoint,
)
```

---

## Enumerations

### `FaultType`

```python
class FaultType(str, Enum):
    latency             = "latency"
    error               = "error"
    timeout             = "timeout"
    partial_failure     = "partial_failure"
    resource_exhaustion = "resource_exhaustion"
    data_corruption     = "data_corruption"
```

Categories of injectable faults. Passed to `FaultConfig.fault_type` and to
`FaultInjector.inject`.

| Member | Exception raised | Notes |
|---|---|---|
| `latency` | None (blocks then returns) | Requires `duration_ms` in `FaultConfig` |
| `error` | `ChaosError` | Requires `error_code` in `FaultConfig` |
| `timeout` | `ChaosTimeoutError` | Simulates a hung operation |
| `partial_failure` | `RuntimeError("[partial_failure] …")` | Simulates degraded service |
| `resource_exhaustion` | `ResourceExhaustedError` | Simulates OOM / quota exceeded |
| `data_corruption` | `DataCorruptionError` | Simulates corrupted read/write |

---

### `ExperimentStatus`

```python
class ExperimentStatus(str, Enum):
    pending   = "pending"
    running   = "running"
    completed = "completed"
    aborted   = "aborted"
```

Lifecycle state of a chaos experiment run.

| Member | Description |
|---|---|
| `pending` | Scheduled but not yet started |
| `running` | Currently executing |
| `completed` | Ran to completion without abort |
| `aborted` | Stopped early via `ExperimentScheduler.abort` |

---

## Custom Exceptions

All exceptions are importable from `aumai_chaos`.

### `ChaosError`

```python
class ChaosError(RuntimeError):
    def __init__(self, error_code: int, message: str) -> None: ...
    error_code: int
```

Simulated application error injected by `FaultInjector.inject_error`.

**Attributes:**

| Attribute | Type | Description |
|---|---|---|
| `error_code` | `int` | The HTTP-style error code supplied at injection time |

**String representation:** `[{error_code}] {message}`

**Example:**

```python
from aumai_chaos import ChaosError, FaultInjector

injector = FaultInjector()
try:
    injector.inject_error(error_code=429, message="Rate limit exceeded")
except ChaosError as exc:
    print(exc.error_code)  # 429
    print(str(exc))        # [429] Rate limit exceeded
```

---

### `ChaosTimeoutError`

```python
class ChaosTimeoutError(TimeoutError):
    ...
```

Simulated timeout error. Subclass of the built-in `TimeoutError`. Raised by
`FaultInjector.inject_timeout`. Catchable with `except TimeoutError`.

---

### `ResourceExhaustedError`

```python
class ResourceExhaustedError(RuntimeError):
    ...
```

Simulated resource exhaustion. Raised by `FaultInjector.inject_resource_exhaustion`.
Use to test handling of out-of-memory conditions, rate limits, or quota exhaustion.

---

### `DataCorruptionError`

```python
class DataCorruptionError(ValueError):
    ...
```

Simulated data corruption. Subclass of `ValueError`. Raised by
`FaultInjector.inject_data_corruption`. Use to test data validation and recovery
code paths.

---

## Pydantic Models

---

### `FaultConfig`

```python
class FaultConfig(BaseModel):
    fault_type: FaultType
    probability: float           # Field(default=1.0, ge=0.0, le=1.0)
    duration_ms: int | None      # Field(default=None, ge=0)
    error_code: int | None       # default None
    error_message: str | None    # default None
    affected_components: list[str]  # default_factory=list
```

Declarative specification for a single injectable fault.

| Field | Type | Default | Description |
|---|---|---|---|
| `fault_type` | `FaultType` | required | Which fault to inject |
| `probability` | `float` | `1.0` | Fraction of invocations that fire; 0.0 = never, 1.0 = always |
| `duration_ms` | `int \| None` | `None` | Sleep duration for `latency` faults; required when `fault_type=latency` |
| `error_code` | `int \| None` | `None` | Error code stored in `ChaosError`; required when `fault_type=error` |
| `error_message` | `str \| None` | `None` | Error message for `error` and `partial_failure` faults |
| `affected_components` | `list[str]` | `[]` | Component labels; used for observation tagging and experiment targeting |

**Example:**

```python
from aumai_chaos import FaultConfig, FaultType

# 200ms latency, fires 30% of the time
latency_fault = FaultConfig(
    fault_type=FaultType.latency,
    probability=0.3,
    duration_ms=200,
    affected_components=["tool_executor"],
)

# 503 error, fires 10% of the time
error_fault = FaultConfig(
    fault_type=FaultType.error,
    probability=0.1,
    error_code=503,
    error_message="Upstream service unavailable",
)
```

---

### `ChaosExperiment`

```python
class ChaosExperiment(BaseModel):
    experiment_id: str
    name: str
    description: str             # default ""
    faults: list[FaultConfig]   # default_factory=list
    duration_seconds: int        # Field(default=60, gt=0)
    target_components: list[str]  # default_factory=list
```

A named collection of faults to be injected against target components for a fixed
duration. Passed to `ExperimentScheduler.schedule`.

| Field | Type | Default | Description |
|---|---|---|---|
| `experiment_id` | `str` | required | Unique identifier; preserved by `schedule` if present |
| `name` | `str` | required | Human-readable name |
| `description` | `str` | `""` | Optional notes |
| `faults` | `list[FaultConfig]` | `[]` | Faults to inject on each tick |
| `duration_seconds` | `int > 0` | `60` | How long to run |
| `target_components` | `list[str]` | `[]` | Default targets used when a fault's `affected_components` is empty |

---

### `ObservationPoint`

```python
class ObservationPoint(BaseModel):
    timestamp: datetime
    component: str
    event: str
    details: dict[str, object]   # default_factory=dict
```

A single timestamped observation recorded by `ExperimentObserver.observe`.

| Field | Type | Description |
|---|---|---|
| `timestamp` | `datetime` | UTC timestamp when the observation was recorded |
| `component` | `str` | The component being observed (e.g. `"llm_tool_call"`) |
| `event` | `str` | Short event label (e.g. `"latency_injected"`) |
| `details` | `dict[str, object]` | Arbitrary structured detail data |

---

### `ExperimentResult`

```python
class ExperimentResult(BaseModel):
    experiment: ChaosExperiment
    status: ExperimentStatus
    start_time: datetime
    end_time: datetime | None    # default None
    observations: list[ObservationPoint]  # default_factory=list
    summary: dict[str, object]  # default_factory=dict
```

Complete record of a chaos experiment run. Returned by `ExperimentScheduler.run`.

| Field | Type | Description |
|---|---|---|
| `experiment` | `ChaosExperiment` | The experiment that was run |
| `status` | `ExperimentStatus` | Final status |
| `start_time` | `datetime` | UTC start time |
| `end_time` | `datetime \| None` | UTC end time; `None` if still running |
| `observations` | `list[ObservationPoint]` | All observations from the run |
| `summary` | `dict[str, object]` | Aggregate counts; see keys below |

**`summary` keys** (populated by `ExperimentScheduler.run`):

| Key | Type | Description |
|---|---|---|
| `total_faults_fired` | `int` | Sum of all faults injected |
| `faults_by_type` | `dict[str, int]` | Per-fault-type injection counts |
| `errors_by_type` | `dict[str, int]` | Per-fault-type exception counts |
| `duration_seconds` | `float` | Actual elapsed time |

---

## Classes

### `FaultInjector`

```python
class FaultInjector:
    def inject_latency(self, duration_ms: int) -> None: ...
    def inject_error(self, error_code: int, message: str) -> None: ...
    def inject_timeout(self) -> None: ...
    def inject_partial_failure(self, message: str = "Partial failure") -> None: ...
    def inject_resource_exhaustion(self, message: str = "Resource exhausted") -> None: ...
    def inject_data_corruption(self, message: str = "Data corrupted") -> None: ...
    def should_inject(self, probability: float) -> bool: ...
    def inject(self, config: FaultConfig) -> None: ...
```

Dispatches and applies individual fault types. All methods are synchronous.

---

#### `FaultInjector.inject_latency`

```python
def inject_latency(self, duration_ms: int) -> None
```

Block the current thread for `duration_ms` milliseconds using `time.sleep`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `duration_ms` | `int` | Sleep duration in milliseconds |

---

#### `FaultInjector.inject_error`

```python
def inject_error(self, error_code: int, message: str) -> None
```

Raise a `ChaosError` with `error_code` and `message`.

**Raises:** `ChaosError`

---

#### `FaultInjector.inject_timeout`

```python
def inject_timeout(self) -> None
```

Raise a `ChaosTimeoutError` to simulate a hung operation.

**Raises:** `ChaosTimeoutError`

---

#### `FaultInjector.inject_partial_failure`

```python
def inject_partial_failure(self, message: str = "Partial failure") -> None
```

Raise a `RuntimeError` with `[partial_failure]` prefix to simulate service degradation.

**Raises:** `RuntimeError`

---

#### `FaultInjector.inject_resource_exhaustion`

```python
def inject_resource_exhaustion(self, message: str = "Resource exhausted") -> None
```

Raise a `ResourceExhaustedError`.

**Raises:** `ResourceExhaustedError`

---

#### `FaultInjector.inject_data_corruption`

```python
def inject_data_corruption(self, message: str = "Data corrupted") -> None
```

Raise a `DataCorruptionError`.

**Raises:** `DataCorruptionError`

---

#### `FaultInjector.should_inject`

```python
def should_inject(self, probability: float) -> bool
```

Return `True` with the given `probability` using `random.random()`.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `probability` | `float` | Value in `[0.0, 1.0]`; `0.0` always returns `False`, `1.0` always returns `True` |

**Returns:** `bool`

---

#### `FaultInjector.inject`

```python
def inject(self, config: FaultConfig) -> None
```

Dispatch to the appropriate injection method based on `config.fault_type`. Respects
`config.probability` — if the RNG decides not to fire, returns without raising or
sleeping.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `config` | `FaultConfig` | The fault specification |

**Raises:**
- `ValueError` if `config.fault_type == FaultType.latency` and `config.duration_ms` is `None`.
- `ValueError` if `config.fault_type == FaultType.error` and `config.error_code` is `None`.
- The appropriate chaos exception for all other fault types (when the probability check passes).

**Example:**

```python
from aumai_chaos import FaultInjector, FaultConfig, FaultType

injector = FaultInjector()

config = FaultConfig(
    fault_type=FaultType.latency,
    probability=0.5,
    duration_ms=300,
)

# Fires ~50% of calls; no-op the other ~50%
injector.inject(config)
```

---

### `ExperimentScheduler`

```python
class ExperimentScheduler:
    def __init__(self) -> None: ...

    def schedule(self, experiment: ChaosExperiment) -> str: ...
    def run(self, experiment_id: str) -> ExperimentResult: ...
    def abort(self, experiment_id: str) -> None: ...
    def get_result(self, experiment_id: str) -> ExperimentResult | None: ...
```

Schedules, runs, and aborts chaos experiments. Results are held in-process memory.

---

#### `ExperimentScheduler.__init__`

No parameters. Initialises internal state: experiment registry, result cache, abort
flags, and a shared `FaultInjector`.

---

#### `ExperimentScheduler.schedule`

```python
def schedule(self, experiment: ChaosExperiment) -> str
```

Register `experiment` and return its `experiment_id`. If the experiment already has
an ID it is preserved; otherwise a new UUID4 is assigned.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `experiment` | `ChaosExperiment` | The experiment to register |

**Returns:** `str` — the `experiment_id` (new or existing).

---

#### `ExperimentScheduler.run`

```python
def run(self, experiment_id: str) -> ExperimentResult
```

Execute the scheduled experiment synchronously. Runs for `experiment.duration_seconds`,
injecting faults on 1-second ticks until the duration elapses or `abort` is called.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `experiment_id` | `str` | The ID returned by `schedule` |

**Returns:** `ExperimentResult` with `status`, `observations`, and `summary`.

**Raises:** `ExperimentNotFoundError` (subclass of `KeyError`) if `experiment_id` was
not registered via `schedule`.

---

#### `ExperimentScheduler.abort`

```python
def abort(self, experiment_id: str) -> None
```

Signal the running experiment to stop at the next 1-second tick. Thread-safe.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `experiment_id` | `str` | ID of the experiment to abort |

**Raises:** `ExperimentNotFoundError` if `experiment_id` is unknown.

---

#### `ExperimentScheduler.get_result`

```python
def get_result(self, experiment_id: str) -> ExperimentResult | None
```

Return the latest `ExperimentResult` for `experiment_id`, or `None` if no result
is available yet (experiment not yet started or not found).

---

### `ExperimentObserver`

```python
class ExperimentObserver:
    def __init__(self) -> None: ...

    def observe(
        self,
        component: str,
        event: str,
        details: dict[str, object] | None = None,
    ) -> None: ...

    def get_observations(self) -> list[ObservationPoint]: ...
    def clear(self) -> None: ...

    @contextmanager
    def scope(
        self, component: str, event_prefix: str = ""
    ) -> Generator[None, None, None]: ...
```

Collects timestamped observation points. Thread-safe via `threading.Lock`.

---

#### `ExperimentObserver.observe`

```python
def observe(
    self,
    component: str,
    event: str,
    details: dict[str, object] | None = None,
) -> None
```

Record a single `ObservationPoint` with the current UTC timestamp.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `component` | `str` | Component label (e.g. `"llm_tool_call"`) |
| `event` | `str` | Short event label (e.g. `"latency_injected"`) |
| `details` | `dict \| None` | Optional structured detail data |

---

#### `ExperimentObserver.get_observations`

```python
def get_observations(self) -> list[ObservationPoint]
```

Return a shallow copy of all recorded observations, taken under the lock.

---

#### `ExperimentObserver.clear`

```python
def clear(self) -> None
```

Discard all recorded observations. Thread-safe.

---

#### `ExperimentObserver.scope`

```python
@contextmanager
def scope(
    self, component: str, event_prefix: str = ""
) -> Generator[None, None, None]
```

Context manager that automatically records `{event_prefix}_start` on enter and
`{event_prefix}_end` on successful exit, or `{event_prefix}_error` with exception
details on failure. The exception is always re-raised.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `component` | `str` | Component label for all recorded events |
| `event_prefix` | `str` | Prefix for the auto-generated event labels; empty string gives `"start"`, `"end"`, `"error"` |

**Example:**

```python
from aumai_chaos import ExperimentObserver

observer = ExperimentObserver()

with observer.scope("database", "query"):
    run_query()  # records "query_start" and "query_end" (or "query_error")

# Minimal (no prefix)
with observer.scope("cache"):
    fetch_from_cache()  # records "start" and "end"
```

---

## Decorator Functions

### `chaos_monkey`

```python
def chaos_monkey(
    fault_type: FaultType = FaultType.latency,
    probability: float = 0.1,
    duration_ms: int = 500,
    error_code: int = 500,
    error_message: str = "Chaos monkey error",
    affected_components: list[str] | None = None,
) -> Callable[[F], F]
```

Decorator factory that randomly injects a single fault before each call to the
wrapped function.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `fault_type` | `FaultType` | `latency` | The fault type to inject |
| `probability` | `float` | `0.1` | Probability that a fault fires per call |
| `duration_ms` | `int` | `500` | Duration for latency faults in ms |
| `error_code` | `int` | `500` | Error code for error faults |
| `error_message` | `str` | `"Chaos monkey error"` | Message for error faults |
| `affected_components` | `list[str] \| None` | `None` | Component labels |

The `FaultConfig` and `FaultInjector` are created once at decoration time.

**Example:**

```python
from aumai_chaos import chaos_monkey, FaultType

@chaos_monkey(fault_type=FaultType.latency, probability=0.2, duration_ms=300)
def call_tool(payload: dict) -> dict:
    return {"status": "ok"}
```

---

### `resilience_test`

```python
def resilience_test(
    faults: list[FaultConfig],
) -> Callable[[F], F]
```

Decorator factory that applies a list of faults in sequence before each function
call. Each fault's probability is evaluated independently.

**Parameters:**

| Parameter | Type | Description |
|---|---|---|
| `faults` | `list[FaultConfig]` | Ordered list of fault configs to evaluate |

A single `FaultInjector` is created at decoration time and shared across all calls.

**Example:**

```python
from aumai_chaos import resilience_test, FaultConfig, FaultType

@resilience_test(faults=[
    FaultConfig(fault_type=FaultType.latency, probability=0.3, duration_ms=100),
    FaultConfig(fault_type=FaultType.error, probability=0.05, error_code=503),
])
def fetch_context(query: str) -> str:
    return "context"
```

---

## `ExperimentNotFoundError`

```python
class ExperimentNotFoundError(KeyError):
    ...
```

Raised by `ExperimentScheduler.run` and `ExperimentScheduler.abort` when the given
`experiment_id` has not been registered with `schedule`. Importable from
`aumai_chaos.scheduler`.
