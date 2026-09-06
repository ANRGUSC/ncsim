"""Generate routing diamond topology diagram for ncsim paper (fig:routing_diamond)."""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'Times', 'DejaVu Serif'],
    'font.size': 9,
    'axes.labelsize': 9,
})

def draw_diamond(ax, highlight='top', color_sel='#2266bb'):
    ax.set_xlim(-0.5, 5.5)
    ax.set_ylim(-1.2, 1.2)
    ax.axis('off')
    ax.set_aspect('equal')

    # Node positions
    nodes = {'src': (0, 0), 'R_f': (2.5, 0.8), 'R_w': (2.5, -0.8), 'dst': (5, 0)}
    labels = {'src': 'src', 'R_f': r'R$_f$', 'R_w': r'R$_w$', 'dst': 'dst'}

    # Edge labels
    top_label = '20 MB/s, 1 ms'
    bot_label = '200 MB/s, 50 ms'

    # Draw edges
    dim_color = '#bbbbbb'
    dim_lw = 1.0
    sel_lw = 2.5

    if highlight == 'top':
        # Top path highlighted
        for (n1, n2), lbl in [(('src','R_f'), top_label), (('R_f','dst'), top_label)]:
            ax.annotate('', xy=nodes[n2], xytext=nodes[n1],
                       arrowprops=dict(arrowstyle='->', color=color_sel, lw=sel_lw))
            mx = (nodes[n1][0]+nodes[n2][0])/2
            my = (nodes[n1][1]+nodes[n2][1])/2
            ax.text(mx, my+0.15, lbl, fontsize=5.5, ha='center', va='bottom',
                   color=color_sel, bbox=dict(fc='white', ec='none', pad=0.5))

        for (n1, n2), lbl in [(('src','R_w'), bot_label), (('R_w','dst'), bot_label)]:
            ax.annotate('', xy=nodes[n2], xytext=nodes[n1],
                       arrowprops=dict(arrowstyle='->', color=dim_color, lw=dim_lw))
            mx = (nodes[n1][0]+nodes[n2][0])/2
            my = (nodes[n1][1]+nodes[n2][1])/2
            ax.text(mx, my-0.15, lbl, fontsize=5.5, ha='center', va='top',
                   color=dim_color, bbox=dict(fc='white', ec='none', pad=0.5))
    else:
        # Bottom path highlighted
        for (n1, n2), lbl in [(('src','R_f'), top_label), (('R_f','dst'), top_label)]:
            ax.annotate('', xy=nodes[n2], xytext=nodes[n1],
                       arrowprops=dict(arrowstyle='->', color=dim_color, lw=dim_lw))
            mx = (nodes[n1][0]+nodes[n2][0])/2
            my = (nodes[n1][1]+nodes[n2][1])/2
            ax.text(mx, my+0.15, lbl, fontsize=5.5, ha='center', va='bottom',
                   color=dim_color, bbox=dict(fc='white', ec='none', pad=0.5))

        for (n1, n2), lbl in [(('src','R_w'), bot_label), (('R_w','dst'), bot_label)]:
            ax.annotate('', xy=nodes[n2], xytext=nodes[n1],
                       arrowprops=dict(arrowstyle='->', color=color_sel, lw=sel_lw))
            mx = (nodes[n1][0]+nodes[n2][0])/2
            my = (nodes[n1][1]+nodes[n2][1])/2
            ax.text(mx, my-0.15, lbl, fontsize=5.5, ha='center', va='top',
                   color=color_sel, bbox=dict(fc='white', ec='none', pad=0.5))

    # Draw nodes on top
    for name, (x, y) in nodes.items():
        circle = plt.Circle((x, y), 0.25, fc='white', ec='#333333', linewidth=1.5, zorder=5)
        ax.add_patch(circle)
        ax.text(x, y, labels[name], ha='center', va='center', fontsize=8,
               fontweight='normal', family='serif', zorder=6)


fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(3.5, 3.2))

draw_diamond(ax1, highlight='top', color_sel='#2266bb')
ax1.set_title('(a) Shortest-path: top path (lower latency)\n'
              'Makespan: 1.0 + (100/20 + 0.002) + 1.0 = 7.0 s',
              fontsize=6.5, pad=3)

draw_diamond(ax2, highlight='bottom', color_sel='#dd8800')
ax2.set_title('(b) Widest-path: bottom path (higher bandwidth)\n'
              'Makespan: 1.0 + (100/200 + 0.1) + 1.0 = 2.6 s',
              fontsize=6.5, pad=3)

plt.tight_layout(pad=0.5)
out = Path(__file__).resolve().parent.parent / 'figures' / 'routing_diamond.png'
fig.savefig(out, dpi=300, bbox_inches='tight', facecolor='white')
plt.close()
print(f'Saved {out}')
