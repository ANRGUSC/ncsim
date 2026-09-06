"""Tests for the visualization API's shared scheduler catalog."""

import asyncio

from ncsim.scheduler.saga_adapter import SAGA_SCHEDULERS
from viz.server.main import list_schedulers


def test_scheduler_endpoint_uses_core_registry():
    catalog = asyncio.run(list_schedulers())
    names = {entry["name"] for entry in catalog}

    assert "heft" in names
    assert "wba" in names
    assert "round_robin" in names
    assert set(SAGA_SCHEDULERS) <= names
    assert next(entry for entry in catalog if entry["name"] == "wba")["options"]
