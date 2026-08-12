"""
Node trajectories for mobility-driven failure traces.

A trajectory is a piecewise-linear path through 2D space: a list of timed
waypoints with linear interpolation between them and clamping outside. Two
standard patterns are provided on top:

- random_waypoint_trajectory: the classic Random Waypoint model -- pick a
  uniform destination in the area, travel at a sampled speed, pause, repeat.
- convoy_trajectories: a group pattern (RPGM-style with fixed offsets) --
  members hold formation around a shared reference path, so their mutual
  links are stable while links to stationary infrastructure stretch and
  break as the convoy moves.

Trajectories are deterministic given their seed; the failure trace compiled
from them (see failure_traces.mobility_trace) inherits that determinism.
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Waypoints:
    """A piecewise-linear trajectory through timed 2D waypoints.

    Attributes:
        points: (time, x, y) tuples in strictly increasing time order
    """

    points: Tuple[Tuple[float, float, float], ...]

    def __post_init__(self):
        if not self.points:
            raise ValueError("Waypoints requires at least one point")
        times = [t for t, _, _ in self.points]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("Waypoint times must be strictly increasing")

    def position(self, time: float) -> Tuple[float, float]:
        """Position at `time`: linear interpolation, clamped at the ends."""
        points = self.points
        if time <= points[0][0]:
            return points[0][1], points[0][2]
        if time >= points[-1][0]:
            return points[-1][1], points[-1][2]
        for (t0, x0, y0), (t1, x1, y1) in zip(points, points[1:]):
            if t0 <= time <= t1:
                alpha = (time - t0) / (t1 - t0)
                return x0 + alpha * (x1 - x0), y0 + alpha * (y1 - y0)
        raise AssertionError("unreachable: time inside waypoint range")


def static_trajectory(x: float, y: float) -> Waypoints:
    """A node that never moves."""
    return Waypoints(points=((0.0, x, y),))


def random_waypoint_trajectory(
    area: Tuple[float, float, float, float],
    speed: Tuple[float, float],
    pause: float,
    horizon: float,
    seed: int = 42,
    start: Tuple[float, float] = None,
) -> Waypoints:
    """The classic Random Waypoint mobility model.

    From the current position, pick a uniform destination in `area`, travel
    to it in a straight line at a speed sampled uniformly from `speed`,
    pause, and repeat until `horizon`.

    Args:
        area: (x_min, y_min, x_max, y_max) bounding box
        speed: (min, max) travel speed in distance units per second
        pause: Pause duration at each waypoint
        horizon: Generate waypoints covering [0, horizon]
        seed: RNG seed; identical seeds yield identical trajectories
        start: Starting position; default a uniform point in the area

    Returns:
        The trajectory
    """
    x_min, y_min, x_max, y_max = area
    if speed[0] <= 0 or speed[1] < speed[0]:
        raise ValueError("speed must be (min, max) with 0 < min <= max")
    rng = random.Random(f"rwp:{seed}")

    if start is None:
        start = (rng.uniform(x_min, x_max), rng.uniform(y_min, y_max))
    t, (x, y) = 0.0, start
    points: List[Tuple[float, float, float]] = [(t, x, y)]

    while t < horizon:
        dest_x = rng.uniform(x_min, x_max)
        dest_y = rng.uniform(y_min, y_max)
        distance = math.hypot(dest_x - x, dest_y - y)
        travel = distance / rng.uniform(*speed)
        if travel > 0:
            t += travel
            x, y = dest_x, dest_y
            points.append((t, x, y))
        if pause > 0:
            t += pause
            points.append((t, x, y))
    return Waypoints(points=tuple(points))


def convoy_trajectories(
    reference: Waypoints,
    offsets: Dict[str, Tuple[float, float]],
) -> Dict[str, Waypoints]:
    """A group of nodes holding fixed formation around a reference path.

    RPGM with zero jitter: each member's position is the reference position
    plus its offset, so intra-convoy links are stable by construction while
    links to nodes outside the convoy stretch and break with the movement.

    Args:
        reference: The shared reference path (e.g. a road as waypoints)
        offsets: node_id -> (dx, dy) formation offset from the reference

    Returns:
        node_id -> trajectory
    """
    return {
        node_id: Waypoints(
            points=tuple((t, x + dx, y + dy) for t, x, y in reference.points)
        )
        for node_id, (dx, dy) in offsets.items()
    }
