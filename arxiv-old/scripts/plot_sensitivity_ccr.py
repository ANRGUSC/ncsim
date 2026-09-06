"""Generate CCR sensitivity plot for ncsim paper (fig:ccr)."""
import json
import sys
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 9,
    'axes.labelsize': 9,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
})

script_dir = Path(__file__).resolve().parent
results_path = script_dir.parent / '_results' / 'sensitivity_ccr.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_sensitivity_ccr.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

# Group by dag_size: small=5-task, medium=10-task, large=20-task
results = data['results']
small = [r for r in results if r['dag_size'] == 'small']
medium = [r for r in results if r['dag_size'] == 'medium']
large = [r for r in results if r['dag_size'] == 'large']

data_sizes = [r['data_size_MB'] for r in small]
s5 = [r['slowdown_factor'] for r in small]
s10 = [r['slowdown_factor'] for r in medium]
s20 = [r['slowdown_factor'] for r in large]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

ax.plot(data_sizes, s20, 's-', color='#2266bb', linewidth=2, markersize=5, label='20-task')
ax.plot(data_sizes, s10, '^-', color='#dd8800', linewidth=1.5, markersize=5, label='10-task')
ax.plot(data_sizes, s5, 'o-', color='#338833', linewidth=1.5, markersize=4, label='5-task')

ax.set_xscale('log')
ax.set_xlabel('Data Size per Edge (MB)')
ax.set_ylabel(r'Slowdown Factor ($\times$)')
ax.set_xlim(0.8, 120)
ax.set_ylim(0.8, 4.2)
ax.set_xticks(data_sizes)
ax.set_xticklabels([str(int(x)) if x == int(x) else str(x) for x in data_sizes])
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper right')

plt.tight_layout(pad=0.3)
out = script_dir.parent / 'figures' / 'sensitivity_ccr.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
