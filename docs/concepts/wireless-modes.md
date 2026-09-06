# Wireless modes and optional fixed capture

`raw_phy` uses clean PHY rates. `solo_80211` includes single-link MAC overhead
without concurrent-link effects. `full_wireless` starts from the same Solo
goodput matrix and applies active contention and hidden-terminal interference.
The CLI and `ncsim.models.wireless.configure_wireless` use the same rate and
RTS/CTS normalization. Explicit bandwidths are clean PHY rates in MB/s.
Legacy `none` and `csma_bianchi` names remain accepted.

The default hidden-terminal treatment is `effective_rate`: active unsensed
transmitters contribute receiver power to an SINR-based service-rate calculation.
Shared endpoints conflict because they share a half-duplex radio. Zero service
pauses transfers; if no future event can restore progress, the run reports
`blocked`. This is distinct from a time limit or an unreachable route. The CLI
returns nonzero for any status other than `completed`. A diagnostic positive
outage floor is explicit and changes the model; it is not a remedy for outages.

## Fixed-capture option

Select `--interference full_wireless --hidden-terminal-model fixed_capture_overlap`,
or pass `hidden_terminal_model="fixed_capture_overlap"` to `configure_wireless`.
It is disabled by default. The option holds each clean MCS fixed and uses an
airtime-overlap and capture approximation for isolated hidden-link pairs.
Pure sensed contention follows the default Bianchi calculation.

Supported operation is 802.11ax, 20 MHz, default MAC timings, and no RTS/CTS.
Each receiver may have one active hidden interferer and neither member may
simultaneously have sensed contenders. Unsupported active combinations raise
an error instead of silently switching models. This is not a general
multi-interferer or packet-level retry model. Saved packet comparisons cover
equal 30 m links at MCS 5; they do not establish accuracy outside that setting.

Run `python -m pytest tests/test_optional_hidden.py tests/test_public_interfaces.py`
for bounded regression checks. The
[study artifact](https://github.com/ANRGUSC/ncsim/tree/paper/artifacts/arxiv-2605.01094)
contains the saved packet observations and its separate `hidden` comparison
command. These checks do not launch ns-3 or a research campaign.

## Other implementation changes

The event engine credits in-flight bytes before applying changed rates and
serializes tasks on each compute node in ready order. `minimum_hop` routing
minimizes hop count over usable positive-bandwidth links; `shortest_path`
continues to minimize latency. These are correctness and routing changes, not
effects of enabling the optional capture model.

The built-in `conflict_aware_heft` and `uniform_discount_heft` policies use
modified communication estimates for static placement; `all_on_fastest` places
all tasks on the fastest node. They supplement `round_robin`, `manual`, and the
installed SAGA catalog and do not replace the default HEFT policy. Their
placement estimates are not an interference-aware execution schedule.
