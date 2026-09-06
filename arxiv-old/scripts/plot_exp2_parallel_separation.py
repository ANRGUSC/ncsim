"""Generate parallel link separation plot for ncsim paper (fig:exp2)."""
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
results_path = script_dir.parent / '_results' / 'exp2_separation.json'

if not results_path.exists():
    print(f"Error: {results_path} not found. Run run_interference_verification.py first.")
    sys.exit(1)

with open(results_path) as f:
    data = json.load(f)

solo_rate = data['solo_rate_MBps']
cs_range = data['cs_range_m']
results = data['results']

# Split into contention and hidden terminal regimes
cont = [r for r in results if r['regime'] == 'contention']
ht = [r for r in results if r['regime'] == 'hidden_terminal']

cont_x = [r['separation_m'] for r in cont]
cont_y = [r['predicted_rate_MBps'] for r in cont]
ht_x = [r['separation_m'] for r in ht]
ht_y = [r['predicted_rate_MBps'] for r in ht]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

# Solo rate reference
ax.axhline(y=solo_rate, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
ax.text(30, solo_rate + 0.4, 'solo rate', fontsize=6, color='gray', alpha=0.7)

# CS range marker
ax.axvline(x=cs_range, color='#cc4444', linewidth=0.8, linestyle='--', alpha=0.6)
ax.text(cs_range + 2, solo_rate * 0.65, 'CS range', fontsize=6, color='#cc4444',
        rotation=90, va='center')

# Main data
ax.plot(cont_x, cont_y, 's-', color='#2266bb', linewidth=2, markersize=4,
        label='Contention (Bianchi)')
ax.plot(ht_x, ht_y, '^-', color='#dd8800', linewidth=2, markersize=5,
        label='Hidden terminal (capture)')

# Hidden terminal dip annotation (if there's a dip just past CS range)
if ht and cont:
    first_ht_rate = ht_y[0]
    last_cont_rate = cont_y[-1]
    if first_ht_rate < last_cont_rate:
        ax.annotate('hidden terminal\ndip', xy=(ht_x[0], first_ht_rate - 0.1),
                    xytext=(ht_x[0] + 6, first_ht_rate - 1.5),
                    fontsize=6, color='#555555',
                    arrowprops=dict(arrowstyle='->', color='#555555', lw=1.2))

ax.set_xlabel('Link Separation (m)')
ax.set_ylabel('Effective Rate per Link (MB/s)')
ax.set_xlim(0, 210)
ax.set_ylim(0, solo_rate * 1.2)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=6, loc='lower right')

plt.tight_layout(pad=0.3)
out = script_dir.parent / 'figures' / 'exp2_parallel_separation.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
