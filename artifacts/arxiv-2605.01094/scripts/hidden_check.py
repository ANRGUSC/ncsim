"""Check the two-link option and homogeneous contention against saved packet seeds."""
import json
import statistics

from hidden_runtime import runtime_rates, figure
from plot_study import seed_stat
from ncsim.models.wifi import bianchi_efficiency


def validate(here):
    saved = json.loads((here / 'results/evidence.json').read_text())['validation']
    packet = here / 'results/packet/main'
    rows = []
    for point in saved['capture_overlap']:
        sep = point['separation_m']
        ns3 = seed_stat(sorted(packet.glob(f'separation_s{sep}_fixed_seed*.csv')), 2)
        default = runtime_rates(sep)
        optional = runtime_rates(sep, optional=True)
        prediction = statistics.mean(optional['goodputs_MBps'])
        assert abs(prediction - point['per_link_MBps']) < .00005
        assert abs(statistics.mean(default['goodputs_MBps']) - saved['production_separation'][str(sep)]['A']) < 3e-6
        rows.append({'separation_m': sep, 'ns3': ns3, 'default': default, 'optional': optional,
                     'legacy_helper_MBps': point['per_link_MBps'],
                     'optional_abs_relative_error': abs(prediction / ns3['mean'] - 1)})
    contention = []
    for n in range(1, 9):
        default = runtime_rates(5, count=n)
        optional = runtime_rates(5, optional=True, count=n)
        assert default['goodputs_MBps'] == optional['goodputs_MBps']
        analytical = 8.6 * bianchi_efficiency(n, 68.8) / n
        assert max(abs(v - analytical) for v in optional['goodputs_MBps']) < 3e-6
        contention.append({'n': n, 'default_and_optional_identical': True,
                           'runtime_MBps': optional['goodputs_MBps'],
                           'ns3': seed_stat(sorted(packet.glob(f'contention_n{n}_s*.csv')), n)})
    errors = [r['optional_abs_relative_error'] for r in rows]
    return {'mode': 'fixed_capture_overlap', 'capture_margin_dB': 5,
            'scope': 'Two parallel 30 m links, fixed MCS 5, 802.11ax, 20 MHz, no RTS/CTS',
            'separation': rows, 'contention': contention, 'validation': saved,
            'acceptance': {'max_abs_relative_error': max(errors),
                           'mean_abs_relative_error': statistics.mean(errors),
                           'max_limit': .15, 'mean_limit': .10,
                           'passed': max(errors) <= .15 and statistics.mean(errors) <= .10}}
