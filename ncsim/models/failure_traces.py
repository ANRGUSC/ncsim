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
- mobility_trace (G3): link state follows inter-node distance along node
  trajectories. Temporally correlated and *trending*: a link degrades before
  it disconnects, so a failure announces itself -- the property that should
  favor small repair scopes.
- jamming_trace (G4): a jammer takes down every radio pair with an endpoint
  in range for the duration of its activity. Spatially correlated and abrupt:
  several links fail at the same instant with no warning, and a targeted
  jammer converts the adversarial-instance methodology into a failure model.
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Tuple

from ncsim.models.disruptions import DisruptionEvent, DisruptionType
from ncsim.models.mobility import Waypoints, static_trajectory
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


def _quantized_factor(distance: float, r_full: float, r_max: float, levels: int) -> float:
    """Map an inter-node distance to a quantized bandwidth factor.

    Full bandwidth within r_full, no link beyond r_max, and a linear ramp
    quantized to `levels` steps in between -- the degradation staircase a
    receding node walks down before the link disconnects. Quantization keeps
    the trace to state *changes* instead of an event per sample.
    """
    if distance <= r_full:
        return 1.0
    if distance >= r_max:
        return 0.0
    raw = (r_max - distance) / (r_max - r_full)
    step = max(1, min(levels - 1, math.ceil(raw * levels)))
    return step / levels


def mobility_trace(
    network: Network,
    trajectories: Dict[str, Waypoints],
    horizon: float,
    dt: float = 0.1,
    r_full: float = 10.0,
    r_max: float = 20.0,
    levels: int = 4,
) -> List[DisruptionEvent]:
    """G3: link state follows inter-node distance along node trajectories.

    Nodes without a trajectory sit at their scenario position. At each sample
    instant every radio pair's distance maps to a quantized bandwidth factor
    (full within r_full, dead beyond r_max, a `levels`-step ramp between),
    and an event is emitted whenever the factor changes. The resulting trace
    is temporally correlated and trending: degradation precedes
    disconnection, giving a warning the memoryless generator never gives,
    and links recover when nodes re-approach.

    Args:
        network: The topology; define links for every pair that may ever be
            in range (the trace closes pairs that start out of range at t=0)
        trajectories: node_id -> trajectory for the mobile nodes
        horizon: Sample [0, horizon]
        dt: Sampling interval; transitions resolve to this resolution
        r_full: Distance up to which the link runs at full bandwidth
        r_max: Distance beyond which the link is down
        levels: Quantization steps of the degradation ramp
    """
    if r_full <= 0 or r_max <= r_full:
        raise ValueError("require 0 < r_full < r_max")
    if dt <= 0 or horizon <= 0 or levels < 2:
        raise ValueError("require dt > 0, horizon > 0, levels >= 2")

    def trajectory_of(node_id: str) -> Waypoints:
        if node_id in trajectories:
            return trajectories[node_id]
        position = network.nodes[node_id].position
        return static_trajectory(position.x, position.y)

    events: List[DisruptionEvent] = []
    for key, link_ids in sorted(radio_pairs(network).items(), key=lambda kv: sorted(kv[0])):
        endpoints = sorted(key)
        if len(endpoints) == 1:
            continue  # Self-loop; distance never changes
        traj_a, traj_b = trajectory_of(endpoints[0]), trajectory_of(endpoints[1])

        previous = 1.0  # Engine link state starts up at full bandwidth
        steps = int(horizon / dt) + 1
        for i in range(steps):
            t = round(i * dt, 6)
            ax, ay = traj_a.position(t)
            bx, by = traj_b.position(t)
            current = _quantized_factor(
                math.hypot(ax - bx, ay - by), r_full, r_max, levels
            )
            if current == previous:
                continue
            if current == 0.0:
                events.extend(_pair_events(link_ids, t, DisruptionType.LINK_DOWN))
            else:
                if previous == 0.0:
                    # Recovery restores full bandwidth; a same-instant degrade
                    # then applies the partial factor (insertion order is
                    # preserved for same-time events).
                    events.extend(_pair_events(link_ids, t, DisruptionType.RECOVERY))
                if current < 1.0:
                    events.extend(
                        _pair_events(
                            link_ids,
                            t,
                            DisruptionType.LINK_DEGRADE,
                            parameters={"bandwidth_factor": current},
                        )
                    )
                elif previous != 0.0:
                    events.extend(_pair_events(link_ids, t, DisruptionType.RECOVERY))
            previous = current

    events.sort(key=lambda e: e.time)  # Stable: preserves per-instant order
    return events


@dataclass(frozen=True)
class Jammer:
    """An area jammer active for a window of time.

    Attributes:
        x, y: Jammer position
        radius: Every radio pair with an endpoint within this range is jammed
        start: Activation time
        duration: How long the jammer stays active
    """

    x: float
    y: float
    radius: float
    start: float
    duration: float

    def __post_init__(self):
        if self.radius <= 0 or self.duration <= 0:
            raise ValueError("Jammer radius and duration must be positive")

    @property
    def end(self) -> float:
        return self.start + self.duration


def jammer_targeting(
    network: Network, between: Tuple[str, str], radius: float, start: float, duration: float
) -> Jammer:
    """Place a jammer at the midpoint of a radio link -- the targeted attack.

    The adversarial variant of the generator: aim at the link the schedule
    leans on hardest. Nearby links within the radius fall as collateral.
    """
    pos_a = network.nodes[between[0]].position
    pos_b = network.nodes[between[1]].position
    return Jammer(
        x=(pos_a.x + pos_b.x) / 2,
        y=(pos_a.y + pos_b.y) / 2,
        radius=radius,
        start=start,
        duration=duration,
    )


def jamming_trace(network: Network, jammers: List[Jammer]) -> List[DisruptionEvent]:
    """G4: spatially correlated outages from area jammers.

    A radio pair is jammed while any jammer with an endpoint of the pair in
    range is active (a jammed receiver kills the inbound direction and CSMA
    silences the outbound one, so the pair goes down as a unit). Overlapping
    windows from multiple jammers merge into one outage per pair. Positions
    are the static scenario positions; composing jamming with mobility needs
    a position-aware variant.

    The distinguishing structure: several links fail at the same instant with
    no warning -- the opposite ends of the correlation spectrum from the
    memoryless and mobility generators.

    Args:
        network: The topology (node positions locate the endpoints)
        jammers: Active jammers

    Returns:
        Time-ordered LINK_DOWN events (both directions per pair) with their
        outage durations; recovery is automatic
    """
    events: List[DisruptionEvent] = []
    for key, link_ids in sorted(radio_pairs(network).items(), key=lambda kv: sorted(kv[0])):
        endpoints = sorted(key)
        if len(endpoints) == 1:
            continue
        windows = []
        for jammer in jammers:
            for node_id in endpoints:
                position = network.nodes[node_id].position
                if math.hypot(position.x - jammer.x, position.y - jammer.y) <= jammer.radius:
                    windows.append((jammer.start, jammer.end))
                    break
        if not windows:
            continue
        # Merge overlapping or touching windows into maximal outages.
        windows.sort()
        merged = [windows[0]]
        for start, end in windows[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        for start, end in merged:
            events.extend(
                _pair_events(
                    link_ids, start, DisruptionType.LINK_DOWN, duration=end - start
                )
            )

    events.sort(key=lambda e: (e.time, e.target_id))
    return events
