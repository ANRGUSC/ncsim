"""Unit tests for ncsim CLI main module."""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from ncsim.main import setup_logging, main
from ncsim.scheduler.saga_adapter import SAGA_AVAILABLE, SAGA_SCHEDULERS


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_sets_info_by_default(self):
        root = logging.getLogger()
        # Remove existing handlers so basicConfig takes effect
        for h in root.handlers[:]:
            root.removeHandler(h)
        root.setLevel(logging.WARNING)
        setup_logging(verbose=False)
        assert root.level == logging.INFO

    def test_sets_debug_when_verbose(self):
        root = logging.getLogger()
        for h in root.handlers[:]:
            root.removeHandler(h)
        root.setLevel(logging.WARNING)
        setup_logging(verbose=True)
        assert root.level == logging.DEBUG


class TestMain:
    """Tests for main() entry point."""

    def test_missing_args_exits(self):
        """Missing required args should raise SystemExit(2)."""
        with pytest.raises(SystemExit) as exc_info:
            main(args=[])
        assert exc_info.value.code == 2

    def test_nonexistent_scenario_returns_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(args=[
                "--scenario", "/nonexistent/scenario.yaml",
                "--output", tmpdir,
            ])
            assert result == 1

    def test_successful_run_round_robin(self):
        """round_robin scheduler works without SAGA dependency."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "round_robin",
            ])
            assert result == 0

    def test_writes_metrics_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "round_robin",
            ])
            metrics_path = Path(tmpdir) / "metrics.json"
            assert metrics_path.exists()
            data = json.loads(metrics_path.read_text())
            assert "makespan" in data
            assert "status" in data

    def test_writes_trace_jsonl(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "round_robin",
            ])
            trace_path = Path(tmpdir) / "trace.jsonl"
            assert trace_path.exists()
            assert trace_path.stat().st_size > 0

    def test_copies_scenario_yaml(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "round_robin",
            ])
            copied = Path(tmpdir) / "scenario.yaml"
            assert copied.exists()

    def test_malformed_yaml_returns_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write an invalid YAML scenario
            bad_yaml = Path(tmpdir) / "bad.yaml"
            bad_yaml.write_text("{{invalid yaml: [[[")
            result = main(args=[
                "--scenario", str(bad_yaml),
                "--output", tmpdir,
            ])
            assert result == 1

    @pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA library not installed")
    def test_heft_scheduler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "heft",
            ])
            assert result == 0

    @pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA library not installed")
    @pytest.mark.parametrize("algorithm", tuple(SAGA_SCHEDULERS))
    def test_every_registered_scheduler_through_cli(self, algorithm):
        with tempfile.TemporaryDirectory() as tmpdir:
            scenario_text = Path("scenarios/demo_simple.yaml").read_text()
            scenario_text = scenario_text.replace(
                "        latency: 0.001\n\n  dags:",
                "        latency: 0.001\n"
                "      - id: l10\n"
                "        from: n1\n"
                "        to: n0\n"
                "        bandwidth: 100\n"
                "        latency: 0.001\n\n  dags:",
            )
            scenario_path = Path(tmpdir) / "scenario.yaml"
            scenario_path.write_text(scenario_text)
            output_path = Path(tmpdir) / "output"
            result = main(args=[
                "--scenario", str(scenario_path),
                "--output", str(output_path),
                "--scheduler", algorithm,
            ])
            assert result == 0

    @pytest.mark.skipif(not SAGA_AVAILABLE, reason="SAGA library not installed")
    def test_scheduler_option_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "wba",
                "--scheduler-option", "alpha=0.75",
            ])
            assert result == 0

    def test_invalid_scheduler_option_returns_1(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = main(args=[
                "--scenario", "scenarios/demo_simple.yaml",
                "--output", tmpdir,
                "--scheduler", "round_robin",
                "--scheduler-option", "alpha=0.75",
            ])
            assert result == 1
