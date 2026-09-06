"""Generate Bianchi Fig 6 reproduction for ncsim paper (fig:bianchi_fig6)."""
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
results_path = script_dir.parent / '_results' / 'bianchi_validation.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_bianchi_external_validation.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

# Find the two Fig 6 configs: W=32 m=5 and W=128 m=3
cfg_w32 = next(c for c in data['configs'] if c['W'] == 32 and c['m'] == 5)
cfg_w128 = next(c for c in data['configs'] if c['W'] == 128 and c['m'] == 3)

n_stations = [s['n'] for s in cfg_w32['stations']]
s_w32 = [s['S_computed'] for s in cfg_w32['stations']]
s_w128 = [s['S_computed'] for s in cfg_w128['stations']]

fig, ax = plt.subplots(figsize=(3.5, 2.7))

ax.plot(n_stations, s_w32, 'o-', color='#2266bb', linewidth=2,
        markersize=4, label='$W=32$, $m=5$')
ax.plot(n_stations, s_w128, '^-', color='#cc3333', linewidth=2,
        markersize=5, label='$W=128$, $m=3$')

ax.set_xlabel('Number of stations $n$')
ax.set_ylabel('Normalized throughput $S$')
ax.set_xlim(0, max(n_stations) + 5)
ax.set_ylim(0.5, 0.9)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper right')

plt.tight_layout(pad=0.3)
out = script_dir.parent / 'figures' / 'bianchi_fig6.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
