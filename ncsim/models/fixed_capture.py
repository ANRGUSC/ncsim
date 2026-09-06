"""Experimental fixed-MCS, single-hidden-interferer overlap approximation.

This opt-in model makes the original Figure 6 analytical helper executable in
the normal flow engine. It is not a replacement for the default effective-rate
model. It uses the inherited airtime proxy and capture threshold, not a fitted
packet-error model or a coupled retry/backoff solution.
"""
import math

from ncsim.models.interference import CsmaBianchiInterference
from ncsim.models.wifi import (
    MCS_TABLES, capture_sinr_threshold, euclidean_distance,
    hidden_terminal_success_rate, received_power_dBm,
    saturated_airtime_fraction, sinr_dB,
)


class UnsupportedCaptureTopology(ValueError):
    """The active topology is outside the optional model's supported scope."""


class FixedCaptureOverlapInterference(CsmaBianchiInterference):
    """Hold each clean link MCS fixed and apply the original overlap helper.

    Supported hidden interactions are isolated pairs: one active hidden link
    at each receiver and no concurrent sensed contenders at either transmitter.
    Pure contention uses the unchanged parent Bianchi calculation. A hidden
    interferer's isolated data airtime is a proxy for temporal overlap; the
    model does not resolve packet starts, ACK interference, or retry feedback.
    Only 802.11ax/20 MHz, default MAC timings, and no RTS/CTS are supported.
    Packet validation currently covers two equal 30 m links at MCS 5.

    Unsupported active combinations raise rather than silently falling back to
    a different model. The event engine's active-set notifications are inherited.
    """

    hidden_terminal_model = 'fixed_capture_overlap'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.rf.wifi_standard != 'ax' or self.rf.channel_width_mhz != 20 or self.rf.rts_cts:
            raise ValueError('fixed_capture_overlap requires 802.11ax/20 MHz without RTS/CTS')
        if not math.isfinite(self.rf.capture_margin_dB):
            raise ValueError('capture_margin_dB must be finite')
        supported = [rate for _, rate in MCS_TABLES['ax']]
        for link_id, rate in self._base_rates.items():
            if not math.isfinite(rate) or rate < 0:
                raise ValueError(f'Invalid fixed PHY rate for {link_id}: {rate}')
            if rate > 0 and not any(abs(rate * 8 - value) < 0.1 for value in supported):
                raise ValueError(f'Fixed PHY rate for {link_id} must match an ax MCS entry')

    def get_interference_factor(self, link_id, active_link_ids, network):
        hidden = active_link_ids & self._hidden_neighbors.get(link_id, set())
        if (link_id not in active_link_ids or not self.hidden_terminals_enabled
                or not hidden or self._base_rates.get(link_id, 0) <= 0):
            return super().get_interference_factor(link_id, active_link_ids, network)
        if len(hidden) != 1:
            raise UnsupportedCaptureTopology('fixed_capture_overlap supports one active hidden interferer per link')
        interferer_id = next(iter(hidden))
        for candidate in (link_id, interferer_id):
            if active_link_ids & self.conflict_graph.conflicts.get(candidate, set()):
                raise UnsupportedCaptureTopology('fixed_capture_overlap does not support mixed hidden and sensed contention')
            if len(active_link_ids & self._hidden_neighbors.get(candidate, set())) > 1:
                raise UnsupportedCaptureTopology('fixed_capture_overlap requires isolated hidden-link pairs')

        def power(tx, rx):
            distance = euclidean_distance(network.nodes[tx].position, network.nodes[rx].position)
            fading = self.shadow_fading_map.get((tx, rx), 0.0)
            return received_power_dBm(self.rf.tx_power_dBm, distance, self.rf, fading)

        link = network.links[link_id]
        interferer = network.links[interferer_id]
        interferer_rate = self._base_rates[interferer_id] * 8
        if interferer_rate <= 0:
            raise UnsupportedCaptureTopology('A zero-rate hidden interferer has no defined data airtime')
        sinr = sinr_dB(power(link.from_node, link.to_node),
                       [power(interferer.from_node, link.to_node)], self.rf.noise_floor_dBm)
        threshold = capture_sinr_threshold(self._base_rates[link_id] * 8,
                                           capture_margin_dB=self.rf.capture_margin_dB)
        airtime = saturated_airtime_fraction(phy_rate_mbps=interferer_rate)
        # Link bandwidth is already solo-MAC-normalized. Do not apply eta(1)
        # a second time, or select a lower MCS under interference.
        return hidden_terminal_success_rate(sinr, threshold, airtime)
