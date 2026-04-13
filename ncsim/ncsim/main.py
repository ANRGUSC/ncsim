"""
ncsim command-line interface.

Usage:
    ncsim --scenario PATH --output DIR [--seed N] [--scheduler ALGO]
"""

import argparse
import logging
import shutil
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


def _setup_wifi_model(scenario, parsed, seed, logger):
    """Set up 802.11 WiFi link model (csma_clique or csma_bianchi).

    Builds RFConfig, conflict graph, computes PHY rates, overwrites
    link bandwidths, and creates the appropriate interference model.

    Returns:
        (interference_model, extra_metrics_dict)
    """
    from ncsim.models.wifi import (
        RFConfig, build_conflict_graph, compute_link_phy_rates,
        generate_shadow_fading_map, carrier_sensing_range,
    )
    from ncsim.models.interference import create_interference_model

    interference_type = parsed.interference if parsed.interference else scenario.config.interference

    # Build RFConfig from YAML rf: section + CLI overrides
    rf_yaml = scenario.config.rf_config or {}
    rf = RFConfig(
        tx_power_dBm=parsed.tx_power if parsed.tx_power is not None else rf_yaml.get("tx_power_dBm", 20.0),
        freq_ghz=parsed.freq if parsed.freq is not None else rf_yaml.get("freq_ghz", 5.0),
        path_loss_exponent=parsed.path_loss_exponent if parsed.path_loss_exponent is not None else rf_yaml.get("path_loss_exponent", 3.0),
        noise_floor_dBm=rf_yaml.get("noise_floor_dBm", -95.0),
        cca_threshold_dBm=rf_yaml.get("cca_threshold_dBm", -82.0),
        channel_width_mhz=int(rf_yaml.get("channel_width_mhz", 20)),
        wifi_standard=parsed.wifi_standard if parsed.wifi_standard is not None else rf_yaml.get("wifi_standard", "ax"),
        shadow_fading_sigma=float(rf_yaml.get("shadow_fading_sigma", 0.0)),
        rts_cts=parsed.rts_cts if parsed.rts_cts else rf_yaml.get("rts_cts", False),
    )

    logger.info(f"RF config: tx_power={rf.tx_power_dBm}dBm, freq={rf.freq_ghz}GHz, "
                f"n={rf.path_loss_exponent}, standard={rf.wifi_standard}, "
                f"BW={rf.channel_width_mhz}MHz, rts_cts={rf.rts_cts}")

    cs_range = carrier_sensing_range(rf)
    logger.info(f"Carrier sensing range: {cs_range:.1f}m")

    # Shadow fading map (deterministic from seed)
    shadow_map = generate_shadow_fading_map(
        scenario.network, rf.shadow_fading_sigma, seed
    )
    if rf.shadow_fading_sigma > 0:
        logger.info(f"Shadow fading: sigma={rf.shadow_fading_sigma} dB (seed={seed})")

    # Compute per-link PHY rates
    phy_rates = compute_link_phy_rates(scenario.network, rf, shadow_map)

    # Build conflict graph
    conflict_graph = build_conflict_graph(scenario.network, rf, shadow_map)

    # Log conflict graph summary
    total_conflicts = sum(len(v) for v in conflict_graph.conflicts.values()) // 2
    logger.info(f"Conflict graph: {len(conflict_graph.conflicts)} links, "
                f"{total_conflicts} conflict pairs")

    # Overwrite link bandwidths with PHY-derived rates
    for link_id, link in scenario.network.links.items():
        if link_id in scenario.explicit_bandwidth_links:
            logger.debug(f"Link {link_id}: keeping explicit bandwidth {link.bandwidth:.2f} MB/s")
            continue

        rate = phy_rates[link_id]
        if rate <= 0:
            logger.warning(f"Link {link_id}: out of range (PHY rate = 0), using minimum 0.001 MB/s")
            rate = 0.001

        if interference_type == "csma_clique":
            clique_size = conflict_graph.max_clique_sizes.get(link_id, 1)
            link.bandwidth = rate / clique_size
            logger.debug(f"Link {link_id}: PHY={rate:.2f} MB/s, "
                         f"clique={clique_size}, effective={link.bandwidth:.2f} MB/s")
        else:  # csma_bianchi
            link.bandwidth = rate
            logger.debug(f"Link {link_id}: base PHY={link.bandwidth:.2f} MB/s")

    # Create interference model
    if interference_type == "csma_clique":
        interference_model = create_interference_model(
            "csma_clique",
            conflict_graph=conflict_graph,
        )
    else:
        interference_model = create_interference_model(
            "csma_bianchi",
            conflict_graph=conflict_graph,
            rf_config=rf,
            network=scenario.network,
            shadow_fading_map=shadow_map,
        )

    # Extra metrics for results output
    extra_metrics = {
        "rf_config": {
            "tx_power_dBm": rf.tx_power_dBm,
            "freq_ghz": rf.freq_ghz,
            "path_loss_exponent": rf.path_loss_exponent,
            "noise_floor_dBm": rf.noise_floor_dBm,
            "cca_threshold_dBm": rf.cca_threshold_dBm,
            "channel_width_mhz": rf.channel_width_mhz,
            "wifi_standard": rf.wifi_standard,
            "shadow_fading_sigma": rf.shadow_fading_sigma,
            "rts_cts": rf.rts_cts,
        },
        "carrier_sensing_range_m": round(cs_range, 2),
        "link_phy_rates_MBps": {k: round(v, 4) for k, v in phy_rates.items()},
        "max_clique_sizes": conflict_graph.max_clique_sizes,
    }

    return interference_model, extra_metrics


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
        choices=["heft", "cpop", "round_robin", "manual"],
        default=None,
        help="Scheduling algorithm (overrides scenario config)"
    )
    parser.add_argument(
        "--routing",
        choices=["direct", "widest_path", "shortest_path", "interference_aware", "interference_aware_dynamic", "interference_aware_dynamic_deferral"],
        default=None,
        help="Routing algorithm (overrides scenario config)"
    )
    parser.add_argument(
        "--routing-hop-cutoff",
        type=int,
        default=None,
        help="Max hops for interference_aware routing path enumeration (default: 4)"
    )
    parser.add_argument(
        "--greedy-order",
        choices=["start", "criticality", "bytes", "overlap"],
        default=None,
        help="Greedy flow ordering for interference_aware routing: "
             "start=GS, criticality=GC, bytes=GB, overlap=GO (default: start)"
    )
    parser.add_argument(
        "--deferral-threshold",
        type=float,
        default=None,
        help="Deferral threshold for interference_aware_dynamic_deferral routing: "
             "defer if effective BW < threshold * no-contention BW (default: 0.3)"
    )
    parser.add_argument(
        "--max-deferrals",
        type=int,
        default=None,
        help="Max times a transfer can be deferred before forced start (default: 3)"
    )
    parser.add_argument(
        "--interference",
        choices=["none", "proximity", "csma_clique", "csma_bianchi"],
        default=None,
        help="Inter-link interference model (overrides scenario config)"
    )
    parser.add_argument(
        "--interference-radius",
        type=float,
        default=None,
        help="Radius for proximity interference model (overrides scenario config)"
    )
    # WiFi RF parameter overrides
    parser.add_argument(
        "--tx-power",
        type=float,
        default=None,
        help="WiFi transmit power in dBm (default: 20)"
    )
    parser.add_argument(
        "--freq",
        type=float,
        default=None,
        help="WiFi carrier frequency in GHz (default: 5.0)"
    )
    parser.add_argument(
        "--path-loss-exponent",
        type=float,
        default=None,
        help="Path loss exponent (default: 3.0)"
    )
    parser.add_argument(
        "--wifi-standard",
        choices=["n", "ac", "ax"],
        default=None,
        help="WiFi standard for MCS tables (default: ax)"
    )
    parser.add_argument(
        "--rts-cts",
        action="store_true",
        default=False,
        help="Enable RTS/CTS (extends conflict graph to protect receivers)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--version",
        action="version",
        version="ncsim 0.2.0"
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

        # Create interference model FIRST (needed by interference_aware routing)
        interference_type = parsed.interference if parsed.interference else scenario.config.interference
        interference_model = None
        extra_metrics = None

        if interference_type in ("csma_clique", "csma_bianchi"):
            # 802.11 WiFi model
            interference_model, extra_metrics = _setup_wifi_model(
                scenario, parsed, seed, logger
            )
        elif interference_type == "proximity":
            from ncsim.models.interference import create_interference_model
            interference_radius = parsed.interference_radius if parsed.interference_radius is not None else scenario.config.interference_radius
            logger.info(f"Creating interference model: proximity (radius={interference_radius})")
            interference_model = create_interference_model(
                "proximity",
                interference_radius=interference_radius
            )
        else:
            logger.info("Interference model: none")

        # Create routing model
        logger.info(f"Creating routing model: {routing_type}")
        if routing_type == "interference_aware":
            from ncsim.models.routing import InterferenceAwareRouting
            from ncsim.models.interference import NoInterference
            hop_cutoff = parsed.routing_hop_cutoff if parsed.routing_hop_cutoff is not None else (
                scenario.config.routing_hop_cutoff if scenario.config.routing_hop_cutoff is not None else 4
            )
            greedy_order = parsed.greedy_order if parsed.greedy_order is not None else (
                scenario.config.greedy_order if scenario.config.greedy_order is not None else "start"
            )
            # Use existing interference model, or NoInterference as fallback
            im = interference_model if interference_model is not None else NoInterference()
            routing_model = InterferenceAwareRouting(
                im, hop_cutoff=hop_cutoff, greedy_order=greedy_order
            )
            logger.info(f"  hop_cutoff={hop_cutoff}, greedy_order={greedy_order}")
        elif routing_type == "interference_aware_dynamic":
            from ncsim.models.routing import DynamicInterferenceAwareRouting
            from ncsim.models.interference import NoInterference
            hop_cutoff = parsed.routing_hop_cutoff if parsed.routing_hop_cutoff is not None else (
                scenario.config.routing_hop_cutoff if scenario.config.routing_hop_cutoff is not None else 4
            )
            im = interference_model if interference_model is not None else NoInterference()
            routing_model = DynamicInterferenceAwareRouting(im, hop_cutoff=hop_cutoff)
            logger.info(f"  hop_cutoff={hop_cutoff}")
        elif routing_type == "interference_aware_dynamic_deferral":
            from ncsim.models.routing import DeferralDynamicRouting
            from ncsim.models.interference import NoInterference
            hop_cutoff = parsed.routing_hop_cutoff if parsed.routing_hop_cutoff is not None else (
                scenario.config.routing_hop_cutoff if scenario.config.routing_hop_cutoff is not None else 4
            )
            deferral_threshold = parsed.deferral_threshold if parsed.deferral_threshold is not None else 0.3
            max_deferrals = parsed.max_deferrals if parsed.max_deferrals is not None else 3
            im = interference_model if interference_model is not None else NoInterference()
            routing_model = DeferralDynamicRouting(
                im, hop_cutoff=hop_cutoff,
                deferral_threshold=deferral_threshold,
                max_deferrals=max_deferrals,
            )
            logger.info(f"  hop_cutoff={hop_cutoff}, deferral_threshold={deferral_threshold}, max_deferrals={max_deferrals}")
        elif routing_type == "widest_path":
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
        if routing_type in ("widest_path", "shortest_path", "interference_aware", "interference_aware_dynamic", "interference_aware_dynamic_deferral"):
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
            interference_model=interference_model,
            seed=seed
        )

        # Set up output directory
        output_dir = Path(parsed.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = output_dir / "trace.jsonl"
        metrics_path = output_dir / "metrics.json"

        # Copy scenario YAML to output dir for self-contained run folders
        scenario_src = Path(parsed.scenario)
        shutil.copy2(scenario_src, output_dir / "scenario.yaml")

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
            total_transfers=total_transfers,
            extra_metrics=extra_metrics
        )
        logger.info(f"Metrics written to: {metrics_path}")

        # Print summary
        print(f"\n=== Simulation Complete ===")
        print(f"Scenario: {scenario.name}")
        print(f"Scheduler: {scheduler_algo}")
        print(f"Routing: {routing_type}")
        print(f"Interference: {interference_type}")
        if interference_type in ("csma_clique", "csma_bianchi") and extra_metrics:
            rf = extra_metrics["rf_config"]
            print(f"  WiFi: {rf['wifi_standard']} @ {rf['freq_ghz']}GHz, "
                  f"TX={rf['tx_power_dBm']}dBm, n={rf['path_loss_exponent']}")
            print(f"  CS range: {extra_metrics['carrier_sensing_range_m']}m, "
                  f"RTS/CTS: {rf['rts_cts']}")
        elif interference_type == "proximity":
            interference_radius = parsed.interference_radius if parsed.interference_radius is not None else scenario.config.interference_radius
            print(f"  radius={interference_radius}")
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
