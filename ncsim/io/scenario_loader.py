"""
Scenario loader for YAML configuration files.

Parses scenario YAML files and creates Network/DAG objects.
"""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple

import yaml

from ncsim.models.network import Node, Link, Network, Position
from ncsim.models.task import Task
from ncsim.models.dag import DAG, Edge


@dataclass
class ScenarioConfig:
    """Configuration section of a scenario.

    Attributes:
        scheduler: Scheduling algorithm to use ("heft", "cpop", "round_robin")
        seed: Random seed for reproducibility
        routing: Routing algorithm to use ("direct", "widest_path", or "shortest_path")
        interference: Interference model type ("none", "proximity", "csma_clique", "csma_bianchi")
        interference_radius: Radius for proximity interference model
        rf_config: Raw dict of RF parameters for WiFi models (from YAML rf: section)
    """
    scheduler: str = "heft"
    seed: int = 42
    routing: str = "direct"
    interference: str = "proximity"
    interference_radius: float = 15.0
    rf_config: Optional[Dict[str, Any]] = None


@dataclass
class Scenario:
    """A complete simulation scenario.

    Attributes:
        name: Human-readable scenario name
        network: Network topology
        dags: List of DAGs to simulate
        config: Scenario configuration
        file_path: Path to source YAML file
        file_hash: SHA256 hash of scenario file
        explicit_bandwidth_links: Link IDs that had bandwidth specified in YAML
    """
    name: str
    network: Network
    dags: List[DAG]
    config: ScenarioConfig
    file_path: Optional[str] = None
    file_hash: Optional[str] = None
    explicit_bandwidth_links: Set[str] = field(default_factory=set)


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        hasher.update(f.read())
    return hasher.hexdigest()[:16]  # First 16 chars for brevity


def _parse_position(pos_data: Optional[Dict]) -> Position:
    """Parse position from YAML dict."""
    if pos_data is None:
        return Position(0.0, 0.0)
    return Position(
        x=float(pos_data.get("x", 0.0)),
        y=float(pos_data.get("y", 0.0))
    )


def _parse_nodes(nodes_data: List[Dict]) -> Dict[str, Node]:
    """Parse nodes from YAML list."""
    nodes = {}
    for node_data in nodes_data:
        node_id = str(node_data["id"])
        node = Node(
            id=node_id,
            compute_capacity=float(node_data["compute_capacity"]),
            position=_parse_position(node_data.get("position"))
        )
        nodes[node_id] = node
    return nodes


def _parse_links(links_data: List[Dict]) -> Tuple[Dict[str, Link], Set[str]]:
    """Parse links from YAML list.

    Returns:
        Tuple of (links dict, set of link IDs with explicit bandwidth).
        Links without explicit bandwidth get a placeholder of 1.0 MB/s
        (to be overwritten by WiFi model before simulation starts).
    """
    links = {}
    explicit_bw: Set[str] = set()
    for link_data in links_data:
        link_id = str(link_data["id"])
        has_bw = "bandwidth" in link_data
        bandwidth = float(link_data["bandwidth"]) if has_bw else 1.0
        link = Link(
            id=link_id,
            from_node=str(link_data["from"]),
            to_node=str(link_data["to"]),
            bandwidth=bandwidth,
            latency=float(link_data.get("latency", 0.0))
        )
        links[link_id] = link
        if has_bw:
            explicit_bw.add(link_id)
    return links, explicit_bw


def _parse_network(network_data: Dict) -> Tuple[Network, Set[str]]:
    """Parse network topology from YAML.

    Returns:
        Tuple of (Network, set of link IDs with explicit bandwidth).
    """
    nodes = _parse_nodes(network_data.get("nodes", []))
    links, explicit_bw = _parse_links(network_data.get("links", []))
    return Network(nodes=nodes, links=links), explicit_bw


def _parse_tasks(tasks_data: List[Dict], dag_id: str) -> Dict[str, Task]:
    """Parse tasks from YAML list."""
    tasks = {}
    for task_data in tasks_data:
        task_id = str(task_data["id"])
        task = Task(
            id=task_id,
            compute_cost=float(task_data["compute_cost"]),
            dag_id=dag_id,
            pinned_to=task_data.get("pinned_to")
        )
        tasks[task_id] = task
    return tasks


def _parse_edges(edges_data: List[Dict]) -> List[Edge]:
    """Parse edges from YAML list."""
    edges = []
    for edge_data in edges_data:
        edge = Edge(
            from_task=str(edge_data["from"]),
            to_task=str(edge_data["to"]),
            data_size=float(edge_data["data_size"])
        )
        edges.append(edge)
    return edges


def _parse_dag(dag_data: Dict) -> DAG:
    """Parse a single DAG from YAML."""
    dag_id = str(dag_data["id"])
    tasks = _parse_tasks(dag_data.get("tasks", []), dag_id)
    edges = _parse_edges(dag_data.get("edges", []))
    inject_at = float(dag_data.get("inject_at", 0.0))

    return DAG(
        id=dag_id,
        tasks=tasks,
        edges=edges,
        inject_at=inject_at
    )


def _parse_dags(dags_data: List[Dict]) -> List[DAG]:
    """Parse DAGs from YAML list."""
    return [_parse_dag(dag_data) for dag_data in dags_data]


def _parse_config(config_data: Optional[Dict]) -> ScenarioConfig:
    """Parse configuration from YAML."""
    if config_data is None:
        return ScenarioConfig()

    return ScenarioConfig(
        scheduler=str(config_data.get("scheduler", "heft")),
        seed=int(config_data.get("seed", 42)),
        routing=str(config_data.get("routing", "direct")),
        interference=str(config_data.get("interference", "proximity")),
        interference_radius=float(config_data.get("interference_radius", 15.0)),
        rf_config=config_data.get("rf"),
    )


def load_scenario(file_path: str) -> Scenario:
    """Load a scenario from a YAML file.

    Args:
        file_path: Path to the scenario YAML file

    Returns:
        Parsed Scenario object

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If YAML is invalid or missing required fields
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Scenario file not found: {file_path}")

    # Compute hash for reproducibility tracking
    file_hash = _compute_file_hash(path)

    # Load YAML
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f"Empty scenario file: {file_path}")

    # Extract scenario root (may be nested under 'scenario' key)
    scenario_data = data.get("scenario", data)

    # Parse name
    name = str(scenario_data.get("name", path.stem))

    # Parse network
    network_data = scenario_data.get("network")
    if network_data is None:
        raise ValueError(f"Scenario missing 'network' section: {file_path}")
    network, explicit_bw_links = _parse_network(network_data)

    # Parse DAGs
    dags_data = scenario_data.get("dags", [])
    if not dags_data:
        raise ValueError(f"Scenario missing 'dags' section: {file_path}")
    dags = _parse_dags(dags_data)

    # Parse config
    config_data = scenario_data.get("config")
    config = _parse_config(config_data)

    return Scenario(
        name=name,
        network=network,
        dags=dags,
        config=config,
        file_path=str(path.absolute()),
        file_hash=file_hash,
        explicit_bandwidth_links=explicit_bw_links,
    )


def validate_scenario(scenario: Scenario) -> List[str]:
    """Validate a scenario for common issues.

    Returns:
        List of warning/error messages (empty if valid)
    """
    issues = []

    # Check for disconnected nodes (nodes not referenced in DAG assignments)
    # This is just a warning, not an error

    # Check DAG structure
    for dag in scenario.dags:
        # Check for cycles (should raise in DAG.__post_init__)
        try:
            dag.topological_order()
        except ValueError as e:
            issues.append(str(e))

        # Check for orphan tasks
        root_tasks = dag.get_root_tasks()
        if not root_tasks:
            issues.append(f"DAG {dag.id}: no root tasks (entry points)")

        # Check edges reference nodes in network for transfer feasibility
        # (This is informational - transfers will just use routing model)

    return issues
