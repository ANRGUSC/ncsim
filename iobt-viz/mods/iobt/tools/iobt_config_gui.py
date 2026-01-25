"""
IoBT-Viz Configuration Generator GUI

A standalone Tkinter-based application for generating Lua configuration
files for IoBT-Viz simulations.

Usage: python iobt_config_gui.py
  or:  runconfig.bat (from OpenRAModSDK folder)
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iobt_config_generator import IoBTConfigGenerator


class ScrollableFrame(ttk.Frame):
    """A scrollable frame container."""

    def __init__(self, container, *args, **kwargs):
        super().__init__(container, *args, **kwargs)

        # Create canvas and scrollbar
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        # Configure canvas scrolling
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_frame = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Bind canvas resize to adjust frame width
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Pack widgets
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Bind mouse wheel scrolling
        self.scrollable_frame.bind("<Enter>", self._bind_mousewheel)
        self.scrollable_frame.bind("<Leave>", self._unbind_mousewheel)

    def _on_canvas_configure(self, event):
        """Adjust the inner frame width when canvas is resized."""
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def _bind_mousewheel(self, event):
        """Bind mouse wheel when cursor enters the frame."""
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        """Unbind mouse wheel when cursor leaves the frame."""
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        """Scroll the canvas with mouse wheel."""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class IoBTConfigGUI:
    """Main GUI application for IoBT configuration generation."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("IoBT-Viz Configuration Generator")
        self.root.geometry("720x600")
        self.root.minsize(600, 400)
        self.root.resizable(True, True)

        self.generator = IoBTConfigGenerator()

        # Find default output path
        self.default_output_path = self._find_default_output_path()

        # Create scrollable container
        self.scroll_container = ScrollableFrame(root)
        self.scroll_container.pack(fill=tk.BOTH, expand=True)

        # Main frame inside scrollable area
        self.main_frame = ttk.Frame(self.scroll_container.scrollable_frame, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self._create_widgets()
        self._update_dag_preview()

    def _find_default_output_path(self) -> str:
        """Find the default output path for iobt-config.lua."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Navigate from tools/ to maps/iobt-sim/
        maps_dir = os.path.join(script_dir, "..", "maps", "iobt-sim")
        default_path = os.path.join(maps_dir, "iobt-config.lua")
        return os.path.abspath(default_path)

    def _create_widgets(self):
        """Create all GUI widgets."""
        row = 0

        # Title
        title_label = ttk.Label(
            self.main_frame,
            text="IoBT-Viz Configuration Generator",
            font=("TkDefaultFont", 14, "bold")
        )
        title_label.grid(row=row, column=0, columnspan=3, pady=(0, 15))
        row += 1

        # === Node Configuration Section ===
        node_frame = ttk.LabelFrame(self.main_frame, text="Node Configuration", padding="10")
        node_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=5)
        row += 1

        # Total Nodes
        ttk.Label(node_frame, text="Total Nodes:").grid(row=0, column=0, sticky="w", pady=2)
        self.total_nodes_var = tk.IntVar(value=50)
        self.total_nodes_scale = ttk.Scale(
            node_frame, from_=10, to=500, variable=self.total_nodes_var,
            orient="horizontal", length=200, command=self._on_value_change
        )
        self.total_nodes_scale.grid(row=0, column=1, padx=5)
        self.total_nodes_label = ttk.Label(node_frame, text="50")
        self.total_nodes_label.grid(row=0, column=2, sticky="w")

        # Infantry %
        ttk.Label(node_frame, text="Infantry %:").grid(row=1, column=0, sticky="w", pady=2)
        self.infantry_pct_var = tk.IntVar(value=70)
        self.infantry_pct_scale = ttk.Scale(
            node_frame, from_=0, to=100, variable=self.infantry_pct_var,
            orient="horizontal", length=200, command=self._on_value_change
        )
        self.infantry_pct_scale.grid(row=1, column=1, padx=5)
        self.infantry_pct_label = ttk.Label(node_frame, text="70%")
        self.infantry_pct_label.grid(row=1, column=2, sticky="w")

        # Vehicle % (calculated, read-only)
        ttk.Label(node_frame, text="Vehicle %:").grid(row=2, column=0, sticky="w", pady=2)
        self.vehicle_pct_label = ttk.Label(node_frame, text="30%")
        self.vehicle_pct_label.grid(row=2, column=1, sticky="w", padx=5)

        # Compute Node %
        ttk.Label(node_frame, text="Compute Node %:").grid(row=3, column=0, sticky="w", pady=2)
        self.compute_pct_var = tk.IntVar(value=30)
        self.compute_pct_scale = ttk.Scale(
            node_frame, from_=0, to=100, variable=self.compute_pct_var,
            orient="horizontal", length=200, command=self._on_value_change
        )
        self.compute_pct_scale.grid(row=3, column=1, padx=5)
        self.compute_pct_label = ttk.Label(node_frame, text="30%")
        self.compute_pct_label.grid(row=3, column=2, sticky="w")

        # === Network Settings Section ===
        network_frame = ttk.LabelFrame(self.main_frame, text="Network Settings", padding="10")
        network_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=5)
        row += 1

        # Communication Range
        ttk.Label(network_frame, text="Communication Range:").grid(row=0, column=0, sticky="w", pady=2)
        self.comm_range_var = tk.IntVar(value=8)
        self.comm_range_spin = ttk.Spinbox(
            network_frame, from_=1, to=50, textvariable=self.comm_range_var,
            width=8, command=self._on_value_change
        )
        self.comm_range_spin.grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(network_frame, text="cells").grid(row=0, column=2, sticky="w")

        # Max Data Rate
        ttk.Label(network_frame, text="Max Data Rate:").grid(row=1, column=0, sticky="w", pady=2)
        self.max_rate_var = tk.IntVar(value=100)
        self.max_rate_spin = ttk.Spinbox(
            network_frame, from_=1, to=1000, textvariable=self.max_rate_var,
            width=8, command=self._on_value_change
        )
        self.max_rate_spin.grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(network_frame, text="Mbps").grid(row=1, column=2, sticky="w")

        # Min Data Rate
        ttk.Label(network_frame, text="Min Data Rate:").grid(row=2, column=0, sticky="w", pady=2)
        self.min_rate_var = tk.IntVar(value=10)
        self.min_rate_spin = ttk.Spinbox(
            network_frame, from_=1, to=1000, textvariable=self.min_rate_var,
            width=8, command=self._on_value_change
        )
        self.min_rate_spin.grid(row=2, column=1, sticky="w", padx=5)
        ttk.Label(network_frame, text="Mbps").grid(row=2, column=2, sticky="w")

        # === DAG Configuration Section ===
        dag_frame = ttk.LabelFrame(self.main_frame, text="DAG Configuration", padding="10")
        dag_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=5)
        row += 1

        # DAG Tree Depth
        ttk.Label(dag_frame, text="DAG Tree Depth:").grid(row=0, column=0, sticky="w", pady=2)
        self.dag_depth_var = tk.IntVar(value=3)
        self.dag_depth_spin = ttk.Spinbox(
            dag_frame, from_=1, to=6, textvariable=self.dag_depth_var,
            width=8, command=self._on_dag_change
        )
        self.dag_depth_spin.grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(dag_frame, text="levels").grid(row=0, column=2, sticky="w")

        # Branching Factor
        ttk.Label(dag_frame, text="Branching Factor:").grid(row=1, column=0, sticky="w", pady=2)
        self.branching_var = tk.IntVar(value=2)
        self.branching_spin = ttk.Spinbox(
            dag_frame, from_=1, to=5, textvariable=self.branching_var,
            width=8, command=self._on_dag_change
        )
        self.branching_spin.grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(dag_frame, text="children per node").grid(row=1, column=2, sticky="w")

        # Task Duration
        ttk.Label(dag_frame, text="Task Duration:").grid(row=2, column=0, sticky="w", pady=2)
        self.task_duration_var = tk.IntVar(value=75)
        self.task_duration_spin = ttk.Spinbox(
            dag_frame, from_=10, to=500, textvariable=self.task_duration_var,
            width=8, command=self._on_value_change
        )
        self.task_duration_spin.grid(row=2, column=1, sticky="w", padx=5)
        ttk.Label(dag_frame, text="ticks (25 = 1 sec)").grid(row=2, column=2, sticky="w")

        # Transfer Duration
        ttk.Label(dag_frame, text="Transfer Duration:").grid(row=3, column=0, sticky="w", pady=2)
        self.transfer_duration_var = tk.IntVar(value=50)
        self.transfer_duration_spin = ttk.Spinbox(
            dag_frame, from_=25, to=250, textvariable=self.transfer_duration_var,
            width=8, command=self._on_value_change
        )
        self.transfer_duration_spin.grid(row=3, column=1, sticky="w", padx=5)
        ttk.Label(dag_frame, text="ticks (cyan link time)").grid(row=3, column=2, sticky="w")

        # DAG Preview
        ttk.Label(dag_frame, text="Preview:").grid(row=4, column=0, sticky="nw", pady=5)
        self.dag_preview_text = tk.Text(dag_frame, height=6, width=35, font=("Courier", 9))
        self.dag_preview_text.grid(row=4, column=1, columnspan=2, sticky="w", pady=5)
        self.dag_preview_text.config(state="disabled")

        # === Simulation Settings Section ===
        sim_frame = ttk.LabelFrame(self.main_frame, text="Simulation Settings", padding="10")
        sim_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=5)
        row += 1

        # Duration
        ttk.Label(sim_frame, text="Duration:").grid(row=0, column=0, sticky="w", pady=2)
        self.duration_var = tk.IntVar(value=60)
        self.duration_spin = ttk.Spinbox(
            sim_frame, from_=10, to=600, textvariable=self.duration_var,
            width=8, command=self._on_value_change
        )
        self.duration_spin.grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(sim_frame, text="seconds").grid(row=0, column=2, sticky="w")

        # Movement Groups
        ttk.Label(sim_frame, text="Movement Groups:").grid(row=1, column=0, sticky="w", pady=2)
        self.num_squads_var = tk.IntVar(value=5)
        self.num_squads_spin = ttk.Spinbox(
            sim_frame, from_=1, to=20, textvariable=self.num_squads_var,
            width=8, command=self._on_value_change
        )
        self.num_squads_spin.grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(sim_frame, text="squads").grid(row=1, column=2, sticky="w")

        # === Output Path Section ===
        output_frame = ttk.Frame(self.main_frame)
        output_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10)
        row += 1

        ttk.Label(output_frame, text="Output Path:").grid(row=0, column=0, sticky="w")
        self.output_path_var = tk.StringVar(value=self.default_output_path)
        self.output_path_entry = ttk.Entry(
            output_frame, textvariable=self.output_path_var, width=55
        )
        self.output_path_entry.grid(row=0, column=1, padx=5)
        self.browse_button = ttk.Button(output_frame, text="Browse...", command=self._browse_output)
        self.browse_button.grid(row=0, column=2)

        # === Buttons Section ===
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=15)
        row += 1

        self.generate_button = ttk.Button(
            button_frame, text="Generate Config", command=self._generate_config
        )
        self.generate_button.pack(side="left", padx=10)

        self.preview_button = ttk.Button(
            button_frame, text="Preview Lua", command=self._preview_lua
        )
        self.preview_button.pack(side="left", padx=10)

        # === Status Bar ===
        self.status_var = tk.StringVar(value="Ready - Scroll with mouse wheel if needed")
        self.status_bar = ttk.Label(
            self.main_frame, textvariable=self.status_var, relief="sunken", anchor="w"
        )
        self.status_bar.grid(row=row, column=0, columnspan=3, sticky="ew")

    def _on_value_change(self, *args):
        """Handle value changes in sliders and spinboxes."""
        # Update labels
        total = int(self.total_nodes_var.get())
        infantry_pct = int(self.infantry_pct_var.get())
        compute_pct = int(self.compute_pct_var.get())

        self.total_nodes_label.config(text=str(total))
        self.infantry_pct_label.config(text=f"{infantry_pct}%")
        self.vehicle_pct_label.config(text=f"{100 - infantry_pct}%")
        self.compute_pct_label.config(text=f"{compute_pct}%")

    def _on_dag_change(self, *args):
        """Handle DAG parameter changes."""
        self._on_value_change()
        self._update_dag_preview()

    def _update_dag_preview(self):
        """Update the DAG tree preview."""
        self.generator.set_config(
            dag_depth=int(self.dag_depth_var.get()),
            branching_factor=int(self.branching_var.get())
        )
        preview = self.generator.generate_dag_preview()

        self.dag_preview_text.config(state="normal")
        self.dag_preview_text.delete(1.0, tk.END)
        self.dag_preview_text.insert(1.0, preview)
        self.dag_preview_text.config(state="disabled")

    def _browse_output(self):
        """Open file browser for output path."""
        initial_dir = os.path.dirname(self.output_path_var.get())
        filename = filedialog.asksaveasfilename(
            initialdir=initial_dir,
            initialfile="iobt-config.lua",
            defaultextension=".lua",
            filetypes=[("Lua files", "*.lua"), ("All files", "*.*")]
        )
        if filename:
            self.output_path_var.set(filename)

    def _get_current_config(self) -> dict:
        """Get current configuration from GUI widgets."""
        return {
            "total_nodes": int(self.total_nodes_var.get()),
            "infantry_pct": int(self.infantry_pct_var.get()),
            "compute_node_pct": int(self.compute_pct_var.get()),
            "comm_range": int(self.comm_range_var.get()),
            "max_data_rate": int(self.max_rate_var.get()),
            "min_data_rate": int(self.min_rate_var.get()),
            "dag_depth": int(self.dag_depth_var.get()),
            "branching_factor": int(self.branching_var.get()),
            "task_duration": int(self.task_duration_var.get()),
            "transfer_duration": int(self.transfer_duration_var.get()),
            "simulation_duration": int(self.duration_var.get()),
            "num_squads": int(self.num_squads_var.get()),
        }

    def _generate_config(self):
        """Generate and save the Lua configuration file."""
        try:
            config = self._get_current_config()
            self.generator.set_config(**config)

            lua_content = self.generator.generate_full_config()
            output_path = self.output_path_var.get()

            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(lua_content)

            self.status_var.set(f"Config saved to: {output_path}")
            messagebox.showinfo(
                "Success",
                f"Configuration generated successfully!\n\nSaved to:\n{output_path}\n\n"
                "Restart IoBT-Viz to load the new configuration."
            )
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            messagebox.showerror("Error", f"Failed to generate config:\n{str(e)}")

    def _preview_lua(self):
        """Show a preview of the generated Lua code."""
        config = self._get_current_config()
        self.generator.set_config(**config)
        lua_content = self.generator.generate_full_config()

        # Create preview window
        preview_window = tk.Toplevel(self.root)
        preview_window.title("Lua Configuration Preview")
        preview_window.geometry("800x600")

        # Text widget with scrollbar
        text_frame = ttk.Frame(preview_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        text_widget = scrolledtext.ScrolledText(
            text_frame, font=("Courier", 10), wrap=tk.NONE
        )
        text_widget.pack(fill=tk.BOTH, expand=True)
        text_widget.insert(1.0, lua_content)
        text_widget.config(state="disabled")

        # Close button
        close_button = ttk.Button(
            preview_window, text="Close",
            command=preview_window.destroy
        )
        close_button.pack(pady=5)


def main():
    """Run the GUI application."""
    root = tk.Tk()

    # Set style
    style = ttk.Style()
    if "clam" in style.theme_names():
        style.theme_use("clam")

    app = IoBTConfigGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
