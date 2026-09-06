"""Model invariants and a global-refresh oracle for the v2 review."""
import copy
import itertools
import math

import pytest

from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.network import Network, Node, Link, Position
from ncsim.models.routing import MinimumHopRouting
from ncsim.models.task import Task
from ncsim.models.wifi import RFConfig, bianchi_efficiency, friis_reference_loss_dB
from ncsim.models.wireless import configure_wireless
from ncsim.scheduler.base import ManualScheduler


@pytest.mark.parametrize('threshold', [5, 8, 11, 14, 18, 22, 25, 29, 32, 35, 38, 41])
@pytest.mark.parametrize('offset', [-1e-7, 0, 1e-7])
@pytest.mark.parametrize('margin', [0, 3, 5, 8])
@pytest.mark.parametrize('rts', [False, True])
def test_isolated_link_preserves_solo_at_every_threshold(threshold, offset, margin, rts):
    rf = RFConfig(capture_margin_dB=margin, rts_cts=rts)
    snr = threshold + offset
    distance = 10 ** ((rf.tx_power_dBm - rf.noise_floor_dBm - snr
                      - friis_reference_loss_dB(rf.freq_ghz)) / 30)
    original = Network(nodes={'a': Node('a', 1, Position(0, 0)),
                              'b': Node('b', 1, Position(distance, 0))},
                       links={'ab': Link('ab', 'a', 'b', 1)})
    solo, full = copy.deepcopy(original), copy.deepcopy(original)
    configure_wireless(solo, 'solo_80211', rf)
    setup = configure_wireless(full, 'full_wireless', rf)
    factor = setup.interference_model.get_interference_factor('ab', {'ab'}, full)
    assert full.links['ab'].bandwidth * factor == pytest.approx(solo.links['ab'].bandwidth, abs=1e-12)


@pytest.mark.parametrize('edges', [[], [(0, 1), (1, 2)],
    [(0, 1), (1, 2), (2, 0)], [(0, 1), (0, 2), (0, 3), (0, 4)],
    [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)]])
def test_random_order_realizes_graph_shares(edges):
    neighbors = {i: set() for i in range(5)}
    for a, b in edges:
        neighbors[a].add(b)
        neighbors[b].add(a)
    counts = dict.fromkeys(neighbors, 0)
    for order in itertools.permutations(neighbors):
        rank = {v: i for i, v in enumerate(order)}
        selected = {v for v in neighbors if all(rank[v] < rank[w] for w in neighbors[v])}
        assert all(not (neighbors[v] & selected) for v in selected)
        for v in selected:
            counts[v] += 1
    for v, count in counts.items():
        assert count / math.factorial(5) == pytest.approx(1 / (1 + len(neighbors[v])))
        for rate in [8.6, 68.8, 143.4]:
            assert 0 <= bianchi_efficiency(1 + len(neighbors[v]), rate) <= 1


def execute_with_refresh_oracle(network, dag, wireless, global_refresh):
    network = copy.deepcopy(network)
    setup = configure_wireless(network, wireless)
    sim = Simulation(network, ManualScheduler(), SingleDAGSource(copy.deepcopy(dag)),
                     routing_model=MinimumHopRouting(), interference_model=setup.interference_model)
    if global_refresh:
        local = sim.engine._refresh_transfers
        # Independently choose every link, bypassing the dependency-neighborhood filter.
        sim.engine._refresh_transfers = lambda changed: local(set(network.links))
    snapshots = []
    def observe(event):
        active = {(f.dag_id, f.from_task, f.to_task): f
                  for state in sim.engine.link_states.values() for f in state.active_transfers}
        progress = {k: min(f.data_remaining, max(0, sim.sim_time-f.started_at)
                          * f.current_effective_rate) for k, f in active.items()}
        snapshots.append((
            (event.event_type.name, event.task_id, event.from_task, event.to_task),
            sim.sim_time,
            {k: (f.data_remaining-progress[k], f.current_effective_rate) for k, f in active.items()},
            sum(s.total_data_transferred for s in sim.engine.link_states.values())
            + sum(progress[k]*len(f.link_ids) for k, f in active.items())))
    sim.add_event_listener(observe)
    result = sim.run()
    tasks = {key: (state.started_at, state.completed_at) for key, state in sim.engine.task_states.items()}
    served = {key: state.total_data_transferred for key, state in sim.engine.link_states.items()}
    remaining = {}
    for state in sim.engine.link_states.values():
        for flow in state.active_transfers:
            key = (flow.dag_id, flow.from_task, flow.to_task)
            remaining[key] = (flow.data_remaining - max(0, sim.engine.sim_time - flow.started_at)
                              * flow.current_effective_rate, flow.current_effective_rate)
    return result, tasks, served, remaining, snapshots


@pytest.mark.parametrize('separation', [20, 80, 120])
@pytest.mark.parametrize('latency', [0, .5])
@pytest.mark.parametrize('wireless', ['solo_80211', 'full_wireless'])
def test_local_refresh_agrees_with_global_on_multihop_shared_and_hidden_flows(separation, latency, wireless):
    positions = {'a': (0, 0), 'b': (30, 0), 'c': (60, 0),
                 'd': (0, separation), 'e': (30, separation)}
    network = Network(nodes={k: Node(k, 1, Position(*p)) for k, p in positions.items()},
                      links={key: Link(key, a, b, 1, latency) for key, a, b in
                             [('ab', 'a', 'b'), ('bc', 'b', 'c'), ('de', 'd', 'e')]})
    dag = DAG('oracle', {k: Task(k, work, 'oracle', node) for k, work, node in
                        [('A', 1, 'a'), ('B', 1, 'b'), ('C', 1, 'c'), ('D', 2, 'd'),
                         ('E', 1, 'e'), ('F', 1, 'c')]},
              [Edge('A', 'C', 4), Edge('B', 'F', 2), Edge('D', 'E', 1)])
    actual = execute_with_refresh_oracle(network, dag, wireless, False)
    reference = execute_with_refresh_oracle(network, dag, wireless, True)
    assert actual[0].status == reference[0].status
    assert actual[0].makespan == pytest.approx(reference[0].makespan, abs=3e-6)
    assert actual[1].keys() == reference[1].keys()
    for key in actual[1]:
        assert actual[1][key] == pytest.approx(reference[1][key], abs=3e-6)
    assert actual[2] == pytest.approx(reference[2], abs=1e-6)
    assert actual[3].keys() == reference[3].keys()
    for key in actual[3]:
        assert actual[3][key] == pytest.approx(reference[3][key], abs=1e-6)
    assert len(actual[4]) == len(reference[4])
    for observed, expected in zip(actual[4], reference[4]):
        assert observed[0] == expected[0]
        assert observed[1] == pytest.approx(expected[1], abs=3e-6)
        assert observed[2].keys() == expected[2].keys()
        for key in observed[2]:
            assert observed[2][key] == pytest.approx(expected[2][key], abs=1e-6)
        assert observed[3] == pytest.approx(expected[3], abs=1e-6)


def test_worked_two_hop_timeline():
    # A finishes at 1; A->C has 4 MB over ab/bc (2 MB/s). B finishes at 2
    # and adds a 1 MB b->c flow. Both get 1 MB/s until t=3, then A->C
    # sends its remaining 1 MB at 2 MB/s until 3.5. D runs 3..4 and C 4..5.
    network = Network(nodes={x: Node(x, 1) for x in 'abc'},
                      links={'ab': Link('ab', 'a', 'b', 2), 'bc': Link('bc', 'b', 'c', 2)})
    dag = DAG('worked', {k: Task(k, w, 'worked', n) for k, w, n in
                        [('A', 1, 'a'), ('B', 2, 'b'), ('C', 1, 'c'), ('D', 1, 'c')]},
              [Edge('A', 'C', 4), Edge('B', 'D', 1)])
    sim = Simulation(network, ManualScheduler(), SingleDAGSource(dag), routing_model=MinimumHopRouting())
    result = sim.run()
    assert result.status == 'completed'
    assert result.makespan == 5
    assert sorted((s.started_at, s.completed_at) for s in sim.engine.task_states.values()) == [
        (0, 1), (0, 2), (3, 4), (4, 5)]
    assert sim.engine.link_states['ab'].total_data_transferred == 4
    assert sim.engine.link_states['bc'].total_data_transferred == 5
