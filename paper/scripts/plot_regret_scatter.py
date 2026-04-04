"""Generate regret scatter plot for ncsim paper (fig:regret_scatter)."""
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
results_path = script_dir.parent / '_results' / 'rank_inversion_sweep.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_rank_inversion_sweep.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

scenarios = data['scenarios']

# Compute oracle vs naive makespans for each scenario
diag_x, diag_y = [], []
regret_points = []  # (oracle, naive)

for s in scenarios:
    oracle = s['bianchi_makespans'][s['best_bianchi']]
    naive = s['bianchi_makespans'][s['best_none']]
    if s['inversion']:
        regret_points.append((oracle, naive))
    else:
        diag_x.append(oracle)
        diag_y.append(oracle)

fig, ax = plt.subplots(figsize=(3.5, 3.2))

# Axis limits
all_vals = diag_x + [p[0] for p in regret_points] + [p[1] for p in regret_points]
max_val = max(all_vals) * 1.1

# Diagonal line
ax.plot([0, max_val], [0, max_val], '--', color='gray', linewidth=0.8, alpha=0.5,
        label='Zero regret')

# All points
all_x = diag_x + [p[0] for p in regret_points]
all_y = diag_y + [p[1] for p in regret_points]
ax.plot(all_x, all_y, 'o', color='#2266bb', markersize=3.5, label='Oracle = Naive',
        markeredgewidth=0.5, markerfacecolor='none', markeredgecolor='#2266bb')

# Arrows from diagonal to actual point, colored by regret magnitude
for oracle, naive in regret_points:
    regret_pct = (naive - oracle) / oracle * 100 if oracle > 0 else 0
    color = '#cc4444' if regret_pct > 50 else '#dd8800'
    lw = 1.5 if regret_pct > 50 else 1.2
    ax.annotate('', xy=(oracle, naive), xytext=(oracle, oracle),
                arrowprops=dict(arrowstyle='->', color=color, lw=lw))
    # Label for significant regret
    if regret_pct > 50:
        ax.text(oracle * 1.05, naive * 1.01, f'{regret_pct:.0f}%',
                fontsize=5.5, color='#cc4444')

ax.set_xlabel('Oracle makespan under csma_bianchi (s)')
ax.set_ylabel('Naive makespan under csma_bianchi (s)')
ax.set_xlim(0, max_val)
ax.set_ylim(0, max_val * 1.1)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=6, loc='upper left')

plt.tight_layout(pad=0.3)
out = script_dir.parent / 'figures' / 'regret_scatter.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
