import collections
import copy
import csv
import hashlib
import json
import logging
import math
from pathlib import Path
import shutil
import statistics
import sys
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from ncsim.models.wifi import RFConfig, bianchi_efficiency, carrier_sensing_range, received_power_dBm, snr_to_rate_mbps, sinr_to_effective_rate_mbps, sinr_dB
from ncsim.models.network import Network, Node, Link, Position
from ncsim.models.dag import DAG, Edge
from ncsim.models.task import Task
from ncsim.models.routing import DirectLinkRouting, MinimumHopRouting, WidestPathRouting
from ncsim.models.wireless import configure_wireless
from ncsim.scheduler.base import ManualScheduler
from ncsim.core.simulation import Simulation
from study_workflows import module, network
from bianchi_reference import bianchi_throughput_S
matplotlib.use('Agg')
POLICIES = ('heft', 'cpop', 'round_robin')
SHORT = {'heft':'H', 'cpop':'C', 'round_robin':'RR'}
plt.rcParams.update({'font.family':'serif','font.size':10,'axes.labelsize':11,'legend.fontsize':9})
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def save(fig,name):
    fig.tight_layout()
    fig.savefig(FIG/name,dpi=220,bbox_inches='tight')
    plt.close(fig)


def rows_file(name, rows):
    (GEN/name).write_text('\n'.join(' & '.join(map(str,row))+r' \\' for row in rows)+'\n')


def winner_set(values):
    best=min(values.values())
    tolerance=max(1e-6,1e-6*best)
    return {p for p,v in values.items() if v<=best+tolerance}


def seed_stat(paths,expected_links):
    observations=[]
    seed_ids=[]
    for path in paths:
        with path.open(newline='') as stream:
            rows=list(csv.DictReader(stream))
        assert len(rows)==expected_links,(path,len(rows))
        assert sorted(int(r['link_index']) for r in rows)==list(range(expected_links))
        assert len({r['seed'] for r in rows})==1
        seed_ids.append(int(rows[0]['seed']))
        values=[float(r['goodput_MBps']) for r in rows]
        assert all(math.isfinite(v) and v>=0 for v in values)
        observations.append(statistics.mean(values))
    assert sorted(seed_ids)==list(range(1,21)),seed_ids
    return {'mean':statistics.mean(observations),'ci95':2.093024054*statistics.stdev(observations)/math.sqrt(20),
            'seed_means':observations}


def bianchi():
    source=INPUT/'bianchi_fig6_original.png'
    # Marker centers read from the source image, not selected by proximity to
    # predicted throughput. Axes are x=110..713 (0..50), y=477..9 (.50...90).
    assert Image.open(source).size==(892,625)
    counts=[5,10,15,20,30,50]
    marker_y={(32,5):[119,177,218,248,290,347], (128,3):[103,100,116,134,165,217]}
    params=dict(slot_us=50,sifs_us=28,difs_us=128,prop_us=1,payload_bits=8184,
                mac_header_bits=272,phy_header_bits=128,ack_bits=112,rate_mbps=1)
    result={'source_sha256':sha(source),'axes_pixels':{'x':[110,713],'y':[477,9]},
            'marker_uncertainty_pixels':2,'points':[],'table3':[]}
    fig,ax=plt.subplots(figsize=(6.3,4.3))
    for (w,m),ys in marker_y.items():
        color='tab:blue' if w==32 else 'tab:red'
        ns=list(range(5,51))
        values=[bianchi_throughput_S(n,w,m,**params)['S'] for n in ns]
        ax.plot(ns,values,color=color,label=f'Production solver: W={w}, m={m}')
        digitized=[.5+(477-y)*.4/468 for y in ys]
        ax.errorbar(counts,digitized,yerr=2*.4/468,fmt='s' if w==32 else 'o',
                    mfc='white',color=color,ms=6,capsize=2,label=f'Bianchi Fig. 6: W={w}, m={m}')
        for n,y,value in zip(counts,ys,digitized):
            computed=bianchi_throughput_S(n,w,m,**params)['S']
            result['points'].append({'W':w,'m':m,'n':n,'pixel_y':y,'digitized':value,'computed':computed,
                                     'relative_error':abs(computed-value)/value})
    for n,reference in [(2,.8473),(3,.8368)]:
        result['table3'].append({'n':n,'computed':bianchi_throughput_S(n,32,3,**params)['S'],'published':reference})
    ax.set(xlabel='Number of stations',ylabel='Normalized throughput',xlim=(0,52),ylim=(.58,.86))
    ax.grid(alpha=.2)
    ax.legend(loc='lower left')
    save(fig,'bianchi_fig6_overlay.png')
    return result


def internal_case(count,separation):
    rf=RFConfig()
    net=Network(nodes={},links={})
    for i in range(count):
        net.nodes[f't{i}']=Node(f't{i}',1,Position(0,i*separation))
        net.nodes[f'r{i}']=Node(f'r{i}',1,Position(30,i*separation))
        net.links[str(i)]=Link(str(i),f't{i}',f'r{i}',1)
    setup=configure_wireless(net,'full_wireless',rf)
    # Independent piecewise fluid calculation for this specific parallel geometry.
    remaining={i:10.0 for i in range(count)}
    finish={}; now=0
    while remaining:
        rates={}
        for i in remaining:
            contenders=[j for j in remaining if j!=i and abs(j-i)*separation<=carrier_sensing_range(rf)]
            hidden=[j for j in remaining if j!=i and j not in contenders]
            raw=68.8
            if hidden:
                powers=[received_power_dBm(20,math.hypot(30,(j-i)*separation),rf) for j in hidden]
                sinr=sinr_dB(received_power_dBm(20,30,rf),powers,rf.noise_floor_dBm)
                raw=min(raw,sinr_to_effective_rate_mbps(sinr,capture_margin_dB=5))
            n=1+len(contenders)
            rates[i]=raw/8*bianchi_efficiency(n,raw)/n if raw else 0
        delta=min(remaining[i]/r for i,r in rates.items() if r>0)
        now+=delta
        for i in list(remaining):
            remaining[i]-=rates[i]*delta
            if remaining[i]<1e-8:
                finish[i]=now
                del remaining[i]
    sim=Simulation(net,ManualScheduler(),routing_model=DirectLinkRouting(),interference_model=setup.interference_model)
    for i in range(count):
        name=f'd{i}'
        sim.inject_dag(DAG(name,{'a':Task('a',0,name,f't{i}'),'b':Task('b',0,name,f'r{i}')},[Edge('a','b',10)]),0)
    result=sim.run()
    assert result.status=='completed',result
    observed={i:sim.engine.get_task_state(f'd{i}','b').completed_at for i in range(count)}
    assert all(abs(observed[i]-finish[i])<4e-6 for i in finish),(count,separation,finish,observed)
    return {'count':count,'separation':separation,'predicted_rates':[10/finish[i] for i in range(count)],
            'simulated_rates':[10/observed[i] for i in range(count)]}


def internal():
    rows=[internal_case(3,s) for s in [10,20,30,35,40,50,60,70,75,100,150]]
    selected=[r for r in rows if r['separation'] in [10,35,40,50,70,75,100,150]]
    rows_file('exp4_rows.tex',[[r['separation'],'all-conf' if r['separation']<=35.6 else 'mixed' if r['separation']<=71.2 else 'all-hid',
        f"{r['predicted_rates'][0]:.3f}",f"{r['simulated_rates'][0]:.3f}",f"{r['predicted_rates'][1]:.3f}",f"{r['simulated_rates'][1]:.3f}"] for r in selected])
    scaling=[internal_case(n,5) for n in range(2,9)]
    rows_file('exp7_rows.tex',[[r['count'],f"{bianchi_efficiency(r['count'],68.8):.3f}",
        f"{bianchi_efficiency(r['count'],68.8)/r['count']:.3f}",f"{r['predicted_rates'][0]:.3f}",f"{r['simulated_rates'][0]:.3f}"] for r in scaling])
    two=[internal_case(2,s) for s in [5,10,20,30,40,50,60,70,75,80,90,100,120,150,200]]
    fig,ax=plt.subplots(figsize=(6.3,3.6))
    ax.plot([r['separation'] for r in two],[r['predicted_rates'][0] for r in two],label='Analytical effective-rate prediction')
    ax.plot([r['separation'] for r in two],[r['simulated_rates'][0] for r in two],'o',mfc='white',label='DES transfer measurement')
    ax.axvline(carrier_sensing_range(RFConfig()),ls='--',color='gray')
    ax.set(xlabel='Parallel-link separation (m)',ylabel='Per-link goodput (MB/s)')
    ax.legend(fontsize=8); ax.grid(alpha=.2)
    save(fig,'exp2_parallel_separation.png')
    return {'three_parallel':rows,'n_way':scaling,'two_parallel':two}


def evaluation():
    data=json.loads((OUT/'workflows.json').read_text())
    lookup={(r['case_id'],r['scheduler'],r['wireless_mode_canonical']):r for r in data['grid']}
    def get(size,dag,route,policy,mode='full_wireless'):
        return lookup[(f'grid{size}_{dag}_{route}',policy,mode)]
    routing=[]; impact=[]; matrix=[]; cases=[]
    for size in (2,3,4):
        for dag,tasks in [('small',5),('medium',10),('large',20)]:
            w=get(size,dag,'widest_path','heft')['makespan_s']; m=get(size,dag,'minimum_hop','heft')['makespan_s']
            routing.append([f'${size}\\times{size}$',tasks,f'{w:.2f}',f'{m:.2f}','Tie' if abs(w-m)<1e-6 else 'Min-hop' if m<w else 'Widest'])
            line=[f'${size}\\times{size}$',f'{tasks}T']
            for policy in ('heft','cpop'):
                s=get(size,dag,'minimum_hop',policy,'solo_80211')['makespan_s']; f=get(size,dag,'minimum_hop',policy)['makespan_s']
                line += [f'{s:.2f}',f'{f:.2f}',f'{100*(f/s-1):.0f}\\%']
            impact.append(line)
            line=[f'${size}\\times{size}$',f'{tasks}T']
            for route in ('widest_path','minimum_hop'):
                solo={p:get(size,dag,route,p,'solo_80211')['makespan_s'] for p in POLICIES}
                full={p:get(size,dag,route,p)['makespan_s'] for p in POLICIES}
                sw=winner_set(solo); fw=winner_set(full); chosen=next(p for p in POLICIES if p in sw)
                ratio=full[chosen]/min(full.values()); inversion=not bool(sw&fw)
                line += [f'{full[p]/min(full.values()):.2f}' for p in POLICIES]+['/'.join(SHORT[p] for p in POLICIES if p in sw)]
                cases.append({'size':size,'tasks':tasks,'routing':route,'solo_winners':sorted(sw),'full_winners':sorted(fw),
                              'chosen':chosen,'ratio':ratio,'inversion':inversion,'solo':solo,'full':full})
            matrix.append(line)
    rows_file('routing_rows.tex',routing); rows_file('interference_rows.tex',impact); rows_file('winner_rows.tex',matrix)
    fig,ax=plt.subplots(figsize=(6.3,3.7))
    ax.bar(range(18),[c['ratio'] for c in cases],color=['tab:red' if c['inversion'] else 'tab:blue' for c in cases])
    ax.axhline(1,color='black',lw=.8)
    ax.set_xticks(range(18),[f"{c['size']}x{c['size']}/{c['tasks']}/{('W' if c['routing']=='widest_path' else 'M')}" for c in cases],rotation=75,fontsize=11)
    ax.set(ylabel='Solo-selected / best Full makespan',ylim=(0,1.7))
    save(fig,'regret_scatter.png')
    fig,ax=plt.subplots(figsize=(6.3,3.6))
    ccr=[]
    for dag,marker in [('small','o'),('medium','s'),('large','^')]:
        group=collections.defaultdict(dict)
        for r in data['ccr']:
            if r['workload_family']==dag: group[r['payload_MB']][r['wireless_mode_canonical']]=r
        xs=sorted(group); ys=[]
        for x in xs:
            pair=group[x]; ratio=pair['full_wireless']['makespan_s']/pair['solo_80211']['makespan_s']
            ys.append(ratio); ccr.append({'dag':dag,'payload_MB':x,'slowdown':ratio,'full_s':pair['full_wireless']['makespan_s'],
                                        'remote_MB':pair['full_wireless']['remote_payload_bytes']/1e6})
        ax.plot(xs,ys,marker=marker,label={'small':'5 tasks','medium':'10 tasks','large':'20 tasks'}[dag])
    ax.set(xscale='log',xlabel='Payload per dependency (MB)',ylabel='Full / Solo makespan')
    ax.legend(); ax.grid(alpha=.2); save(fig,'sensitivity_ccr.png')
    fig,ax=plt.subplots(figsize=(6.3,3.4))
    for mode,style,label in [('solo_80211','o-','Solo'),('full_wireless','s--','Full')]:
        group=[r for r in data['multidag'] if r['mode']==mode]
        ax.plot([r['count'] for r in group],[r['makespan_s'] for r in group],style,label=label,mfc='none')
    ax.set(xlabel='Number of injected workflows',ylabel='Makespan (s)',xticks=range(1,6)); ax.legend(); ax.grid(alpha=.2)
    save(fig,'multidag.png')
    # Route load on the exact 4x4, 20-task factorial case.
    legacy=module('minimal_grid_plot',INPUT/'run_full_scheduler_comparison.py')
    topology=network(*legacy.generate_network(4)); configure_wireless(topology,'solo_80211')
    tasks,edges=legacy._make_dag_large()
    fig,axes=plt.subplots(1,2,figsize=(7.2,3.6)); route_stats=[]
    for ax,route in zip(axes,('widest_path','minimum_hop')):
        row=get(4,'large',route,'heft'); planner=WidestPathRouting() if route=='widest_path' else MinimumHopRouting()
        counts=collections.Counter(); lengths=[]
        for edge in edges:
            a,b=(row['placement'][edge[key]] for key in ('from','to'))
            if a!=b:
                path=planner.get_path(a,b,topology); lengths.append(len(path))
                for lid in path:
                    l=topology.links[lid]; counts[tuple(sorted((l.from_node,l.to_node)))]+=1
        undirected={tuple(sorted((l.from_node,l.to_node))) for l in topology.links.values()}
        for a,b in undirected:
            a_pos=topology.nodes[a].position;b_pos=topology.nodes[b].position
            count=counts.get(tuple(sorted((a,b))),0)
            ax.plot([a_pos.x,b_pos.x],[a_pos.y,b_pos.y],color=plt.cm.Blues(.3+.7*count/max(counts.values())) if count else '.85',lw=1+.35*count)
        for n,node in topology.nodes.items():
            ax.plot(node.position.x,node.position.y,'ko',ms=4)
            ax.annotate(n[1:],(node.position.x,node.position.y),xytext=(3,3),textcoords='offset points',fontsize=8)
        ax.set_title(f"{'Widest path' if route=='widest_path' else 'Minimum hop'}: {row['makespan_s']:.1f} s")
        ax.set_aspect('equal');ax.invert_yaxis();ax.axis('off')
        route_stats.append({'routing':route,'remote_MB':row['remote_payload_bytes']/1e6,'MB_hops':row['byte_hops']/1e6,
                            'mean_hops':statistics.mean(lengths),'used_undirected_links':len(counts),'max_flows':max(counts.values())})
    save(fig,'routing_topo_4x4_largedag.png')
    return {'cases':cases,'inversions':sum(c['inversion'] for c in cases),'mean_regret':statistics.mean(c['ratio']-1 for c in cases),
            'max_regret':max(c['ratio']-1 for c in cases),'ccr':ccr,'route_stats':route_stats}
