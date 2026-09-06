import json
import statistics
def parallel_setup(separation, optional=False, count=2):
    from ncsim.models.network import Network, Node, Link, Position
    from ncsim.models.wireless import configure_wireless
    net = Network(nodes={}, links={})
    for i in range(count):
        net.nodes[f't{i}'] = Node(f't{i}', 1, Position(0, i * separation))
        net.nodes[f'r{i}'] = Node(f'r{i}', 1, Position(30, i * separation))
        net.links[str(i)] = Link(str(i), f't{i}', f'r{i}', 1)
    setup = configure_wireless(net, 'full_wireless', hidden_terminal_model=(
        'fixed_capture_overlap' if optional else 'effective_rate'))
    return net, setup


def runtime_rates(separation, optional=False, count=2, payloads=None):
    """Measure completed DAG transfers through the actual event engine."""
    from ncsim.core.simulation import Simulation
    from ncsim.models.dag import DAG, Edge
    from ncsim.models.task import Task
    from ncsim.models.routing import DirectLinkRouting
    from ncsim.scheduler.base import ManualScheduler
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


def figure(report, plots):
    """Only Figure 6 is regenerated. All original packet points are retained."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from ncsim.models.wifi import carrier_sensing_range, RFConfig
    save = plots.save
    rows = report['separation']
    data = report['validation']
    predicted = data['contention_predictions']
    contention = data['contention']
    fig, axes = plt.subplots(2, 1, figsize=(6.3, 7.0))
    ax = axes[0]
    ns = list(range(1, 9))
    ax.plot(ns, [predicted[str(n)] for n in ns], 'o-', label='ncsim default model')
    ax.errorbar(ns, [contention[str(n)]['mean'] for n in ns],
                yerr=[contention[str(n)]['ci95'] for n in ns], fmt='s--',
                color='tab:red', capsize=3, label='ns-3 fixed MCS 5')
    ax.set(xlabel='Number of contending links', ylabel='Per-link goodput (MB/s)',
           title='(a) Homogeneous contention')
    ax.legend(fontsize=11); ax.grid(alpha=.2)
    ax = axes[1]
    ss = [r['separation_m'] for r in rows]
    ax.plot(ss, [r['legacy_helper_MBps'] for r in rows], 'o-',
            label='Capture/overlap formula')
    ax.errorbar(ss, [r['ns3']['mean'] for r in rows], yerr=[r['ns3']['ci95'] for r in rows],
                fmt='s--', color='tab:red', capsize=3, label='ns-3 fixed MCS 5')
    ax.plot(ss, [statistics.mean(r['default']['goodputs_MBps']) for r in rows], ':',
            color='black', lw=2, label='Default effective-rate model')
    ax.plot(ss, [statistics.mean(r['optional']['goodputs_MBps']) for r in rows],
            'D', mfc='none', mec='tab:green', ms=8, mew=1.3,
            label='Optional fixed-capture (DES)')
    ax.axvline(carrier_sensing_range(RFConfig()), color='gray', ls='--', lw=1)
    ax.set(xlabel='Parallel-link separation (m)', ylabel='Per-link goodput (MB/s)',
           title='(b) Fixed-MCS separation experiment')
    ax.legend(loc='lower right', fontsize=11); ax.grid(alpha=.2)
    save(fig, 'ns3_validation.png')
    print('Updated Figure 6 only')
