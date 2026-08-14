"""
Unit tests for scenario loader.
"""

import pytest
import tempfile
from pathlib import Path

from ncsim.io.scenario_loader import load_scenario, validate_scenario


SIMPLE_SCENARIO = """
scenario:
  name: "Test Scenario"

  network:
    nodes:
      - id: n0
        compute_capacity: 100
        position: {x: 0, y: 0}
      - id: n1
        compute_capacity: 50
        position: {x: 10, y: 0}
    links:
      - id: l01
        from: n0
        to: n1
        bandwidth: 100
        latency: 0.001

  dags:
    - id: dag_1
      inject_at: 0.0
      tasks:
        - id: T0
          compute_cost: 100
        - id: T1
          compute_cost: 200
      edges:
        - from: T0
          to: T1
          data_size: 50

  config:
    scheduler: heft
    seed: 42
"""


class TestLoadScenario:
    """Tests for load_scenario function."""

    def test_loads_simple_scenario(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SIMPLE_SCENARIO)
            f.flush()

            scenario = load_scenario(f.name)

            assert scenario.name == "Test Scenario"
            assert len(scenario.network.nodes) == 2
            assert len(scenario.network.links) == 1
            assert len(scenario.dags) == 1
            assert scenario.config.scheduler == "heft"
            assert scenario.config.scheduler_options == {}
            assert scenario.config.seed == 42

    def test_loads_scheduler_options(self):
        scenario_yaml = SIMPLE_SCENARIO.replace(
            "scheduler: heft",
            "scheduler: wba\n    scheduler_options:\n      alpha: 0.75",
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_yaml)
            f.flush()

            scenario = load_scenario(f.name)

            assert scenario.config.scheduler == "wba"
            assert scenario.config.scheduler_options == {"alpha": 0.75}

    def test_rejects_non_mapping_scheduler_options(self):
        scenario_yaml = SIMPLE_SCENARIO.replace(
            "scheduler: heft",
            "scheduler: wba\n    scheduler_options: invalid",
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_yaml)
            f.flush()

            with pytest.raises(ValueError, match="scheduler_options must be a mapping"):
                load_scenario(f.name)

    def test_loads_network_correctly(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SIMPLE_SCENARIO)
            f.flush()

            scenario = load_scenario(f.name)
            network = scenario.network

            n0 = network.get_node("n0")
            assert n0.compute_capacity == 100
            assert n0.position.x == 0

            n1 = network.get_node("n1")
            assert n1.compute_capacity == 50

            link = network.get_link("l01")
            assert link.from_node == "n0"
            assert link.to_node == "n1"
            assert link.bandwidth == 100
            assert link.latency == 0.001

    def test_loads_dag_correctly(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SIMPLE_SCENARIO)
            f.flush()

            scenario = load_scenario(f.name)
            dag = scenario.dags[0]

            assert dag.id == "dag_1"
            assert dag.inject_at == 0.0
            assert len(dag.tasks) == 2
            assert len(dag.edges) == 1

            t0 = dag.get_task("T0")
            assert t0.compute_cost == 100

            t1 = dag.get_task("T1")
            assert t1.compute_cost == 200

    def test_computes_file_hash(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SIMPLE_SCENARIO)
            f.flush()

            scenario = load_scenario(f.name)

            assert scenario.file_hash is not None
            assert len(scenario.file_hash) == 16

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_scenario("/nonexistent/path.yaml")

    def test_raises_on_missing_network(self):
        scenario_no_network = """
scenario:
  name: "No Network"
  dags:
    - id: dag_1
      tasks:
        - id: T0
          compute_cost: 100
      edges: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_no_network)
            f.flush()

            with pytest.raises(ValueError, match="missing 'network'"):
                load_scenario(f.name)

    def test_raises_on_missing_dags(self):
        scenario_no_dags = """
scenario:
  name: "No DAGs"
  network:
    nodes:
      - id: n0
        compute_capacity: 100
    links: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_no_dags)
            f.flush()

            with pytest.raises(ValueError, match="missing 'dags'"):
                load_scenario(f.name)

    def test_uses_default_config(self):
        scenario_no_config = """
scenario:
  name: "No Config"
  network:
    nodes:
      - id: n0
        compute_capacity: 100
    links: []
  dags:
    - id: dag_1
      tasks:
        - id: T0
          compute_cost: 100
      edges: []
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(scenario_no_config)
            f.flush()

            scenario = load_scenario(f.name)

            assert scenario.config.scheduler == "heft"
            assert scenario.config.seed == 42


class TestValidateScenario:
    """Tests for validate_scenario function."""

    def test_valid_scenario_no_issues(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SIMPLE_SCENARIO)
            f.flush()

            scenario = load_scenario(f.name)
            issues = validate_scenario(scenario)

            assert len(issues) == 0
