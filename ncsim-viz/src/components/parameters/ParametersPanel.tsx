import { useMemo } from 'react';
import type { Scenario } from '../../types/scenario';
import type { MetricsData } from '../../types/metrics';
import type { TraceEvent } from '../../types/trace';
import { getTaskAssignments } from '../../engine/SimulationState';

interface Props {
  scenario: Scenario;
  metrics: MetricsData;
  trace: TraceEvent[];
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
      <h3 className="text-sm font-semibold mb-3">{title}</h3>
      {children}
    </div>
  );
}

function KV({ label, value }: { label: string; value: string | number | boolean }) {
  return (
    <div className="flex justify-between py-1 border-b border-[var(--color-border)]/50 last:border-0">
      <span className="text-xs text-[var(--color-text-secondary)]">{label}</span>
      <span className="text-xs font-mono text-[var(--color-text)]">{String(value)}</span>
    </div>
  );
}

export function ParametersPanel({ scenario, metrics, trace }: Props) {
  const cfg = scenario.config;

  const assignments = useMemo(() => getTaskAssignments(trace), [trace]);

  return (
    <div className="p-6 space-y-4 max-w-4xl mx-auto overflow-auto h-full">
      <h2 className="text-xl font-bold mb-4">Parameters</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Scenario */}
        <Section title="Scenario">
          <KV label="Name" value={scenario.name} />
          <KV label="Seed" value={cfg.seed} />
          <KV label="Nodes" value={scenario.network.nodes.length} />
          <KV label="Links" value={scenario.network.links.length} />
          <KV label="DAGs" value={scenario.dags.length} />
          <KV label="Total Tasks" value={metrics.total_tasks} />
          <KV label="Total Transfers" value={metrics.total_transfers} />
          <KV label="Total Events" value={metrics.total_events} />
        </Section>

        {/* Scheduler & Results */}
        <Section title="Scheduler">
          <KV label="Algorithm" value={cfg.scheduler} />
          <KV label="Makespan" value={`${metrics.makespan.toFixed(6)}s`} />
          <KV label="Status" value={metrics.status} />
        </Section>

        {/* Routing */}
        <Section title="Routing">
          <KV label="Algorithm" value={cfg.routing ?? 'direct'} />
          <p className="text-xs text-[var(--color-text-secondary)] mt-2">
            {cfg.routing === 'widest_path'
              ? 'Widest-path routing selects the route with maximum bottleneck bandwidth.'
              : cfg.routing === 'shortest_path'
              ? 'Shortest-path routing minimizes hop count between nodes.'
              : 'Direct routing uses only explicitly declared links (single-hop).'}
          </p>
        </Section>

        {/* Interference */}
        <Section title="Interference Model">
          <KV label="Model" value={cfg.interference ?? 'none'} />
          {cfg.interference_radius != null && (
            <KV label="Radius" value={`${cfg.interference_radius}m`} />
          )}
          <p className="text-xs text-[var(--color-text-secondary)] mt-2">
            {cfg.interference === 'csma_clique'
              ? 'Static clique model: link bandwidth = PHY_rate / max_clique_size.'
              : cfg.interference === 'csma_bianchi'
              ? 'Bianchi saturation model: MAC throughput derived from collision probability and backoff.'
              : cfg.interference === 'proximity'
              ? `Proximity-based: links within ${cfg.interference_radius ?? '?'}m share bandwidth.`
              : 'No interference model applied. Links use declared bandwidth.'}
          </p>
        </Section>
      </div>

      {/* WiFi RF Configuration (from scenario YAML or metrics) */}
      {(cfg.rf || metrics.rf_config) && (
        <Section title="WiFi RF Configuration (PHY Parameters)">
          <div className="grid grid-cols-2 gap-x-6">
            {cfg.rf ? (
              <>
                <KV label="TX Power" value={`${cfg.rf.tx_power_dBm} dBm`} />
                <KV label="Frequency" value={`${cfg.rf.freq_ghz} GHz`} />
                <KV label="Path Loss Exponent" value={cfg.rf.path_loss_exponent ?? 'N/A'} />
                <KV label="Noise Floor" value={`${cfg.rf.noise_floor_dBm} dBm`} />
                <KV label="CCA Threshold" value={`${cfg.rf.cca_threshold_dBm} dBm`} />
                <KV label="Channel Width" value={`${cfg.rf.channel_width_mhz} MHz`} />
                <KV label="WiFi Standard" value={`802.11${cfg.rf.wifi_standard}`} />
                <KV label="Shadow Fading σ" value={cfg.rf.shadow_fading_sigma ?? 0} />
                <KV label="RTS/CTS" value={cfg.rf.rts_cts ? 'Enabled' : 'Disabled'} />
              </>
            ) : metrics.rf_config ? (
              Object.entries(metrics.rf_config).map(([k, v]) => (
                <KV key={k} label={k} value={String(v)} />
              ))
            ) : null}
          </div>
        </Section>
      )}

      {/* Derived WiFi Values (from metrics) */}
      {metrics.carrier_sensing_range_m != null && (
        <Section title="Derived WiFi Values">
          <KV label="Carrier Sensing Range" value={`${metrics.carrier_sensing_range_m.toFixed(1)}m`} />
          {metrics.link_phy_rates_MBps && (
            <>
              <h4 className="text-xs font-semibold mt-3 mb-1 text-[var(--color-text-secondary)]">Link PHY Rates</h4>
              {Object.entries(metrics.link_phy_rates_MBps).map(([k, v]) => (
                <KV key={k} label={k} value={`${v.toFixed(1)} MB/s`} />
              ))}
            </>
          )}
          {metrics.max_clique_sizes && (
            <>
              <h4 className="text-xs font-semibold mt-3 mb-1 text-[var(--color-text-secondary)]">Max Clique Sizes</h4>
              {Object.entries(metrics.max_clique_sizes).map(([k, v]) => (
                <KV key={k} label={k} value={v} />
              ))}
            </>
          )}
        </Section>
      )}

      {/* Task Assignments */}
      {assignments.size > 0 && (
        <Section title="Task Assignments (Scheduler Output)">
          <div className="overflow-auto max-h-64">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[var(--color-text-secondary)]">
                  <th className="text-left py-1">Task</th>
                  <th className="text-left py-1">Node</th>
                  <th className="text-right py-1">Compute Cost</th>
                </tr>
              </thead>
              <tbody>
                {scenario.dags.flatMap((dag) =>
                  dag.tasks.map((task) => (
                    <tr key={task.id} className="border-t border-[var(--color-border)]/30">
                      <td className="py-1 font-mono">{task.id}</td>
                      <td className="font-mono">{assignments.get(task.id) ?? '—'}</td>
                      <td className="text-right font-mono">{task.compute_cost} CU</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Network Nodes */}
        <Section title="Network Nodes">
          <div className="overflow-auto max-h-48">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[var(--color-text-secondary)]">
                  <th className="text-left py-1">ID</th>
                  <th className="text-right py-1">Capacity</th>
                  <th className="text-right py-1">Position</th>
                  <th className="text-right py-1">Util.</th>
                </tr>
              </thead>
              <tbody>
                {scenario.network.nodes.map((n) => (
                  <tr key={n.id} className="border-t border-[var(--color-border)]/30">
                    <td className="py-1 font-mono">{n.id}</td>
                    <td className="text-right font-mono">{n.compute_capacity} CU/s</td>
                    <td className="text-right font-mono">({n.position.x}, {n.position.y})</td>
                    <td className="text-right font-mono">{((metrics.node_utilization[n.id] ?? 0) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>

        {/* Network Links */}
        <Section title="Network Links">
          <div className="overflow-auto max-h-48">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[var(--color-text-secondary)]">
                  <th className="text-left py-1">ID</th>
                  <th className="text-left py-1">From→To</th>
                  <th className="text-right py-1">BW</th>
                  <th className="text-right py-1">Latency</th>
                  <th className="text-right py-1">Util.</th>
                </tr>
              </thead>
              <tbody>
                {scenario.network.links.map((l) => (
                  <tr key={l.id} className="border-t border-[var(--color-border)]/30">
                    <td className="py-1 font-mono">{l.id}</td>
                    <td className="font-mono">{l.from}→{l.to}</td>
                    <td className="text-right font-mono">{l.bandwidth} MB/s</td>
                    <td className="text-right font-mono">{l.latency}s</td>
                    <td className="text-right font-mono">{((metrics.link_utilization[l.id] ?? 0) * 100).toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>

      {/* DAG Edges */}
      <Section title="DAG Edges (Data Dependencies)">
        <div className="overflow-auto max-h-48">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--color-text-secondary)]">
                <th className="text-left py-1">From Task</th>
                <th className="text-left py-1">To Task</th>
                <th className="text-right py-1">Data Size</th>
              </tr>
            </thead>
            <tbody>
              {scenario.dags.flatMap((dag) =>
                dag.edges.map((e, i) => (
                  <tr key={`${dag.id}-${i}`} className="border-t border-[var(--color-border)]/30">
                    <td className="py-1 font-mono">{e.from}</td>
                    <td className="font-mono">{e.to}</td>
                    <td className="text-right font-mono">{e.data_size} MB</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
