"""Generate MCS staircase plot for ncsim paper (fig:exp1)."""
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

# MCS staircase data
staircase_x = [
    1, 8.30, 8.30, 10.46, 10.46, 13.16, 13.16, 16.57,
    16.57, 20.86, 20.86, 28.36, 28.36, 35.70, 35.70, 48.53,
    48.53, 65.97, 65.97, 83.05, 83.05, 104.55, 104.55, 131.62,
    131.62, 145,
]
staircase_y = [
    17.925, 17.925, 16.125, 16.125, 14.338, 14.338, 12.900, 12.900,
    10.750, 10.750, 9.675, 9.675, 8.600, 8.600, 6.450, 6.450,
    4.300, 4.300, 3.225, 3.225, 2.150, 2.150, 1.075, 1.075,
    0, 0,
]

# Verified points
vp_x = [1, 12, 30, 50, 75, 105, 140]
vp_y = [17.925, 14.338, 8.600, 4.300, 3.225, 1.075, 0]

fig, ax = plt.subplots(figsize=(3.5, 2.2))

ax.plot(staircase_x, staircase_y, color='#2266bb', linewidth=2, label='MCS staircase')
ax.plot(vp_x, vp_y, 'o', color='#cc3333', markersize=4, label='Verified points', zorder=5)

ax.set_xlabel('Distance (m)')
ax.set_ylabel('Data Rate (MB/s)')
ax.set_xlim(0, 145)
ax.set_ylim(0, 20)
ax.grid(True, color='#cccccc', linewidth=0.5)
ax.legend(fontsize=7, loc='upper right')

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'exp1_mcs_staircase.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
