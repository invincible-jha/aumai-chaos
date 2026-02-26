"""CLI entry point for aumai-chaos."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from aumai_chaos.core import FaultInjector
from aumai_chaos.models import (
    ChaosExperiment,
    FaultConfig,
    FaultType,
)
from aumai_chaos.scheduler import ExperimentNotFoundError, ExperimentScheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_experiment(path: str) -> ChaosExperiment:
    """Load a :class:`ChaosExperiment` from a YAML or JSON file."""
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    if file_path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
            data: dict[str, Any] = yaml.safe_load(raw)
        except ImportError:
            click.echo("PyYAML required for YAML files. Install: pip install pyyaml", err=True)
            sys.exit(1)
    else:
        data = json.loads(raw)
    return ChaosExperiment(**data)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
@click.version_option()
def main() -> None:
    """AumAI Chaos — fault injection for testing agent resilience."""


@main.command("run")
@click.option(
    "--experiment",
    "experiment_path",
    required=True,
    metavar="PATH",
    help="Path to experiment definition (YAML or JSON).",
)
@click.option("--json-output", is_flag=True, help="Emit results as JSON.")
def run_command(experiment_path: str, json_output: bool) -> None:
    """Run a chaos experiment defined in a YAML/JSON file."""
    try:
        experiment = _load_experiment(experiment_path)
    except Exception as exc:
        click.echo(f"Error loading experiment: {exc}", err=True)
        sys.exit(1)

    scheduler = ExperimentScheduler()
    experiment_id = scheduler.schedule(experiment)

    click.echo(
        f"Running experiment '{experiment.name}' "
        f"(id={experiment_id}) for {experiment.duration_seconds}s..."
    )

    try:
        result = scheduler.run(experiment_id)
    except Exception as exc:
        click.echo(f"Experiment failed: {exc}", err=True)
        sys.exit(1)

    if json_output:
        click.echo(result.model_dump_json(indent=2))
        return

    click.echo(f"\nStatus    : {result.status.value}")
    click.echo(f"Start     : {result.start_time.isoformat()}")
    click.echo(f"End       : {result.end_time.isoformat() if result.end_time else 'n/a'}")
    click.echo(f"Summary   :")
    for key, value in result.summary.items():
        click.echo(f"  {key}: {value}")
    click.echo(f"Observations: {len(result.observations)} recorded")


@main.command("inject")
@click.option(
    "--fault",
    "fault_type_str",
    required=True,
    type=click.Choice([f.value for f in FaultType], case_sensitive=False),
    help="Fault type to inject.",
)
@click.option("--duration", "duration_ms", default=500, show_default=True, help="Duration for latency faults (ms).")
@click.option("--error-code", default=500, show_default=True, help="Error code for error faults.")
@click.option("--message", default="Injected fault", show_default=True, help="Error message.")
@click.option("--target", "target_component", default="*", show_default=True, help="Target component label.")
def inject_command(
    fault_type_str: str,
    duration_ms: int,
    error_code: int,
    message: str,
    target_component: str,
) -> None:
    """Perform a one-off fault injection immediately."""
    fault_config = FaultConfig(
        fault_type=FaultType(fault_type_str),
        probability=1.0,
        duration_ms=duration_ms,
        error_code=error_code,
        error_message=message,
        affected_components=[target_component],
    )
    injector = FaultInjector()
    click.echo(
        f"Injecting '{fault_type_str}' fault into component '{target_component}'..."
    )
    try:
        injector.inject(fault_config)
        click.echo("Fault injection complete (no exception raised — e.g., latency).")
    except Exception as exc:
        click.echo(f"Fault raised: {type(exc).__name__}: {exc}")


@main.command("report")
@click.option("--experiment-id", required=True, help="ID of the experiment to report on.")
@click.option("--json-output", is_flag=True, help="Emit raw JSON.")
def report_command(experiment_id: str, json_output: bool) -> None:
    """Display the results of a completed chaos experiment.

    NOTE: results are in-process only. For persistent results, redirect
    the 'run' command output to a file with --json-output.
    """
    # The scheduler is in-process; in production this would query a store.
    click.echo(
        "Note: The scheduler is in-process. Results persist only within a session.\n"
        "Use `aumai-chaos run --json-output > result.json` to persist results.",
        err=True,
    )
    click.echo(f"No persistent result found for experiment-id: {experiment_id}")
    sys.exit(1)


if __name__ == "__main__":
    main()
