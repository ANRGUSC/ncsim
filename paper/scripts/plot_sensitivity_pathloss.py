"""Generate path loss sensitivity plot for ncsim paper (fig:pathloss)."""
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

n_vals = [2.0, 2.5, 3.0, 3.5]
slowdown = [1.33, 1.80, 2.00, 104.61]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

ax.plot(n_vals, slowdown, 's-', color='#2266bb', linewidth=2, markersize=5,
        label='Slowdown (Bianchi/none)')

# Regime cliff annotation
ax.annotate('regime cliff', xy=(3.48, 100), xytext=(3.3, 45),
            fontsize=7, color='#cc3333',
            arrowprops=dict(arrowstyle='->', color='#cc3333', lw=1.5),
            ha='right')

ax.set_xlabel(r'Path Loss Exponent $n$')
ax.set_ylabel(r'Slowdown Factor ($\times$)')
ax.set_xlim(1.8, 3.7)
ax.set_ylim(0, 110)
ax.set_xticks([2.0, 2.5, 3.0, 3.5])
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper left')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'sensitivity_pathloss.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
