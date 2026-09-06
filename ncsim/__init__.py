"""Lightweight simulation of DAG scheduling over networked systems.

ncsim provides a deterministic discrete-event simulator for heterogeneous
compute nodes, multi-hop networks, and realistic Wi-Fi interference.
"""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib


try:
    __version__ = version("anrg-ncsim")
except PackageNotFoundError:
    # A source checkout is expected to be installed (normally with
    # ``pip install -e .``), but keep imports usable for tooling that reads the
    # package before installation.
    __version__ = "0+unknown"

# Prefer the adjacent project metadata when importing directly from a source
# checkout. This prevents a different globally installed ncsim release from
# leaking its version into local experiments and tests.
_source_pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
if _source_pyproject.is_file():
    with _source_pyproject.open("rb") as _source_handle:
        __version__ = tomllib.load(_source_handle)["project"]["version"]

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
