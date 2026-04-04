"""Generate path loss sensitivity plot for ncsim paper (fig:pathloss)."""
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
results_path = script_dir.parent / '_results' / 'sensitivity_pathloss.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_sensitivity_pathloss.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

results = [r for r in data['results'] if r['slowdown_factor'] is not None]
n_vals = [r['path_loss_exponent'] for r in results]
slowdown = [r['slowdown_factor'] for r in results]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

ax.plot(n_vals, slowdown, 's-', color='#2266bb', linewidth=2, markersize=6,
        label='Slowdown (Bianchi/none)')

# Annotate each point with its value
for x, y in zip(n_vals, slowdown):
    ax.annotate(f'{y:.1f}$\\times$', xy=(x, y), xytext=(0, 8),
                textcoords='offset points', fontsize=7, ha='center',
                color='#2266bb')

ax.set_xlabel(r'Path Loss Exponent $n$')
ax.set_ylabel(r'Slowdown Factor ($\times$)')
ax.set_xlim(1.8, max(n_vals) + 0.25)
ax.set_ylim(0, 4.0)
ax.set_xticks(n_vals)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper left')

plt.tight_layout(pad=0.3)
out = script_dir.parent / 'figures' / 'sensitivity_pathloss.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
