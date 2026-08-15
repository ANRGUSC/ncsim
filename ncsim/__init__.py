"""Lightweight simulation of DAG scheduling over networked systems.

ncsim provides a deterministic discrete-event simulator for heterogeneous
compute nodes, multi-hop networks, and realistic Wi-Fi interference.
"""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("anrg-ncsim")
except PackageNotFoundError:
    # A source checkout is expected to be installed (normally with
    # ``pip install -e .``), but keep imports usable for tooling that reads the
    # package before installation.
    __version__ = "0+unknown"

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
    "__version__",
]
