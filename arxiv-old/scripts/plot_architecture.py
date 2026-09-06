"""Generate architecture block diagram for ncsim paper (fig:architecture)."""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

# IEEE style
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 9,
    'axes.labelsize': 9,
    'xtick.labelsize': 7,
    'ytick.labelsize': 7,
})

fig, ax = plt.subplots(figsize=(3.5, 3.0))
ax.set_xlim(0, 10)
ax.set_ylim(0, 10)
ax.axis('off')

box_color = '#e8e8e8'
border_color = '#333333'
arrow_color = '#555555'

def draw_box(ax, x, y, w, h, text, fontsize=8, bold=False, fc=box_color):
    rect = mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.15",
                                    facecolor=fc, edgecolor=border_color, linewidth=1.2)
    ax.add_patch(rect)
    weight = 'bold' if bold else 'normal'
    ax.text(x + w/2, y + h/2, text, ha='center', va='center',
            fontsize=fontsize, fontweight=weight, family='serif')

def draw_arrow(ax, x, y1, y2):
    ax.annotate('', xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(arrowstyle='->', color=arrow_color, lw=1.5))

# Input box
draw_box(ax, 1.5, 8.5, 7, 0.8, 'Input:  Scenario YAML → Scenario Loader', fontsize=8, bold=True)

# Arrow
draw_arrow(ax, 5, 8.5, 8.0)

# Core box
draw_box(ax, 1.5, 7.2, 7, 0.7, 'Core:  Network + DAGs + Config', fontsize=8, bold=True)

# Arrow
draw_arrow(ax, 5, 7.2, 6.7)

# Simulation Engine (large box)
engine_rect = mpatches.FancyBboxPatch((1.0, 2.5), 8, 4.1, boxstyle="round,pad=0.15",
                                       facecolor='#f5f5f5', edgecolor=border_color, linewidth=1.5)
ax.add_patch(engine_rect)
ax.text(5, 6.2, 'Simulation Engine', ha='center', va='center',
        fontsize=9, fontweight='bold', family='serif')

# Sub-items inside
items = [
    'Event Queue (min-heap, 6 event types)',
    'Execution Engine (state machine)',
]
hookitems = [
    '<- Scheduler (HEFT, CPOP, RoundRobin, Manual)',
    '<- Routing Model (Direct, Widest, Shortest)',
    '<- Interference Model (None, CSMA Bianchi)',
]

y_pos = 5.6
for item in items:
    ax.text(2.0, y_pos, item, ha='left', va='center', fontsize=7, family='serif')
    y_pos -= 0.55

for item in hookitems:
    ax.text(2.4, y_pos, item, ha='left', va='center', fontsize=7, family='serif',
            color='#2255aa')
    y_pos -= 0.55

# Arrow
draw_arrow(ax, 5, 2.5, 2.0)

# Output box
draw_box(ax, 1.5, 1.0, 7, 0.8, 'Output:  JSONL Trace + Metrics JSON', fontsize=8, bold=True)

plt.tight_layout(pad=0.3)
out = Path(__file__).resolve().parent.parent / 'figures' / 'architecture.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
