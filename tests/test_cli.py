"""Tests for aumai_chaos.cli — Click command interface."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from aumai_chaos.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_experiment_json(tmp_path: Path, data: dict[object, object]) -> Path:
    """Write a JSON experiment definition and return the path."""
    file_path = tmp_path / "experiment.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")
    return file_path


_MINIMAL_EXPERIMENT: dict[str, object] = {
    "experiment_id": "cli-test",
    "name": "CLI Test Experiment",
    "description": "Used in CLI tests",
    "faults": [],
    "duration_seconds": 1,
    "target_components": [],
}


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class TestVersionFlag:
    def test_version_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_version_contains_expected_string(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert "0.1.0" in result.output


# ---------------------------------------------------------------------------
# --help
# ---------------------------------------------------------------------------


class TestHelpFlag:
    def test_help_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_help_lists_subcommands(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "run" in result.output
        assert "inject" in result.output
        assert "report" in result.output


# ---------------------------------------------------------------------------
# run command
# ---------------------------------------------------------------------------


class TestRunCommand:
    def test_run_no_experiment_flag_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["run"])
        assert result.exit_code != 0

    def test_run_missing_file_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--experiment", "/nonexistent/path.json"])
        assert result.exit_code != 0

    def test_run_valid_json_experiment_succeeds(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(main, ["run", "--experiment", str(exp_path)])
        assert result.exit_code == 0, result.output

    def test_run_prints_experiment_name(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(main, ["run", "--experiment", str(exp_path)])
        assert "CLI Test Experiment" in result.output

    def test_run_prints_status(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(main, ["run", "--experiment", str(exp_path)])
        assert "completed" in result.output

    def test_run_json_output_flag_emits_valid_json(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(
            main, ["run", "--experiment", str(exp_path), "--json-output"]
        )
        assert result.exit_code == 0, result.output
        # The CLI prints a "Running …" preamble before the JSON block.
        # Extract the JSON portion by finding the first '{'.
        json_start = result.output.index("{")
        parsed = json.loads(result.output[json_start:])
        assert "status" in parsed
        assert "experiment" in parsed

    def test_run_json_output_contains_summary(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(
            main, ["run", "--experiment", str(exp_path), "--json-output"]
        )
        json_start = result.output.index("{")
        parsed = json.loads(result.output[json_start:])
        assert "summary" in parsed

    def test_run_invalid_json_exits_nonzero(self, tmp_path: Path) -> None:
        runner = CliRunner()
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON AT ALL", encoding="utf-8")
        result = runner.invoke(main, ["run", "--experiment", str(bad_file)])
        assert result.exit_code != 0

    def test_run_yaml_experiment_when_pyyaml_unavailable(
        self, tmp_path: Path
    ) -> None:
        """When PyYAML is not installed, the CLI should exit non-zero and report it."""
        from unittest.mock import patch

        yaml_content = (
            "experiment_id: yaml-test\n"
            "name: YAML Experiment\n"
            "faults: []\n"
            "duration_seconds: 1\n"
            "target_components: []\n"
        )
        yaml_file = tmp_path / "experiment.yaml"
        yaml_file.write_text(yaml_content, encoding="utf-8")

        runner = CliRunner()
        # Simulate PyYAML not being importable by patching builtins.__import__
        _builtins = __builtins__
        real_import = (  # type: ignore[union-attr]
            _builtins.__import__  # type: ignore[union-attr]
            if hasattr(_builtins, "__import__")
            else __import__
        )

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)  # type: ignore[call-arg]

        with patch("builtins.__import__", side_effect=fake_import):
            result = runner.invoke(main, ["run", "--experiment", str(yaml_file)])

        assert result.exit_code != 0

    def test_run_scheduler_exception_exits_nonzero(self, tmp_path: Path) -> None:
        """When scheduler.run raises an unexpected exception, the CLI exits non-zero."""
        from unittest.mock import patch

        from aumai_chaos.scheduler import ExperimentScheduler

        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        runner = CliRunner()

        with patch.object(
            ExperimentScheduler,
            "run",
            side_effect=RuntimeError("unexpected scheduler failure"),
        ):
            result = runner.invoke(main, ["run", "--experiment", str(exp_path)])

        assert result.exit_code != 0

    def test_run_prints_observation_count(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(main, ["run", "--experiment", str(exp_path)])
        assert "Observations" in result.output

    def test_run_reports_experiment_id_in_output(self, tmp_path: Path) -> None:
        runner = CliRunner()
        exp_path = _write_experiment_json(tmp_path, _MINIMAL_EXPERIMENT)
        result = runner.invoke(main, ["run", "--experiment", str(exp_path)])
        assert "cli-test" in result.output


# ---------------------------------------------------------------------------
# inject command
# ---------------------------------------------------------------------------


class TestInjectCommand:
    def test_inject_latency_exits_zero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["inject", "--fault", "latency", "--duration", "10"],
        )
        assert result.exit_code == 0, result.output

    def test_inject_latency_prints_component(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["inject", "--fault", "latency", "--duration", "10", "--target", "my_svc"],
        )
        assert "my_svc" in result.output

    def test_inject_error_prints_exception(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "inject",
                "--fault",
                "error",
                "--error-code",
                "503",
                "--message",
                "kaboom",
            ],
        )
        assert result.exit_code == 0
        assert "ChaosError" in result.output

    def test_inject_timeout_prints_exception(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["inject", "--fault", "timeout"])
        assert result.exit_code == 0
        assert "ChaosTimeoutError" in result.output

    def test_inject_partial_failure_prints_exception(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["inject", "--fault", "partial_failure"])
        assert result.exit_code == 0
        assert "RuntimeError" in result.output

    def test_inject_resource_exhaustion_prints_exception(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["inject", "--fault", "resource_exhaustion"])
        assert result.exit_code == 0
        assert "ResourceExhaustedError" in result.output

    def test_inject_data_corruption_prints_exception(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["inject", "--fault", "data_corruption"])
        assert result.exit_code == 0
        assert "DataCorruptionError" in result.output

    def test_inject_missing_fault_flag_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["inject"])
        assert result.exit_code != 0

    def test_inject_invalid_fault_type_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["inject", "--fault", "not_a_fault"])
        assert result.exit_code != 0

    def test_inject_latency_completion_message(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["inject", "--fault", "latency", "--duration", "5"],
        )
        assert "complete" in result.output.lower()


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


class TestReportCommand:
    def test_report_always_exits_nonzero(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["report", "--experiment-id", "any-id"])
        assert result.exit_code != 0

    def test_report_missing_id_flag_fails(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["report"])
        assert result.exit_code != 0

    def test_report_prints_in_process_note(self) -> None:
        # CliRunner mixes stdout and stderr into result.output by default.
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--experiment-id", "some-id"],
        )
        # The "in-process" note is written via click.echo(…, err=True) which
        # appears in the combined output captured by CliRunner.
        assert "in-process" in result.output.lower()
