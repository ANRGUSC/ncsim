#!/usr/bin/env python3
"""
Interactive script to explore ncsim simulation step by step.

Usage:
    cd ncsim
    python explore_sim.py
    python explore_sim.py scenarios/bandwidth_contention.yaml
"""

import sys
from ncsim.io.scenario_loader import load_scenario
from ncsim.scheduler.saga_adapter import create_scheduler
from ncsim.scheduler.base import NetworkSnapshot
from ncsim.core.event_queue import EventQueue, EventType
from ncsim.core.execution_engine import ExecutionEngine
from ncsim.models.dag import SingleDAGSource


def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print('='*60)


def print_event(event, prefix=""):
    """Pretty print an event."""
    etype = event.event_type.name
    time = f"{event.sim_time:.6f}"

    details = []
    if event.dag_id:
        details.append(f"dag={event.dag_id}")
    if event.task_id:
        details.append(f"task={event.task_id}")
    if event.node_id:
        details.append(f"node={event.node_id}")
    if event.from_task and event.to_task:
        details.append(f"transfer={event.from_task}->{event.to_task}")
    if event.link_id:
        details.append(f"link={event.link_id}")
    if event.data:
        for k, v in event.data.items():
            if k != "dag":  # Skip the full dag object
                details.append(f"{k}={v}")

    detail_str = ", ".join(details) if details else ""
    print(f"{prefix}[{time}] {etype:20} {detail_str}")


def print_node_states(engine):
    """Print current state of all nodes."""
    print("\n  Node States:")
    for node_id, state in engine.node_states.items():
        if state.current_task:
            status = f"BUSY ({state.current_task.task_id})"
        else:
            status = "IDLE"
        queue_info = f", queue={len(state.queue)}" if len(state.queue) > 0 else ""
        print(f"    {node_id}: {status}{queue_info}")


def print_link_states(engine):
    """Print current state of all links."""
    active_links = [(lid, ls) for lid, ls in engine.link_states.items() if ls.num_transfers > 0]
    if active_links:
        print("\n  Active Transfers:")
        for link_id, state in active_links:
            for t in state.active_transfers:
                print(f"    {link_id}: {t.from_task}->{t.to_task} ({t.data_remaining:.1f} MB remaining)")


def main():
    # Load scenario
    scenario_path = sys.argv[1] if len(sys.argv) > 1 else "scenarios/demo_simple.yaml"

    print_header(f"Loading Scenario: {scenario_path}")
    scenario = load_scenario(scenario_path)

    print(f"\nNetwork: {len(scenario.network.nodes)} nodes, {len(scenario.network.links)} links")
    for node_id, node in scenario.network.nodes.items():
        print(f"  {node_id}: compute_capacity={node.compute_capacity}")
    for link_id, link in scenario.network.links.items():
        print(f"  {link_id}: {link.from_node}->{link.to_node} (bw={link.bandwidth}, lat={link.latency})")

    dag = scenario.dags[0]
    print(f"\nDAG: {dag.id} ({len(dag.tasks)} tasks, {len(dag.edges)} edges)")
    for task_id, task in dag.tasks.items():
        preds = dag.get_predecessors(task_id)
        pred_str = f" <- {preds}" if preds else " (root)"
        print(f"  {task_id}: cost={task.compute_cost}{pred_str}")

    # Create scheduler and get plan
    print_header("Scheduling with HEFT")
    scheduler = create_scheduler("heft")
    snapshot = NetworkSnapshot.from_network(scenario.network)
    plan = scheduler.on_dag_inject(dag, snapshot)

    print("\nTask Assignments:")
    for task_id in dag.topological_order():
        node_id = plan.assignments[task_id]
        task = dag.get_task(task_id)
        node = scenario.network.get_node(node_id)
        runtime = task.compute_cost / node.compute_capacity
        print(f"  {task_id} -> {node_id} (will take {runtime:.3f}s)")

    # Set up simulation
    print_header("Simulation Events")
    print("\nPress Enter to step through events, 'q' to quit, 'r' to run all\n")

    event_queue = EventQueue()
    engine = ExecutionEngine(
        network=scenario.network,
        scheduler=scheduler,
        event_queue=event_queue
    )

    # Inject DAG
    event_queue.schedule(
        sim_time=0.0,
        event_type=EventType.DAG_INJECT,
        dag_id=dag.id,
        data={"dag": dag}
    )

    run_all = False
    event_count = 0

    while not event_queue.is_empty():
        event = event_queue.pop()
        if event is None:
            break

        event_count += 1
        print(f"\n--- Event {event_count} ---")
        print_event(event, prefix="  ")

        # Process event
        engine.handle_event(event)

        # Show state after processing
        print_node_states(engine)
        print_link_states(engine)

        # Show pending events
        pending = list(event_queue)
        if pending:
            print(f"\n  Pending events ({len(pending)}):")
            for e in pending[:5]:  # Show first 5
                print_event(e, prefix="    ")
            if len(pending) > 5:
                print(f"    ... and {len(pending)-5} more")

        if not run_all:
            try:
                user_input = input("\n[Enter=next, r=run all, q=quit] > ").strip().lower()
                if user_input == 'q':
                    break
                elif user_input == 'r':
                    run_all = True
            except EOFError:
                break

    # Final summary
    print_header("Simulation Complete")
    makespan = engine.get_makespan()
    print(f"\nMakespan: {makespan:.6f} seconds")
    print(f"Total events: {event_count}")

    print("\nNode Utilization:")
    for node_id in scenario.network.nodes:
        util = engine.get_node_utilization(node_id)
        bar = "#" * int(util * 20) + "-" * (20 - int(util * 20))
        print(f"  {node_id}: [{bar}] {util*100:.1f}%")

    print("\nLink Utilization:")
    for link_id in scenario.network.links:
        util = engine.get_link_utilization(link_id)
        bar = "#" * int(util * 20) + "-" * (20 - int(util * 20))
        print(f"  {link_id}: [{bar}] {util*100:.1f}%")


if __name__ == "__main__":
    main()
