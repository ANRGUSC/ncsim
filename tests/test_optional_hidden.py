"""Opt-in behavior, default preservation, and executable Figure 6 evidence."""
import importlib.util
import ast
import hashlib
import json
import math
from pathlib import Path
import sys

import pytest

from ncsim.models.fixed_capture import FixedCaptureOverlapInterference, UnsupportedCaptureTopology
from ncsim.models.interference import CsmaBianchiInterference, create_interference_model
from ncsim.models.wifi import RFConfig, bianchi_efficiency, saturated_airtime_fraction
from ncsim.models.wireless import configure_wireless

ROOT = Path(__file__).resolve().parents[1]
from tests.wireless_helpers import parallel_setup, runtime_rates

DEFAULT_CLASS_AST_SHA256 = 'fcc7f01931cb4cff8e179325d1c447201395e20973a1a6ef753da646a3e8e264'


def test_default_is_not_replaced_and_optional_is_identified():
    _, default = parallel_setup(80)
    _, optional = parallel_setup(80, True)
    assert type(default.interference_model) is CsmaBianchiInterference
    assert type(optional.interference_model) is FixedCaptureOverlapInterference
    assert 'hidden_terminal_model' not in default.metadata
    assert optional.metadata['hidden_terminal_model'] == 'fixed_capture_overlap'
    assert default.raw_phy_rates_MBps == optional.raw_phy_rates_MBps
    assert default.solo_80211_rates_MBps == optional.solo_80211_rates_MBps


@pytest.mark.parametrize('separation', [10, 70, 72, 75, 80, 90, 100, 120, 200])
def test_opt_in_matches_independent_two_link_formula(separation):
    net, setup = parallel_setup(separation, True)
    model = setup.interference_model
    if separation <= 71.22:
        expected = bianchi_efficiency(2, 68.8) / (2 * bianchi_efficiency(1, 68.8))
    elif separation <= 100:
        # Independent single-station cycle accounting: ceil(12358/935.68)=14.
        data_us = 44 + 14 * 13.6
        cycle_us = data_us + 16 + .1 + 28 + 43 + .1 + 7.5 * 9
        expected = 1 - data_us / cycle_us
    else:
        expected = 1.0
    for link in net.links:
        assert model.get_interference_factor(link, set(net.links), net) == pytest.approx(expected, abs=1e-12)
        assert model.get_interference_factor(link, {link}, net) == 1.0
    assert model.get_interference_factor('0', set(), net) == 1.0


def test_default_matches_frozen_implementation_across_active_sets():
    old_path = ROOT / 'tests/fixtures/effective_rate_reference.py'
    spec = importlib.util.spec_from_file_location('pre_optional_interference', old_path)
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    for count in [1, 2, 3, 8]:
        for distance in [5, 40, 70, 75, 80, 100, 120, 300]:
            net, setup = parallel_setup(distance, count=count)
            old = previous.CsmaBianchiInterference(setup.conflict_graph, setup.rf_config, net,
                                                  base_rates=setup.raw_phy_rates_MBps)
            for active in [set(net.links), set(net.links) - {'0'}, {'0'}]:
                for link in net.links:
                    assert setup.interference_model.get_interference_factor(link, active, net) == old.get_interference_factor(link, active, net)
                    assert setup.interference_model.get_affected_links(link, active, net) == old.get_affected_links(link, active, net)


def test_default_class_body_is_unchanged():
    tree = ast.parse((ROOT / 'ncsim/models/interference.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CsmaBianchiInterference')
    assert hashlib.sha256(ast.dump(node).encode()).hexdigest() == DEFAULT_CLASS_AST_SHA256


def test_completion_removes_hidden_loss_and_conserves_bytes():
    data = runtime_rates(80, True, payloads=[10, 5])
    solo = 8.6 * bianchi_efficiency(1, 68.8)
    degraded = solo * (1 - saturated_airtime_fraction())
    first = 5 / degraded
    assert data['finished_s'] == pytest.approx([first + 5 / solo, first], abs=4e-6)
    assert data['served_MB'] == pytest.approx([10, 5], abs=1e-9)
    net, setup = parallel_setup(80, True)
    assert setup.interference_model.get_affected_links('1', {'0', '1'}, net) == {'0'}


@pytest.mark.parametrize('separation', [40, 80])
def test_unsupported_mixed_and_multiple_hidden_interactions_raise(separation):
    net, setup = parallel_setup(separation, True, count=3)
    with pytest.raises(UnsupportedCaptureTopology):
        for link in net.links:
            setup.interference_model.get_interference_factor(link, set(net.links), net)


@pytest.mark.parametrize('rf', [RFConfig(rts_cts=True), RFConfig(channel_width_mhz=40), RFConfig(wifi_standard='ac')])
def test_unsupported_phy_configuration_is_not_silently_accepted(rf):
    net, _ = parallel_setup(80)
    with pytest.raises(ValueError):
        configure_wireless(net, 'full_wireless', rf, hidden_terminal_model='fixed_capture_overlap')


def test_factory_and_mode_errors():
    with pytest.raises(ValueError):
        create_interference_model('raw_phy', hidden_terminal_model='fixed_capture_overlap')
    with pytest.raises(ValueError):
        create_interference_model('full_wireless', hidden_terminal_model='typo')
    net, _ = parallel_setup(80)
    with pytest.raises(ValueError):
        configure_wireless(net, 'solo_80211', hidden_terminal_model='fixed_capture_overlap')


def test_hidden_ablation_retains_solo_rate():
    net, _ = parallel_setup(80)
    setup = configure_wireless(net, 'full_wireless', components='contention-only',
                              hidden_terminal_model='fixed_capture_overlap')
    assert setup.interference_model.get_interference_factor('0', set(net.links), net) == 1.0


def test_unrecognized_fixed_rate_is_rejected():
    net, setup = parallel_setup(80)
    with pytest.raises(ValueError, match='MCS'):
        create_interference_model('full_wireless', hidden_terminal_model='fixed_capture_overlap',
                                  conflict_graph=setup.conflict_graph, rf_config=setup.rf_config,
                                  network=net, base_rates={'0': 6.123, '1': 8.6})


def test_cli_opt_in_and_default(tmp_path):
    from ncsim.main import main
    results = {}
    for mode in ['effective_rate', 'fixed_capture_overlap']:
        folder = tmp_path / mode
        args = ['--scenario', str(ROOT / 'scenarios/fixed_capture_pair.yaml'),
                '--output', str(folder)]
        if mode != 'effective_rate':
            args += ['--hidden-terminal-model', mode]
        assert main(args) == 0
        results[mode] = json.loads((folder / 'metrics.json').read_text())
    assert results['effective_rate']['makespan'] == pytest.approx(runtime_rates(80)['finished_s'][0], abs=3e-6)
    assert results['fixed_capture_overlap']['makespan'] == pytest.approx(runtime_rates(80, True)['finished_s'][0], abs=3e-6)
    assert results['fixed_capture_overlap']['hidden_terminal_model'] == 'fixed_capture_overlap'
    assert 'hidden_terminal_model' not in results['effective_rate']


def test_cli_rejects_ignored_optional_flag(tmp_path):
    from ncsim.main import main
    assert main(['--scenario', str(ROOT / 'scenarios/fixed_capture_pair.yaml'),
                 '--output', str(tmp_path), '--interference', 'proximity',
                 '--hidden-terminal-model', 'fixed_capture_overlap']) == 1
