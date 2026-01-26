"""
Results/metrics writer for simulation output.

Writes metrics.json per CLAUDE.md section 8.2 specification.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Any, Optional

from ncsim.core.event_queue import round_time
from ncsim.core.simulation import SimulationResult


def write_results(
    output_path: Path,
    result: SimulationResult,
    scenario_name: str,
    seed: int,
    total_tasks: int = 0,
    total_transfers: int = 0
) -> None:
    """Write simulation results to a JSON file.

    Args:
        output_path: Path to output file
        result: SimulationResult from simulation
        scenario_name: Name of the scenario file
        seed: Random seed used
        total_tasks: Number of tasks in DAG(s)
        total_transfers: Number of data transfers
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metrics = {
        "scenario": scenario_name,
        "seed": seed,
        "makespan": round_time(result.makespan),
        "total_tasks": total_tasks,
        "total_transfers": total_transfers,
        "total_events": result.total_events,
        "status": result.status,
        "node_utilization": {
            node_id: round(util, 3)
            for node_id, util in result.node_utilization.items()
        },
        "link_utilization": {
            link_id: round(util, 3)
            for link_id, util in result.link_utilization.items()
        }
    }

    if result.error_message:
        metrics["error_message"] = result.error_message

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)


def read_results(path: Path) -> Dict[str, Any]:
    """Read results from a JSON file.

    Args:
        path: Path to metrics file

    Returns:
        Dictionary of metrics
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_results(
    result1: Dict[str, Any],
    result2: Dict[str, Any],
    tolerance: float = 1e-6
) -> Dict[str, Any]:
    """Compare two result sets for differences.

    Args:
        result1: First result set
        result2: Second result set
        tolerance: Tolerance for floating-point comparison

    Returns:
        Dictionary with comparison results
    """
    differences = {}

    # Check scalar fields
    for key in ["makespan", "total_tasks", "total_transfers", "total_events", "status"]:
        v1 = result1.get(key)
        v2 = result2.get(key)
        if isinstance(v1, float) and isinstance(v2, float):
            if abs(v1 - v2) > tolerance:
                differences[key] = {"expected": v1, "actual": v2}
        elif v1 != v2:
            differences[key] = {"expected": v1, "actual": v2}

    # Check node utilization
    nu1 = result1.get("node_utilization", {})
    nu2 = result2.get("node_utilization", {})
    nu_diff = {}
    for node_id in set(nu1.keys()) | set(nu2.keys()):
        u1 = nu1.get(node_id, 0.0)
        u2 = nu2.get(node_id, 0.0)
        if abs(u1 - u2) > tolerance:
            nu_diff[node_id] = {"expected": u1, "actual": u2}
    if nu_diff:
        differences["node_utilization"] = nu_diff

    # Check link utilization
    lu1 = result1.get("link_utilization", {})
    lu2 = result2.get("link_utilization", {})
    lu_diff = {}
    for link_id in set(lu1.keys()) | set(lu2.keys()):
        u1 = lu1.get(link_id, 0.0)
        u2 = lu2.get(link_id, 0.0)
        if abs(u1 - u2) > tolerance:
            lu_diff[link_id] = {"expected": u1, "actual": u2}
    if lu_diff:
        differences["link_utilization"] = lu_diff

    return {
        "match": len(differences) == 0,
        "differences": differences
    }
