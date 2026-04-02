"""Generate parallel link separation plot for ncsim paper (fig:exp2)."""
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

# Contention regime data
cont_x = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70]
cont_y = [3.787]*14

# Hidden terminal regime data
ht_x = [75, 80, 85, 90, 95, 100, 110, 120, 130, 140, 150, 175, 200]
ht_y = [3.225, 3.225, 3.225, 4.300, 4.300, 4.300, 4.300, 4.300,
        6.450, 6.450, 6.450, 6.450, 6.450]

# Verified contention points
vc_x = [5, 15, 30, 50, 70]
vc_y = [3.787]*5

# Verified hidden terminal points
vht_x = [75, 90, 100, 130, 200]
vht_y = [3.225, 4.300, 4.300, 6.450, 6.450]

fig, ax = plt.subplots(figsize=(3.5, 2.5))

# Solo rate reference
ax.axhline(y=8.600, color='gray', linewidth=0.8, linestyle='--', alpha=0.5)
ax.text(30, 9.0, 'solo rate', fontsize=6, color='gray', alpha=0.7)

# CS range marker
ax.axvline(x=71.2, color='#cc4444', linewidth=0.8, linestyle='--', alpha=0.6)
ax.text(73, 5.5, 'CS range', fontsize=6, color='#cc4444', rotation=90, va='center')

# Main data
ax.plot(cont_x, cont_y, color='#2266bb', linewidth=2, label='Contention (Bianchi)')
ax.plot(ht_x, ht_y, color='#dd8800', linewidth=2, label='Hidden terminal (SINR)')

# Verified markers
ax.plot(vc_x, vc_y, 's', color='#2266bb', markersize=4, zorder=5)
ax.plot(vht_x, vht_y, '^', color='#dd8800', markersize=5, zorder=5)

# Hidden terminal dip annotation
ax.annotate('hidden terminal\ndip', xy=(76, 3.1), xytext=(82, 1.8),
            fontsize=6, color='#555555',
            arrowprops=dict(arrowstyle='->', color='#555555', lw=1.2))

ax.set_xlabel('Link Separation (m)')
ax.set_ylabel('Effective Rate per Link (MB/s)')
ax.set_xlim(0, 210)
ax.set_ylim(0, 10)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=6, loc='lower right')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'exp2_parallel_separation.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
