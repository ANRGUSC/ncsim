"""Unit tests for results writer."""

import json
import tempfile
from pathlib import Path

import pytest

from ncsim.core.simulation import SimulationResult
from ncsim.io.results_writer import write_results, read_results, compare_results


@pytest.fixture
def basic_result():
    """A minimal SimulationResult."""
    return SimulationResult(
        makespan=10.123456789,
        total_events=50,
        status="completed",
        node_utilization={"n0": 0.85678, "n1": 0.42345},
        link_utilization={"l01": 0.33367},
    )


@pytest.fixture
def error_result():
    """A SimulationResult with an error."""
    return SimulationResult(
        makespan=0.0,
        total_events=5,
        status="error",
        error_message="Deadlock detected",
        node_utilization={},
        link_utilization={},
    )


class TestWriteResults:
    """Tests for write_results function."""

    def test_writes_valid_json(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42)
            data = json.loads(path.read_text())
            assert isinstance(data, dict)

    def test_creates_parent_dirs(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "deep" / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42)
            assert path.exists()

    def test_output_has_required_fields(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42, total_tasks=5, total_transfers=3)
            data = json.loads(path.read_text())
            for key in ["scenario", "seed", "makespan", "total_tasks",
                         "total_transfers", "total_events", "status",
                         "node_utilization", "link_utilization"]:
                assert key in data, f"Missing key: {key}"

    def test_rounds_utilization_to_3_decimals(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42)
            data = json.loads(path.read_text())
            assert data["node_utilization"]["n0"] == 0.857
            assert data["node_utilization"]["n1"] == 0.423
            assert data["link_utilization"]["l01"] == 0.334

    def test_rounds_makespan(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42)
            data = json.loads(path.read_text())
            # round_time rounds to 6 decimals
            assert data["makespan"] == 10.123457

    def test_includes_error_message_when_present(self, error_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, error_result, "test.yaml", seed=1)
            data = json.loads(path.read_text())
            assert data["error_message"] == "Deadlock detected"

    def test_omits_error_message_when_none(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42)
            data = json.loads(path.read_text())
            assert "error_message" not in data

    def test_merges_extra_metrics(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            extra = {"rf_power": 20, "model": "csma"}
            write_results(path, basic_result, "test.yaml", seed=42, extra_metrics=extra)
            data = json.loads(path.read_text())
            assert data["rf_power"] == 20
            assert data["model"] == "csma"


class TestReadResults:
    """Tests for read_results function."""

    def test_roundtrip(self, basic_result):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            write_results(path, basic_result, "test.yaml", seed=42)
            data = read_results(path)
            assert data["scenario"] == "test.yaml"
            assert data["seed"] == 42

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            read_results(Path("/nonexistent/path/metrics.json"))


class TestCompareResults:
    """Tests for compare_results function."""

    def test_identical_match(self):
        r = {"makespan": 10.0, "total_tasks": 5, "status": "completed",
             "total_transfers": 3, "total_events": 50,
             "node_utilization": {"n0": 0.5}, "link_utilization": {"l01": 0.3}}
        result = compare_results(r, r)
        assert result["match"] is True
        assert result["differences"] == {}

    def test_detects_makespan_diff(self):
        r1 = {"makespan": 10.0, "total_tasks": 5, "status": "completed",
               "total_transfers": 3, "total_events": 50}
        r2 = {"makespan": 12.0, "total_tasks": 5, "status": "completed",
               "total_transfers": 3, "total_events": 50}
        result = compare_results(r1, r2)
        assert result["match"] is False
        assert "makespan" in result["differences"]

    def test_within_tolerance_matches(self):
        r1 = {"makespan": 10.0}
        r2 = {"makespan": 10.0 + 1e-8}
        result = compare_results(r1, r2, tolerance=1e-6)
        assert result["match"] is True

    def test_detects_status_diff(self):
        r1 = {"status": "completed"}
        r2 = {"status": "error"}
        result = compare_results(r1, r2)
        assert result["match"] is False
        assert "status" in result["differences"]

    def test_detects_node_utilization_diff(self):
        r1 = {"node_utilization": {"n0": 0.5}}
        r2 = {"node_utilization": {"n0": 0.9}}
        result = compare_results(r1, r2)
        assert result["match"] is False
        assert "node_utilization" in result["differences"]

    def test_handles_missing_keys_defaults_to_zero(self):
        r1 = {"node_utilization": {"n0": 0.5}}
        r2 = {"node_utilization": {}}
        result = compare_results(r1, r2)
        assert result["match"] is False
        # n0 missing in r2 defaults to 0.0, so diff detected
        assert "node_utilization" in result["differences"]
