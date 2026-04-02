"""Generate CCR sensitivity plot for ncsim paper (fig:ccr)."""
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

data_sizes = [1, 2, 5, 10, 20, 50, 100]

# 20-task
s20 = [1.08, 1.54, 3.55, 2.63, 3.82, 2.24, 1.00]
# 10-task
s10 = [1.14, 1.37, 1.38, 1.96, 2.13, 1.00, 1.00]
# 5-task
s5 = [1.06, 1.12, 1.29, 1.47, 1.00, 1.00, 1.00]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

ax.plot(data_sizes, s20, 's-', color='#2266bb', linewidth=2, markersize=5, label='20-task')
ax.plot(data_sizes, s10, '^-', color='#dd8800', linewidth=1.5, markersize=5, label='10-task')
ax.plot(data_sizes, s5, 'o-', color='#338833', linewidth=1.5, markersize=4, label='5-task')

ax.set_xscale('log')
ax.set_xlabel('Data Size per Edge (MB)')
ax.set_ylabel(r'Slowdown Factor ($\times$)')
ax.set_xlim(0.8, 120)
ax.set_ylim(0.8, 4.2)
ax.set_xticks([1, 2, 5, 10, 20, 50, 100])
ax.set_xticklabels(['1', '2', '5', '10', '20', '50', '100'])
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper right')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'sensitivity_ccr.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
