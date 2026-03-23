# Keyboard Shortcuts

ncsim-viz supports keyboard shortcuts for efficient navigation and playback control. Press ++question++ at any time to display the shortcut overlay within the application.

---

## Full Reference

| Key | Action |
|---|---|
| ++space++ | Play / Pause simulation |
| ++left++ | Step backward one event |
| ++right++ | Step forward one event |
| ++shift+left++ | Jump backward 10% of the makespan |
| ++shift+right++ | Jump forward 10% of the makespan |
| ++home++ | Jump to the start of the simulation (time 0) |
| ++end++ | Jump to the end of the simulation (makespan) |
| ++plus++ | Increase playback speed one step |
| ++minus++ | Decrease playback speed one step |
| ++1++ | Switch to the Overview tab |
| ++2++ | Switch to the Network tab |
| ++3++ | Switch to the DAG tab |
| ++4++ | Switch to the Schedule tab |
| ++5++ | Switch to the Simulation tab |
| ++6++ | Switch to the Parameters tab |
| ++d++ | Toggle dark / light theme |
| ++question++ | Show / hide keyboard shortcuts overlay |

---

## Playback Speed Levels

The ++plus++ and ++minus++ keys cycle through the following speed values:

| Level | Speed |
|---|---|
| 1 | 0.25x |
| 2 | 0.5x |
| 3 | 1x (default) |
| 4 | 2x |
| 5 | 5x |
| 6 | 10x |

You can also click the speed buttons in the transport bar on the Simulation tab to jump directly to any speed level.

---

## Scope and Behavior

!!! info "Shortcuts work on all tabs"
    Tab switching (++1++ through ++6++) and the theme toggle (++d++) work from any visualization tab, not just the Simulation tab. Playback controls (++space++, arrow keys, ++home++/++end++, ++plus++/++minus++) are active whenever the Simulation tab's playback engine is loaded.

!!! note "Text input fields"
    Keyboard shortcuts are automatically disabled when focus is inside a text input field or text area, so you can type normally in the Configure & Run form without triggering shortcuts.

---

## Shortcut Overlay

Press ++question++ to open the shortcuts overlay. The overlay displays all shortcuts in a modal dialog. Press ++question++ again or click outside the modal to dismiss it. You can also open the overlay by clicking the keyboard icon in the header toolbar.

---

## Related Pages

- **[Visualization Tabs](visualization-tabs.md)** -- Detailed guide to each tab and its interactive features
- **[Viz Overview](viz-overview.md)** -- Architecture and workflow overview
