"""Generate regret scatter plot for ncsim paper (fig:regret_scatter)."""
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

# Oracle = Naive points (on diagonal)
diag_x = [11.434, 11.434, 20.071, 26.032, 43.887, 36.510,
           12.375, 12.375, 69.282, 8.934, 676.194]
diag_y = diag_x[:]

# Points with regret (oracle_x, naive_y)
regret_points = [
    (36.325, 50.819),
    (25.040, 28.832),
    (55.312, 56.102),
    (53.967, 315.197),
    (253.907, 1396.857),
    (184.773, 434.129),
    (937.411, 1524.713),
]

# Red arrows (rank inversions) - large regret
red_arrows = [
    (53.967, 53.967, 53.967, 315.197),
    (253.907, 253.907, 253.907, 1396.857),
    (184.773, 184.773, 184.773, 434.129),
    (937.411, 937.411, 937.411, 1524.713),
]

# Orange arrows (moderate regret)
orange_arrows = [
    (36.325, 36.325, 36.325, 50.819),
    (25.040, 25.040, 25.040, 28.832),
    (55.312, 55.312, 55.312, 56.102),
]

# Labels for extreme points
labels = [
    (60, 330, '484%'),
    (260, 1410, '450%'),
    (190, 450, '135%'),
    (937, 1540, '63%'),
]

fig, ax = plt.subplots(figsize=(3.5, 3.2))

# Diagonal line
ax.plot([0, 1100], [0, 1100], '--', color='gray', linewidth=0.8, alpha=0.5, label='Zero regret')

# All points
all_x = diag_x + [p[0] for p in regret_points]
all_y = diag_y + [p[1] for p in regret_points]
ax.plot(all_x, all_y, 'o', color='#2266bb', markersize=3.5, label='Oracle = Naive',
        markeredgewidth=0.5, markerfacecolor='none', markeredgecolor='#2266bb')

# Red arrows
for x1, y1, x2, y2 in red_arrows:
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color='#cc4444', lw=1.5))

# Orange arrows
for x1, y1, x2, y2 in orange_arrows:
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle='->', color='#dd8800', lw=1.2))

# Labels
for x, y, txt in labels:
    ha = 'center' if x > 900 else 'left'
    va = 'bottom' if x > 900 else 'center'
    ax.text(x, y, txt, fontsize=5.5, color='#cc4444', ha=ha, va=va)

ax.set_xlabel('Oracle makespan under csma_bianchi (s)')
ax.set_ylabel('Naive makespan under csma_bianchi (s)')
ax.set_xlim(0, 1100)
ax.set_ylim(0, 1650)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=6, loc='upper left')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'regret_scatter.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
