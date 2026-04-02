"""Generate multi-DAG scaling plot for ncsim paper (fig:multidag)."""
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

k_vals = [1, 2, 3, 4, 5]
no_interf = [8.43, 10.43, 13.33, 15.32, 18.03]
csma = [12.37, 17.75, 25.35, 32.56, 39.92]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

ax.plot(k_vals, no_interf, 'o-', color='#777777', linewidth=1.5, markersize=4,
        label='No interference')
ax.plot(k_vals, csma, 's-', color='#cc3333', linewidth=2, markersize=5,
        label='CSMA/CA Bianchi')

ax.set_xlabel(r'Number of Concurrent DAGs ($k$)')
ax.set_ylabel('Makespan (s)')
ax.set_xlim(0.5, 5.5)
ax.set_ylim(0, 45)
ax.set_xticks([1, 2, 3, 4, 5])
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper left')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'multidag.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
