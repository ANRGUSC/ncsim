"""Generate multi-DAG scaling plot for ncsim paper (fig:multidag)."""
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
results_path = script_dir.parent / '_results' / 'multidag_contention.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_multidag_contention.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

k_vals = [r['num_dags'] for r in data['results']]
no_interf = [r['makespan_none'] for r in data['results']]
csma = [r['makespan_csma_bianchi'] for r in data['results']]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

ax.plot(k_vals, no_interf, 'o-', color='#777777', linewidth=1.5, markersize=4,
        label='No interference')
ax.plot(k_vals, csma, 's-', color='#cc3333', linewidth=2, markersize=5,
        label='CSMA/CA Bianchi')

ax.set_xlabel(r'Number of Concurrent DAGs ($k$)')
ax.set_ylabel('Makespan (s)')
ax.set_xlim(0.5, max(k_vals) + 0.5)
ax.set_ylim(0, max(csma) * 1.15)
ax.set_xticks(k_vals)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper left')

plt.tight_layout(pad=0.3)
out = script_dir.parent / 'figures' / 'multidag.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
