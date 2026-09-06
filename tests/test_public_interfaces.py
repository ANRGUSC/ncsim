"""Consistency checks for the published CLI, package, and scheduler catalog."""
import argparse
import copy
import logging
from pathlib import Path
import tomllib

import pytest
from ncsim.io.scenario_loader import load_scenario
from ncsim.main import _setup_wifi_model, main
from ncsim.models.wireless import configure_wireless
from ncsim.models.wifi import RFConfig
from ncsim.core.simulation import Simulation, SimulationResult
from ncsim.scheduler.saga_adapter import scheduler_catalog

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('rate', [0, 8.6, 68.8, 143.4])
@pytest.mark.parametrize('rts', [False, True])
@pytest.mark.parametrize('mode', ['raw_phy', 'solo_80211', 'full_wireless'])
def test_cli_and_api_share_rate_normalization(rate, rts, mode):
    scenario = load_scenario(ROOT / 'scenarios/fixed_capture_pair.yaml')
    for link in scenario.network.links.values():
        link.bandwidth = rate / 8
    scenario.explicit_bandwidth_links = set(scenario.network.links)
    api = copy.deepcopy(scenario.network)
    args = argparse.Namespace(interference=mode, tx_power=None, freq=None,
        path_loss_exponent=None, wifi_standard=None, rts_cts=rts,
        capture_margin_db=None, hidden_terminal_model='effective_rate',
        wireless_components='combined', outage_floor_factor=None)
    _, metadata = _setup_wifi_model(scenario, args, 42, logging.getLogger('test'))
    setup = configure_wireless(api, mode, RFConfig(rts_cts=rts),
                              explicit_bandwidth_links=set(api.links))
    for key in api.links:
        assert scenario.network.links[key].bandwidth == api.links[key].bandwidth
        assert metadata['link_solo_80211_rates_MBps'][key] == round(setup.solo_80211_rates_MBps[key], 4)


@pytest.mark.parametrize('status', ['completed', 'error', 'unroutable', 'blocked_wireless', 'limit_reached'])
def test_cli_exit_status(status, tmp_path, monkeypatch):
    def run(self):
        return SimulationResult(makespan=0, total_events=0, status=status,
                                error_message=None if status == 'completed' else 'test outcome')
    monkeypatch.setattr(Simulation, 'run', run)
    assert main(['--scenario', str(ROOT / 'scenarios/demo_simple.yaml'),
                 '--output', str(tmp_path)]) == (0 if status == 'completed' else 1)


def test_scheduler_catalog_uses_existing_ui_categories():
    assert all(row['kind'] in {'saga', 'builtin'} for row in scheduler_catalog())


def test_package_discovery_excludes_studies_and_scratch():
    data = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    assert data['tool']['setuptools']['packages']['find']['include'] == ['ncsim', 'ncsim.*']
