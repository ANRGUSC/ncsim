"""Small deterministic wireless fixtures; no study-folder dependencies."""
from ncsim.models.network import Network, Node, Link, Position
from ncsim.models.wireless import configure_wireless
from ncsim.core.simulation import Simulation
from ncsim.models.dag import DAG, Edge
from ncsim.models.task import Task
from ncsim.models.routing import DirectLinkRouting
from ncsim.scheduler.base import ManualScheduler


def parallel_setup(separation, optional=False, count=2):
    net = Network(nodes={}, links={})
    for i in range(count):
        net.nodes[f't{i}'] = Node(f't{i}', 1, Position(0, i * separation))
        net.nodes[f'r{i}'] = Node(f'r{i}', 1, Position(30, i * separation))
        net.links[str(i)] = Link(str(i), f't{i}', f'r{i}', 1)
    setup = configure_wireless(net, 'full_wireless', hidden_terminal_model=(
        'fixed_capture_overlap' if optional else 'effective_rate'))
    return net, setup


def runtime_rates(separation, optional=False, count=2, payloads=None):
    net, setup = parallel_setup(separation, optional, count)
    payloads = payloads or [10.] * count
    sim = Simulation(net, ManualScheduler(), routing_model=DirectLinkRouting(),
                     interference_model=setup.interference_model)
    for i in range(count):
        name = f'd{i}'
        sim.inject_dag(DAG(name, {
            'a': Task('a', 0, name, f't{i}'), 'b': Task('b', 0, name, f'r{i}')
        }, [Edge('a', 'b', payloads[i])]), 0)
    result = sim.run()
    assert result.status == 'completed', result.status
    finished = [sim.engine.get_task_state(f'd{i}', 'b').completed_at for i in range(count)]
    return {'goodputs_MBps': [payloads[i] / finished[i] for i in range(count)],
            'finished_s': finished,
            'served_MB': [sim.engine.link_states[str(i)].total_data_transferred for i in range(count)],
            'metadata': setup.metadata}
