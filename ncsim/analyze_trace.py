#!/usr/bin/env python3
"""
Analyze a trace file from ncsim.

Usage:
    python analyze_trace.py ../test_output/trace.jsonl
    python analyze_trace.py trace.jsonl --timeline
    python analyze_trace.py trace.jsonl --gantt
"""

import json
import sys
from collections import defaultdict
from pathlib import Path


def load_trace(path):
    """Load trace events from JSONL file."""
    events = []
    with open(path) as f:
        for line in f:
            events.append(json.loads(line))
    return events


def print_summary(events):
    """Print summary statistics."""
    print("\n=== Trace Summary ===\n")

    # Find sim_start and sim_end
    sim_start = next((e for e in events if e["type"] == "sim_start"), None)
    sim_end = next((e for e in events if e["type"] == "sim_end"), None)

    if sim_start:
        print(f"Scenario: {sim_start.get('scenario', 'unknown')}")
        print(f"Seed: {sim_start.get('seed', 'unknown')}")

    if sim_end:
        print(f"Status: {sim_end.get('status', 'unknown')}")
        print(f"Makespan: {sim_end.get('makespan', 0):.6f} seconds")

    print(f"Total events: {len(events)}")

    # Count event types
    type_counts = defaultdict(int)
    for e in events:
        type_counts[e["type"]] += 1

    print("\nEvent counts:")
    for etype, count in sorted(type_counts.items()):
        print(f"  {etype}: {count}")


def print_timeline(events):
    """Print chronological timeline of events."""
    print("\n=== Event Timeline ===\n")

    for e in events:
        time = e.get("sim_time", 0)
        etype = e["type"]

        # Format event details
        if etype == "sim_start":
            detail = f"scenario={e.get('scenario')}"
        elif etype == "sim_end":
            detail = f"makespan={e.get('makespan')}"
        elif etype == "dag_inject":
            detail = f"dag={e.get('dag_id')}, tasks={e.get('task_ids')}"
        elif etype in ("task_scheduled", "task_start"):
            detail = f"{e.get('task_id')} on {e.get('node_id')}"
        elif etype == "task_complete":
            detail = f"{e.get('task_id')} on {e.get('node_id')} (duration={e.get('duration')})"
        elif etype == "transfer_start":
            detail = f"{e.get('from_task')}->{e.get('to_task')} via {e.get('link_id')} ({e.get('data_size')} MB)"
        elif etype == "transfer_complete":
            detail = f"{e.get('from_task')}->{e.get('to_task')} (duration={e.get('duration')})"
        else:
            detail = ""

        print(f"[{time:8.4f}] {etype:20} {detail}")


def print_gantt(events):
    """Print ASCII Gantt chart of task execution and transfers."""
    print("\n=== Execution Gantt Chart ===\n")

    # Collect task timings
    tasks = {}  # task_id -> {node, start, end}
    transfers = []  # [{from, to, link, start, end}]

    for e in events:
        if e["type"] == "task_start":
            task_id = e["task_id"]
            tasks[task_id] = {"node": e["node_id"], "start": e["sim_time"]}
        elif e["type"] == "task_complete":
            task_id = e["task_id"]
            if task_id in tasks:
                tasks[task_id]["end"] = e["sim_time"]
        elif e["type"] == "transfer_start":
            transfers.append({
                "from": e["from_task"],
                "to": e["to_task"],
                "link": e.get("link_id", "?"),
                "start": e["sim_time"],
                "data_size": e.get("data_size", 0)
            })
        elif e["type"] == "transfer_complete":
            # Find matching transfer
            for t in transfers:
                if t["from"] == e["from_task"] and t["to"] == e["to_task"] and "end" not in t:
                    t["end"] = e["sim_time"]
                    break

    if not tasks:
        print("No tasks found in trace")
        return

    # Find time range (include transfers)
    max_time = max(t.get("end", 0) for t in tasks.values())
    for t in transfers:
        if "end" in t:
            max_time = max(max_time, t["end"])
    if max_time == 0:
        max_time = 1

    # Chart settings
    width = 60
    scale = width / max_time

    # Print header
    print(f"Time: 0{' ' * (width-4)}{max_time:.2f}s")
    print(f"       |{'=' * width}|")

    # Group tasks by node
    nodes = defaultdict(list)
    for task_id, task in tasks.items():
        nodes[task["node"]].append((task_id, task))

    # Print each node's tasks
    for node_id in sorted(nodes.keys()):
        for task_id, task in sorted(nodes[node_id], key=lambda x: x[1].get("start", 0)):
            start = task.get("start", 0)
            end = task.get("end", start)

            start_col = int(start * scale)
            end_col = int(end * scale)
            duration = end - start

            bar = " " * start_col + "#" * max(1, end_col - start_col)
            bar = bar[:width]
            bar = bar + " " * (width - len(bar))

            print(f"{node_id:6} |{bar}| {task_id} ({duration:.3f}s)")

    # Print separator before transfers
    if transfers:
        print(f"       |{'-' * width}|")

        # Group transfers by link
        links = defaultdict(list)
        for t in transfers:
            if "end" in t:
                links[t["link"]].append(t)

        for link_id in sorted(links.keys()):
            for t in sorted(links[link_id], key=lambda x: x["start"]):
                start = t["start"]
                end = t["end"]

                start_col = int(start * scale)
                end_col = int(end * scale)
                duration = end - start

                bar = " " * start_col + "~" * max(1, end_col - start_col)
                bar = bar[:width]
                bar = bar + " " * (width - len(bar))

                label = f"{t['from']}->{t['to']}"
                print(f"{link_id:6} |{bar}| {label} ({duration:.3f}s)")

    print(f"       |{'=' * width}|")
    print("\nLegend: # = task execution, ~ = data transfer")


def print_task_details(events):
    """Print detailed information about each task."""
    print("\n=== Task Details ===\n")

    tasks = defaultdict(dict)

    for e in events:
        if e["type"] == "task_scheduled":
            tasks[e["task_id"]]["node"] = e["node_id"]
            tasks[e["task_id"]]["scheduled_at"] = e["sim_time"]
        elif e["type"] == "task_start":
            tasks[e["task_id"]]["started_at"] = e["sim_time"]
        elif e["type"] == "task_complete":
            tasks[e["task_id"]]["completed_at"] = e["sim_time"]
            tasks[e["task_id"]]["duration"] = e.get("duration")

    for task_id in sorted(tasks.keys()):
        t = tasks[task_id]
        print(f"{task_id}:")
        print(f"  Node: {t.get('node', 'unknown')}")
        print(f"  Scheduled: {t.get('scheduled_at', 'N/A')}")
        print(f"  Started: {t.get('started_at', 'N/A')}")
        print(f"  Completed: {t.get('completed_at', 'N/A')}")
        if t.get('duration'):
            print(f"  Duration: {t['duration']:.6f}s")
        # Calculate wait time
        if t.get('scheduled_at') is not None and t.get('started_at') is not None:
            wait = t['started_at'] - t['scheduled_at']
            if wait > 0:
                print(f"  Wait time: {wait:.6f}s")
        print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_trace.py <trace.jsonl> [--timeline] [--gantt] [--tasks]")
        print("\nOptions:")
        print("  --timeline  Show chronological event timeline")
        print("  --gantt     Show ASCII Gantt chart")
        print("  --tasks     Show per-task details")
        print("  (default)   Show summary + gantt")
        sys.exit(1)

    trace_path = sys.argv[1]
    options = sys.argv[2:]

    if not Path(trace_path).exists():
        print(f"Error: File not found: {trace_path}")
        sys.exit(1)

    events = load_trace(trace_path)

    if not options:
        # Default: summary + gantt
        print_summary(events)
        print_gantt(events)
    else:
        if "--timeline" in options:
            print_timeline(events)
        if "--gantt" in options:
            print_gantt(events)
        if "--tasks" in options:
            print_task_details(events)
        if "--summary" in options or (not any(x in options for x in ["--timeline", "--gantt", "--tasks"])):
            print_summary(events)


if __name__ == "__main__":
    main()
