"""The 108 grid, 42 payload, and ten concurrent-workflow executions."""
import importlib.util
import json
import platform

from workflow_core import Case, run_case, _build_dag
from ncsim.models.network import Network, Node, Link, Position
from ncsim.models.routing import MinimumHopRouting
from ncsim.models.wireless import configure_wireless
from ncsim.scheduler.saga_adapter import create_scheduler
from ncsim.core.simulation import Simulation


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def network(nodes, links):
    return Network(
        nodes={n['id']: Node(n['id'], n['compute_capacity'], Position(n['x'], n['y'])) for n in nodes},
        links={l['id']: Link(l['id'], l['from'], l['to'], l['bandwidth']) for l in links})


def run(here, smoke=False):
    grid = module('study_grid', here / 'inputs/run_full_scheduler_comparison.py')
    ccr = module('study_ccr', here / 'inputs/run_sensitivity_ccr.py')
    payload = {'grid': [], 'ccr': [], 'multidag': []}
    for size in ((2,) if smoke else (2, 3, 4)):
        net = network(*grid.generate_network(size))
        for dag_name, generator in grid.DAG_GENERATORS.items():
            if smoke and dag_name != 'small':
                continue
            for routing in (('minimum_hop',) if smoke else ('minimum_hop', 'widest_path')):
                case_id = f'grid{size}_{dag_name}_{routing}'
                case = Case(case_id, f'grid{size}', 42, {'nodes': len(net.nodes), 'links': len(net.links)},
                            net, dag_name, 42, _build_dag(case_id, *generator()), routing)
                payload['grid'].extend(run_case(case, schedulers=('heft', 'cpop', 'round_robin')))
        print(f'Grid {size}x{size}: complete', flush=True)
    for dag_name, (_, generator) in ccr.DAG_GENERATORS.items():
        if smoke and dag_name != 'small':
            continue
        for mb in ((1.,) if smoke else ccr.DATA_SIZES):
            case_id = f'ccr_{dag_name}_{mb:g}'
            net = network(*ccr.generate_network())
            case = Case(case_id, 'ccr_grid3', 42, {}, net, dag_name, 42, _build_dag(case_id, *generator(mb)))
            for row in run_case(case, schedulers=('heft',)):
                row['payload_MB'] = mb
                payload['ccr'].append(row)
    for count in ((1,) if smoke else range(1, 6)):
        for mode in ('solo_80211', 'full_wireless'):
            net = network(*ccr.generate_network())
            setup = configure_wireless(net, mode, seed=42)
            routing = MinimumHopRouting()
            sim = Simulation(net, create_scheduler('heft', routing=routing), routing_model=routing,
                             interference_model=setup.interference_model, seed=42)
            for i in range(count):
                sim.inject_dag(_build_dag(f'dag{i}', *ccr._make_dag_small(10.0)), inject_at=.5*i)
            result = sim.run()
            payload['multidag'].append({'count': count, 'mode': mode, 'status': result.status,
                'makespan_s': result.makespan if result.status == 'completed' else None,
                'placements': {k: v.assignments for k, v in sim.engine.placement_plans.items()}})
    expected = (6, 2, 2) if smoke else (108, 42, 10)
    assert tuple(len(payload[k]) for k in ('grid', 'ccr', 'multidag')) == expected
    payload['replay_environment'] = {'python': platform.python_version(), 'seed': 42,
                                   'PYTHONHASHSEED': '0', 'smoke': smoke}
    return payload
