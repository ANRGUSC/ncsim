"""
ncsim command-line interface.

Usage:
    ncsim --scenario PATH --output DIR [--seed N] [--scheduler ALGO]
"""

import argparse
import logging
import sys
from pathlib import Path

from ncsim.io.scenario_loader import load_scenario
from ncsim.io.trace_writer import TraceWriter, TraceEventAdapter
from ncsim.io.results_writer import write_results
from ncsim.models.dag import SingleDAGSource, MultiDAGSource
from ncsim.core.simulation import Simulation
from ncsim.scheduler.saga_adapter import create_scheduler


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )


def main(args: list = None) -> int:
    """Main entry point for ncsim CLI.

    Args:
        args: Command-line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        prog="ncsim",
        description="Headless Discrete Event Simulator for Networked Computing"
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="Path to scenario YAML file"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for trace and metrics"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed (overrides scenario config)"
    )
    parser.add_argument(
        "--scheduler",
        choices=["heft", "cpop", "round_robin"],
        default=None,
        help="Scheduling algorithm (overrides scenario config)"
    )
    parser.add_argument(
        "--routing",
        choices=["direct", "widest_path", "shortest_path"],
        default=None,
        help="Routing algorithm (overrides scenario config)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="ncsim 0.1.0"
    )

    parsed = parser.parse_args(args)
    setup_logging(parsed.verbose)
    logger = logging.getLogger(__name__)

    try:
        # Load scenario
        logger.info(f"Loading scenario: {parsed.scenario}")
        scenario = load_scenario(parsed.scenario)
        logger.info(f"Scenario '{scenario.name}' loaded: "
                   f"{len(scenario.network.nodes)} nodes, "
                   f"{len(scenario.network.links)} links, "
                   f"{len(scenario.dags)} DAG(s)")

        # Override config if specified
        seed = parsed.seed if parsed.seed is not None else scenario.config.seed
        scheduler_algo = parsed.scheduler if parsed.scheduler else scenario.config.scheduler
        routing_type = parsed.routing if parsed.routing else scenario.config.routing

        # Create routing model
        logger.info(f"Creating routing model: {routing_type}")
        if routing_type == "widest_path":
            from ncsim.models.routing import WidestPathRouting
            routing_model = WidestPathRouting()
        elif routing_type == "shortest_path":
            from ncsim.models.routing import ShortestPathRouting
            routing_model = ShortestPathRouting()
        else:
            from ncsim.models.routing import DirectLinkRouting
            routing_model = DirectLinkRouting()

        # Create scheduler (pass routing model for SAGA bandwidth awareness)
        logger.info(f"Creating scheduler: {scheduler_algo}")
        if routing_type in ("widest_path", "shortest_path"):
            scheduler = create_scheduler(scheduler_algo, routing=routing_model)
        else:
            scheduler = create_scheduler(scheduler_algo)

        # Create DAG source
        if len(scenario.dags) == 1:
            dag_source = SingleDAGSource(scenario.dags[0])
        else:
            dag_source = MultiDAGSource(scenario.dags)

        # Create simulation
        sim = Simulation(
            network=scenario.network,
            scheduler=scheduler,
            dag_source=dag_source,
            routing_model=routing_model,
            seed=seed
        )

        # Set up output directory
        output_dir = Path(parsed.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = output_dir / "trace.jsonl"
        metrics_path = output_dir / "metrics.json"

        # Set up trace writer
        trace_writer = TraceWriter(
            output_path=trace_path,
            scenario_name=Path(parsed.scenario).name,
            scenario_hash=scenario.file_hash or "",
            seed=seed
        )

        trace_adapter = TraceEventAdapter(trace_writer)

        # Open trace file and write header
        trace_writer.open()
        trace_writer.write_sim_start()

        # Connect trace writer to simulation
        sim.add_event_listener(trace_adapter.on_event)

        # Run simulation
        logger.info("Running simulation...")
        result = sim.run()

        # Write trace footer
        trace_writer.write_sim_end(
            status=result.status,
            makespan=result.makespan,
            total_events=trace_writer.event_count
        )
        trace_writer.close()

        logger.info(f"Trace written to: {trace_path}")

        # Calculate task/transfer counts
        total_tasks = sum(len(dag.tasks) for dag in scenario.dags)
        total_transfers = sum(len(dag.edges) for dag in scenario.dags)

        # Write metrics
        write_results(
            output_path=metrics_path,
            result=result,
            scenario_name=Path(parsed.scenario).name,
            seed=seed,
            total_tasks=total_tasks,
            total_transfers=total_transfers
        )
        logger.info(f"Metrics written to: {metrics_path}")

        # Print summary
        print(f"\n=== Simulation Complete ===")
        print(f"Scenario: {scenario.name}")
        print(f"Scheduler: {scheduler_algo}")
        print(f"Routing: {routing_type}")
        print(f"Seed: {seed}")
        print(f"Makespan: {result.makespan:.6f} seconds")
        print(f"Total events: {result.total_events}")
        print(f"Status: {result.status}")

        if result.status == "error":
            print(f"Error: {result.error_message}")
            return 1

        return 0

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Invalid scenario: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
