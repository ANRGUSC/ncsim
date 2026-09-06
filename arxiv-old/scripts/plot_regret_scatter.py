"""Generate regret bar chart for ncsim paper (fig:regret_scatter)."""
import json
import sys
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 9,
    'axes.labelsize': 9,
    'xtick.labelsize': 6.5,
    'ytick.labelsize': 7,
})

script_dir = Path(__file__).resolve().parent
results_path = script_dir.parent / '_results' / 'scheduler_comparison.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_scheduler_comparison.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

regret_entries = data['regret']

# Build ordered list: grouped by network, then DAG, then routing
network_order = ['small', 'medium', 'large']
network_labels = {'small': '2×2', 'medium': '3×3', 'large': '4×4'}
dag_order = ['small', 'medium', 'large']
dag_labels = {'small': '5T', 'medium': '10T', 'large': '20T'}
routing_order = ['widest_path', 'shortest_path']
routing_labels = {'widest_path': 'WP', 'shortest_path': 'SP'}

# Index regret entries for lookup
regret_map = {}
for r in regret_entries:
    key = (r['network'], r['dag'], r['routing'])
    regret_map[key] = r

labels = []
ratios = []
is_inversion = []

for net in network_order:
    for dag in dag_order:
        for routing in routing_order:
            entry = regret_map[(net, dag, routing)]
            ratio = entry['makespan_chosen'] / entry['makespan_optimal']
            labels.append(f"{dag_labels[dag]}/{routing_labels[routing]}")
            ratios.append(ratio)
            is_inversion.append(ratio > 1.005)

# X positions with gaps between network groups
positions = []
pos = 0
group_centers = []
group_start = 0
for i in range(len(ratios)):
    positions.append(pos)
    if (i + 1) % 6 == 0 and i < len(ratios) - 1:
        group_centers.append((group_start + pos) / 2)
        group_start = pos + 2
        pos += 2  # gap between groups
    else:
        pos += 1
group_centers.append((group_start + positions[-1]) / 2)

fig, ax = plt.subplots(figsize=(3.5, 2.8))

colors = ['#cc4444' if inv else '#7799bb' for inv in is_inversion]
bars = ax.bar(positions, ratios, color=colors, width=0.7, edgecolor='white',
              linewidth=0.3)

# Reference line at y=1.0
ax.axhline(y=1.0, color='gray', linestyle='--', linewidth=0.8, zorder=0)
ax.text(positions[-1] + 0.5, 1.0, 'Oracle Baseline\n(zero regret)',
        va='center', ha='left', fontsize=5.5, color='gray', style='italic')

# Label bars with regret > 1.0
for pos_i, ratio, inv in zip(positions, ratios, is_inversion):
    if inv:
        ax.text(pos_i, ratio + 0.04, f'{ratio:.2f}×', ha='center', va='bottom',
                fontsize=5.5, color='#cc4444', fontweight='bold')

ax.set_xticks(positions)
ax.set_xticklabels(labels, rotation=60, ha='right')
ax.set_ylabel('Regret Ratio (naive / oracle)')
ax.set_ylim(0, max(ratios) * 1.15)

# Network group labels
for center, net in zip(group_centers, network_order):
    ax.text(center, -0.45, network_labels[net], ha='center', va='top',
            fontsize=8, fontweight='bold', transform=ax.get_xaxis_transform())

ax.grid(True, axis='y', color='#cccccc', linewidth=0.5)

plt.tight_layout(pad=0.3)
plt.subplots_adjust(bottom=0.28)
out = script_dir.parent / 'figures' / 'regret_scatter.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
