"""Numerical and causal regressions from the September 2026 paper review."""

import math
from decimal import Decimal, localcontext

import pytest

from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge, SingleDAGSource
from ncsim.models.interference import InterferenceModel
from ncsim.models.network import Network, Node, Link, Position
from ncsim.models.routing import MinimumHopRouting, ShortestPathRouting
from ncsim.models.task import Task
from ncsim.models.wifi import bianchi_fixed_point, bianchi_efficiency
from ncsim.models.wireless import configure_wireless
from ncsim.scheduler.base import ManualScheduler, NetworkSnapshot
from ncsim.scheduler.saga_adapter import create_scheduler


def decimal_reference_tau(n):
    """Independent tau-domain bisection using the original rational equation."""
    with localcontext() as context:
        context.prec = 60
        lo, hi = Decimal(0), Decimal(2) / 17
        for _ in range(220):
            tau = (lo + hi) / 2
            p = 1 - (1 - tau) ** (n - 1)
            if p == Decimal('0.5'):
                target = Decimal(2) / (17 + 48)
            else:
                target = 2 * (1 - 2*p) / ((1 - 2*p)*17 + p*16*(1-(2*p)**6))
            if tau > target:
                hi = tau
            else:
                lo = tau
        return float(tau)


@pytest.mark.parametrize('n', [1, 5, 8, 10, 20, 50, 100, 101, 256, 1000])
def test_bianchi_agrees_with_independent_high_precision_root(n):
    tau, p = bianchi_fixed_point(n)
    assert tau == pytest.approx(decimal_reference_tau(n), abs=1e-12)
    assert abs(p - (-math.expm1((n-1)*math.log1p(-tau)))) < 1e-10


def test_bianchi_full_contender_range_and_removed_cap():
    for n in range(1, 1001):
        tau, p = bianchi_fixed_point(n)
        assert abs(p - (1-(1-tau)**(n-1))) < 1e-10
    assert bianchi_efficiency(100) == pytest.approx(0.282560850, rel=1e-7)
    assert bianchi_efficiency(200) != bianchi_efficiency(100)


def test_rate_aware_solo_and_rts_timing():
    assert bianchi_efficiency(1, 8.6) == pytest.approx(0.834787737, rel=1e-7)
    assert bianchi_efficiency(1, 143.4) == pytest.approx(0.279414577, rel=1e-7)
    for rate in (8.6, 68.8, 143.4):
        assert bianchi_efficiency(1, rate, rts_cts=True) < bianchi_efficiency(1, rate)


def two_flows(latency=0):
    net = Network(
        nodes={f'n{i}': Node(f'n{i}', 10, Position(i*10, 0)) for i in range(4)},
        links={'a': Link('a', 'n0', 'n1', 1, latency),
               'b': Link('b', 'n2', 'n3', 1, latency)},
    )
    dag = DAG('d', {f'T{i}': Task(f'T{i}', 1, 'd', f'n{i}') for i in range(4)},
              [Edge('T0', 'T1', 2), Edge('T2', 'T3', 1)])
    return net, dag


class BlockingInterference(InterferenceModel):
    def __init__(self, mutual=False):
        self.mutual = mutual

    def get_interference_factor(self, link_id, active_link_ids, network):
        if {'a', 'b'} <= active_link_ids and (link_id == 'a' or self.mutual):
            return 0.0
        return 1.0

    def get_affected_links(self, changed_link_id, active_link_ids, network):
        return active_link_ids


@pytest.mark.parametrize('latency', [0, 0.5])
def test_stall_recovers_without_creating_bytes_or_recharging_latency(latency):
    net, dag = two_flows(latency)
    sim = Simulation(net, ManualScheduler(), SingleDAGSource(dag),
                     interference_model=BlockingInterference())
    result = sim.run()
    assert result.status == 'completed'
    assert result.makespan == pytest.approx(3.2 + latency, abs=2e-6)
    assert sim.engine.link_states['a'].total_data_transferred == pytest.approx(2)
    assert sim.engine.link_states['b'].total_data_transferred == pytest.approx(1)


def test_mutual_stall_is_a_model_deadlock_not_completion():
    net, dag = two_flows()
    sim = Simulation(net, ManualScheduler(), SingleDAGSource(dag),
                     interference_model=BlockingInterference(True))
    assert sim.run().status == 'blocked_wireless'
    assert sim.engine.link_states['a'].total_data_transferred == 0
    assert sim.engine.link_states['b'].total_data_transferred == 0


@pytest.mark.parametrize('limit', [dict(max_events=0), dict(max_events=2),
                                   dict(max_sim_time=0.05)])
def test_execution_limit_never_reports_completed(limit):
    net, dag = two_flows()
    sim = Simulation(net, ManualScheduler(), SingleDAGSource(dag))
    assert sim.run(**limit).status == 'limit_reached'


def test_unavailable_required_link_is_unroutable():
    net, dag = two_flows()
    net.links['a'].bandwidth = 0
    assert Simulation(net, ManualScheduler(), SingleDAGSource(dag)).run().status == 'unroutable'


def test_minimum_hop_ignores_latencies_and_unavailable_shortcuts():
    net = Network(nodes={x: Node(x, 1) for x in 'abcd'}, links={
        'ab': Link('ab', 'a', 'b', 1), 'bc': Link('bc', 'b', 'c', 1),
        'cd': Link('cd', 'c', 'd', 1), 'ad': Link('ad', 'a', 'd', 1, 10),
    })
    assert MinimumHopRouting().get_path('a', 'd', net) == ['ad']
    assert ShortestPathRouting().get_path('a', 'd', net) == ['ab', 'bc', 'cd']
    net.links['ad'].bandwidth = 0
    assert MinimumHopRouting().get_path('a', 'd', net) == ['ab', 'bc', 'cd']


def test_zero_conflict_planner_normalization_and_controls():
    net = Network(nodes={'x': Node('x', 10, Position(0, 0)),
                         'y': Node('y', 20, Position(20, 0))},
                  links={'xy': Link('xy', 'x', 'y', 1)})
    setup = configure_wireless(net, 'solo_80211')
    dag = DAG('d', {'a': Task('a', 1), 'b': Task('b', 2)}, [Edge('a', 'b', 1)])
    for name in ('conflict_aware_heft', 'uniform_discount_heft'):
        scheduler = create_scheduler(name, routing=MinimumHopRouting(),
                                     conflict_graph=setup.conflict_graph,
                                     wireless_model=setup.interference_model)
        plan = scheduler.on_dag_inject(dag, NetworkSnapshot.from_network(net, 0))
        assert plan.metadata['link_multipliers']['xy'] == pytest.approx(1)
    plan = create_scheduler('all_on_fastest').on_dag_inject(
        dag, NetworkSnapshot.from_network(net, 0))
    assert set(plan.assignments.values()) == {'y'}


def test_queued_task_reserves_slot_before_newly_ready_child():
    # Roots A/B/C arrive together. When A finishes, its child D becomes
    # ready at the same timestamp that queued B is scheduled to start.
    net = Network(nodes={'n': Node('n', 1)}, links={})
    dag = DAG('fifo', {x: Task(x, 1, 'fifo', 'n') for x in 'ABCD'}, [Edge('A','D',0)])
    sim = Simulation(net, ManualScheduler(), SingleDAGSource(dag))
    result = sim.run()
    assert result.status == 'completed'
    assert result.makespan == 4
    intervals = sorted((t.started_at, t.completed_at) for t in sim.engine.task_states.values())
    assert intervals == [(0,1), (1,2), (2,3), (3,4)]


@pytest.mark.parametrize('size', [30,40,50])
def test_all_on_fastest_equals_serial_total_work(size):
    # Self-contained workload: different task costs on heterogeneous processors.
    net = Network(nodes={'a': Node('a', 160), 'b': Node('b', 320)}, links={})
    dag = DAG('serial', {str(i): Task(str(i), 1 + i % 7, 'serial')
                         for i in range(size)},
              [Edge(str(i - 1), str(i), 1) for i in range(1, size)])
    sim = Simulation(net, create_scheduler('all_on_fastest'), SingleDAGSource(dag))
    result = sim.run()
    expected = sum(t.compute_cost for t in dag.tasks.values()) / 320
    assert result.status == 'completed'
    assert result.makespan == pytest.approx(expected, abs=size*1e-6)
    assert max(result.node_utilization.values()) <= 1.00001
