"""
Failure trace generators: disruption processes with distinct statistical structure.

All generators compile to the same artifact -- a time-ordered list of
DisruptionEvents -- so the simulator is indifferent to where a trace came
from, and traces with different correlation structure can be compared under
identical workloads and repair policies.

ncsim links are directed; a bidirectional radio link is modeled as a pair of
directed links. A wireless failure takes out the pair, so every generator
here emits events for both directions of a radio link together.

Generators:
- single_failure_trace (G1): one scheduled failure, the controlled-analysis
  case -- sweep which link and when.
- gilbert_elliott_trace (G2): per-link two-state Markov process with
  exponential up/down times (MTBF/MTTR). Memoryless, independent across
  radio links, no warning before a failure; burstiness comes from short MTTR.
"""

import random
from typing import Dict, FrozenSet, List, Optional, Tuple

from ncsim.models.disruptions import DisruptionEvent, DisruptionType
from ncsim.models.network import Network


def radio_pairs(network: Network) -> Dict[FrozenSet[str], List[str]]:
    """Group directed links into bidirectional radio pairs.

    Args:
        network: The network topology

    Returns:
        Mapping from the unordered node pair to the directed link IDs
        between those nodes (one entry for a one-way link, two for a pair).
    """
    pairs: Dict[FrozenSet[str], List[str]] = {}
    for link in network.links.values():
        pairs.setdefault(frozenset((link.from_node, link.to_node)), []).append(link.id)
    return pairs


def _pair_events(
    link_ids: List[str],
    time: float,
    disruption_type: DisruptionType,
    duration: Optional[float] = None,
    parameters: Optional[dict] = None,
) -> List[DisruptionEvent]:
    """Emit one event per directed link of a radio pair."""
    return [
        DisruptionEvent(
            time=time,
            target_type="link",
            target_id=link_id,
            disruption_type=disruption_type,
            duration=duration,
            parameters=dict(parameters or {}),
        )
        for link_id in sorted(link_ids)
    ]


def single_failure_trace(
    network: Network,
    between: Tuple[str, str],
    time: float,
    duration: Optional[float] = None,
    bandwidth_factor: Optional[float] = None,
) -> List[DisruptionEvent]:
    """G1: one scheduled disruption of the radio link between two nodes.

    The controlled-analysis generator: sweeping `between` over links (by
    scheduled traffic) and `time` over the schedule isolates how failure
    location and timing interact with each repair scope.

    Args:
        network: The network topology
        between: The two endpoints of the radio link to disrupt
        time: When the disruption occurs
        duration: If set, the link recovers after this many seconds;
            None means a permanent failure
        bandwidth_factor: If set, degrade to this fraction of bandwidth
            instead of failing outright

    Returns:
        DisruptionEvents for both directions of the radio link

    Raises:
        ValueError: If no link exists between the given nodes
    """
    pair = frozenset(between)
    link_ids = radio_pairs(network).get(pair)
    if not link_ids:
        raise ValueError(f"No link between {between[0]} and {between[1]}")
    if bandwidth_factor is not None:
        return _pair_events(
            link_ids,
            time,
            DisruptionType.LINK_DEGRADE,
            duration=duration,
            parameters={"bandwidth_factor": bandwidth_factor},
        )
    return _pair_events(link_ids, time, DisruptionType.LINK_DOWN, duration=duration)


def gilbert_elliott_trace(
    network: Network,
    mtbf: float,
    mttr: float,
    horizon: float,
    seed: int = 42,
    pairs: Optional[List[Tuple[str, str]]] = None,
) -> List[DisruptionEvent]:
    """G2: memoryless per-link failures with exponential up and down times.

    Each radio pair alternates between an up state with exponential holding
    time (mean `mtbf`) and a down state with exponential holding time (mean
    `mttr`), independently of every other pair -- the classic two-state
    Markov (Gilbert-Elliott) link model. Failures arrive without warning and
    without spatial correlation, which is exactly what distinguishes this
    process from mobility-driven and jamming-driven traces.

    Args:
        network: The network topology
        mtbf: Mean time between failures (mean up-state holding time)
        mttr: Mean time to recovery (mean down-state holding time)
        horizon: Generate events in [0, horizon)
        seed: RNG seed; the same seed yields the identical trace
        pairs: Restrict to these radio pairs (by endpoints); default all

    Returns:
        Time-ordered DisruptionEvents, both directions per failure, each
        LINK_DOWN carrying its outage duration so recovery is automatic

    Raises:
        ValueError: If mtbf, mttr, or horizon is not positive
    """
    if mtbf <= 0 or mttr <= 0 or horizon <= 0:
        raise ValueError("mtbf, mttr, and horizon must be positive")

    all_pairs = radio_pairs(network)
    if pairs is not None:
        selected = {}
        for a, b in pairs:
            key = frozenset((a, b))
            if key not in all_pairs:
                raise ValueError(f"No link between {a} and {b}")
            selected[key] = all_pairs[key]
        all_pairs = selected

    events: List[DisruptionEvent] = []
    # One independent stream per pair, seeded from (seed, sorted endpoints),
    # so adding or removing a pair never perturbs the others' traces. String
    # seeds hash via SHA-512 inside random.Random, stable across processes.
    for key in sorted(all_pairs, key=sorted):
        link_ids = all_pairs[key]
        rng = random.Random(f"{seed}:{':'.join(sorted(key))}")
        t = rng.expovariate(1.0 / mtbf)
        while t < horizon:
            outage = rng.expovariate(1.0 / mttr)
            events.extend(
                _pair_events(link_ids, t, DisruptionType.LINK_DOWN, duration=outage)
            )
            t += outage + rng.expovariate(1.0 / mtbf)

    events.sort(key=lambda e: (e.time, e.target_id))
    return events
