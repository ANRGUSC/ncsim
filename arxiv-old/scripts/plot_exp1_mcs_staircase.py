"""Generate MCS staircase plot for ncsim paper (fig:exp1).

Computes the rate staircase directly from ncsim's WiFi model functions,
so it always reflects the current MCS table and RF parameters.
"""
import sys
import matplotlib.pyplot as plt
from pathlib import Path

# Add project root to path for ncsim imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from ncsim.models.wifi import (
    snr_to_rate_mbps, path_loss_dB, rate_mbps_to_MBps, RFConfig,
)

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 9,
    'axes.labelsize': 9,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
})

rf = RFConfig()

# Sweep distances at fine resolution to capture MCS transitions
distances = [d / 10.0 for d in range(10, 1451)]  # 1.0 to 145.0m by 0.1m
rates = []
for d in distances:
    pl = path_loss_dB(d, rf.freq_ghz, rf.path_loss_exponent)
    rx_power = rf.tx_power_dBm - pl
    snr = rx_power - rf.noise_floor_dBm
    rate_mbps = snr_to_rate_mbps(snr, rf.wifi_standard, rf.channel_width_mhz)
    rates.append(rate_mbps_to_MBps(rate_mbps))

# Build staircase coordinates (step function)
staircase_x, staircase_y = [distances[0]], [rates[0]]
for i in range(1, len(distances)):
    if rates[i] != rates[i - 1]:
        # Step down: add point at current distance with old rate, then new rate
        staircase_x.append(distances[i])
        staircase_y.append(rates[i - 1])
    staircase_x.append(distances[i])
    staircase_y.append(rates[i])

# Compute verified points at specific distances
vp_x = [1, 12, 30, 50, 75, 105, 140]
vp_y = []
for d in vp_x:
    pl = path_loss_dB(d, rf.freq_ghz, rf.path_loss_exponent)
    rx_power = rf.tx_power_dBm - pl
    snr = rx_power - rf.noise_floor_dBm
    rate_mbps = snr_to_rate_mbps(snr, rf.wifi_standard, rf.channel_width_mhz)
    vp_y.append(rate_mbps_to_MBps(rate_mbps))

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
