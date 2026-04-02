"""Generate Bianchi Fig 6 reproduction for ncsim paper (fig:bianchi_fig6)."""
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

# W=32, m=5
n_stations = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
s_w32 = [0.810153, 0.75788, 0.723136, 0.697548, 0.677235,
         0.660309, 0.645739, 0.632901, 0.621392, 0.610936]
# W=128, m=3
s_w128 = [0.825024, 0.826309, 0.813031, 0.798105, 0.783692,
          0.770226, 0.757731, 0.746123, 0.7353, 0.725166]

fig, ax = plt.subplots(figsize=(3.5, 2.7))

ax.plot(n_stations, s_w32, 'o-', color='#2266bb', linewidth=2,
        markersize=4, label='$W=32$, $m=5$')
ax.plot(n_stations, s_w128, '^-', color='#cc3333', linewidth=2,
        markersize=5, label='$W=128$, $m=3$')

ax.set_xlabel('Number of stations $n$')
ax.set_ylabel('Normalized throughput $S$')
ax.set_xlim(0, 55)
ax.set_ylim(0.5, 0.9)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper right')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'bianchi_fig6.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
