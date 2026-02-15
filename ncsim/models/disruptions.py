"""
Network and node disruption model definitions.

Phase 2: No disruptions (stable network).
Future: Jamming, node failures, link degradation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict, Any


class DisruptionType(Enum):
    """Types of network/node disruptions."""
    LINK_DOWN = auto()       # Link completely unavailable
    LINK_DEGRADE = auto()    # Link bandwidth reduced
    NODE_DOWN = auto()       # Node unavailable
    NODE_DEGRADE = auto()    # Node capacity reduced
    JAMMING = auto()         # Interference on a link
    RECOVERY = auto()        # End of a disruption


@dataclass
class DisruptionEvent:
    """A disruption in the network.

    Attributes:
        time: When the disruption occurs
        target_type: "link" or "node"
        target_id: ID of affected link or node
        disruption_type: Type of disruption
        duration: How long disruption lasts (None = permanent)
        parameters: Disruption-specific parameters
    """
    time: float
    target_type: str  # "link" or "node"
    target_id: str
    disruption_type: DisruptionType
    duration: Optional[float] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.target_type not in ("link", "node"):
            raise ValueError(f"target_type must be 'link' or 'node', got '{self.target_type}'")


class DisruptionModel(ABC):
    """Abstract base class for disruption generation.

    Phase 2: NoDisruptions returns no events.
    Future: StochasticJamming, AdversarialJamming, ScheduledFailures, etc.
    """

    @abstractmethod
    def get_next_disruption(self, current_time: float) -> Optional[DisruptionEvent]:
        """Get the next disruption event.

        Args:
            current_time: Current simulation time

        Returns:
            Next disruption event, or None if no more disruptions
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset disruption state to initial conditions."""
        pass


class NoDisruptions(DisruptionModel):
    """Phase 2 implementation: Stable network with no disruptions."""

    def get_next_disruption(self, current_time: float) -> Optional[DisruptionEvent]:
        """Return None - no disruptions in Phase 2."""
        return None

    def reset(self) -> None:
        """Nothing to reset."""
        pass


class ScheduledDisruptions(DisruptionModel):
    """Disruptions at predetermined times.

    Useful for testing failure scenarios.
    Not used in Phase 2 - placeholder for future.
    """

    def __init__(self, disruptions: list[DisruptionEvent]):
        self._disruptions = sorted(disruptions, key=lambda d: d.time)
        self._next_index = 0

    def get_next_disruption(self, current_time: float) -> Optional[DisruptionEvent]:
        """Return next scheduled disruption."""
        if self._next_index >= len(self._disruptions):
            return None

        disruption = self._disruptions[self._next_index]
        if disruption.time >= current_time:
            self._next_index += 1
            return disruption

        return None

    def reset(self) -> None:
        """Reset to first disruption."""
        self._next_index = 0
