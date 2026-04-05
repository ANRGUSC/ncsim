"""
ncsim - Headless Discrete Event Simulator for Networked Computing Research

This package provides a deterministic DES for simulating DAG execution
on heterogeneous networked compute nodes.
"""

__version__ = "1.0.0"

from ncsim.core.simulation import Simulation
from ncsim.models.network import Node, Link, Network
from ncsim.models.dag import DAG, Edge, Task
from ncsim.io.scenario_loader import load_scenario

__all__ = [
    "Simulation",
    "Node",
    "Link",
    "Network",
    "DAG",
    "Edge",
    "Task",
    "load_scenario",
]
