"""Recompute the appendix tables from seed-level packet observations."""
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics

from statistics_helpers import percentile, number, table, read_dynamic
from mac_predictions import asymmetric_prediction, parallel_network
from ncsim.models.wifi import bianchi_efficiency
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def dist(values):
    return dict(median=statistics.median(values), q25=percentile(values, .25),
                q75=percentile(values, .75), p95=percentile(values, .95))


def seeds(rows):
    if sorted(int(r['seed']) for r in rows) != list(range(1, 21)):
        raise ValueError('Each setting/link must contain exactly seeds 1 through 20')


def analyze(here, generated):
    base = here / 'results/packet'
    result = {'asymmetric': [], 'rate_rts': []}
    prediction = asymmetric_prediction()
    data = [r for p in sorted((base / 'overlapping').glob('asymmetric_seed*.csv')) for r in read(p)]
    for link in 'ABC':
        rows = [r for r in data if r['link'] == link]
        seeds(rows)
        vals = [float(r['goodput_MBps']) for r in rows]
        pred = prediction['per_link_MBps'][link]
        result['asymmetric'].append({'link': link, 'prediction_MBps': pred,
            'ns3': dist(vals), 'errors': dist([abs(pred-v)/v for v in vals])})
    for mcs, rate in ((0, 8.6), (11, 143.4)):
        for rts in (0, 1):
            rows = [r for p in sorted((base / 'rate_overhead').glob(f'rate_mcs{mcs}_rts{rts}_s*.csv')) for r in read(p)]
            seeds(rows)
            vals = [float(r['goodput_MBps']) for r in rows]
            pred = rate / 8 * bianchi_efficiency(1, rate, rts_cts=bool(rts))
            result['rate_rts'].append({'mcs': mcs, 'rts': rts, 'prediction_MBps': pred,
                'ns3': dist(vals), 'errors': dist([abs(pred-v)/v for v in vals])})
    def med_iqr(d):
        return f"{number(d['median'],2)} [{number(d['q25'],2)}, {number(d['q75'],2)}]"
    table(generated / 'packet_rate_table.tex', ['MCS','RTS','ncsim MB/s','ns-3 median [IQR]','Error p95'],
        [(r['mcs'], 'on' if r['rts'] else 'off', number(r['prediction_MBps'],3), med_iqr(r['ns3']),
          number(100*r['errors']['p95'])+r'\%') for r in result['rate_rts']], 'rlrrr')
    table(generated / 'packet_asym_table.tex', ['Link','ncsim MB/s','ns-3 median [IQR]','Error p95'],
        [(r['link'], number(r['prediction_MBps'],3), med_iqr(r['ns3']), number(100*r['errors']['p95'])+r'\%')
         for r in result['asymmetric']], 'lrrr')
    return result


def dynamic(here, generated, figures):
    manifest = json.loads((here / 'inputs/packet_settings.json').read_text())
    predictions = parallel_network(manifest['dynamic_separation_m'])
    solo = 68.8/8 * bianchi_efficiency(1, 68.8)
    plt.rcParams.update({'font.size':10, 'pdf.fonttype':42, 'axes.spines.top':False,
                         'axes.spines.right':False, 'figure.constrained_layout.use':True})
    fig, axs = plt.subplots(1, 2, figsize=(7.1, 2.9))
    summary = {'stable_windows': [[1,1.5], [2.5,3.5], [4.5,5.5]], 'settings': []}
    rows_table = []
    for ax, separation in zip(axs, manifest['dynamic_separation_m']):
        runs = [read_dynamic(here / f'results/packet/dynamic/dynamic_s{separation}_seed{seed}.csv', separation, seed)
                for seed in manifest['packet_seeds']]
        for link in [0,1]:
            item = {'separation_m': separation, 'link': 'AB'[link], 'intervals': [], 'windows': []}
            x = [.55+.1*b for b in range(50)]
            for b,t in enumerate(x):
                values = [next(int(r['payload_bytes']) for r in run if int(r['link_index'])==link
                              and math.isclose(float(r['start_s']),.5+.1*b,abs_tol=1e-8))/1e5 for run in runs]
                prediction = predictions[separation]['AB'[link]] if 2<=t<4 else solo if link==0 else 0
                item['intervals'].append(dict(start_s=round(t-.05,1), end_s=round(t+.05,1),
                    prediction_MBps=prediction, median_MBps=statistics.median(values),
                    q25_MBps=percentile(values,.25), q75_MBps=percentile(values,.75), samples_MBps=values))
            for a,b in summary['stable_windows']:
                values = [sum(int(r['payload_bytes']) for r in run if int(r['link_index'])==link
                              and a-1e-8<=float(r['start_s'])<b-1e-8)/(1e6*(b-a)) for run in runs]
                prediction = predictions[separation]['AB'[link]] if a==2.5 else solo if link==0 else 0
                window = dict(start_s=a, end_s=b, prediction_MBps=prediction,
                    median_MBps=statistics.median(values), q25_MBps=percentile(values,.25),
                    q75_MBps=percentile(values,.75), samples_MBps=values)
                item['windows'].append(window)
                rows_table.append((separation, 'AB'[link], f'{a:g}--{b:g}', f'{prediction:.3f}',
                    f"{window['median_MBps']:.3f} [{window['q25_MBps']:.3f}, {window['q75_MBps']:.3f}]"))
            values = item['intervals']
            color = f'C{link}'
            ax.plot(x, [r['median_MBps'] for r in values], color=color, label=f'ns-3 {item["link"]}')
            ax.fill_between(x, [r['q25_MBps'] for r in values], [r['q75_MBps'] for r in values], color=color, alpha=.16)
            ax.step(x, [r['prediction_MBps'] for r in values], where='mid', linestyle='--', color=color, label=f'ncsim {item["link"]}')
            summary['settings'].append(item)
        ax.axvline(2,color='.6',linewidth=.6)
        ax.axvline(4,color='.6',linewidth=.6)
        ax.set(xlabel='Time (s)', ylabel='Payload goodput (MB/s)', title=f'Separation {separation} m', ylim=(0,4.5))
    axs[0].legend(fontsize=8,ncol=2)
    fig.savefig(figures / 'dynamic_udp.pdf', bbox_inches='tight')
    plt.close(fig)
    table(generated / 'dynamic_udp_table.tex',
          ['Spacing m','Link','Window s','ncsim MB/s','ns-3 median [IQR] MB/s'], rows_table, 'rlrrr')
    return summary
