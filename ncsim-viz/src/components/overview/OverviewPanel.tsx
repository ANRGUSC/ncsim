import { useMemo } from 'react';
import type { Scenario } from '../../types/scenario';
import type { MetricsData } from '../../types/metrics';
import type { TraceEvent } from '../../types/trace';
import { Clock, Cpu, ArrowRightLeft, Zap, Network, GitBranch } from 'lucide-react';

interface Props {
  scenario: Scenario;
  metrics: MetricsData;
  trace: TraceEvent[];
}

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub?: string }) {
  return (
    <div className="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
      <div className="flex items-center gap-2 text-[var(--color-text-secondary)] text-xs mb-2">
        {icon}
        {label}
      </div>
      <div className="text-2xl font-bold text-[var(--color-accent)]">{value}</div>
      {sub && <div className="text-xs text-[var(--color-text-secondary)] mt-1">{sub}</div>}
    </div>
  );
}

function UtilizationBar({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs font-mono w-12 text-right text-[var(--color-text-secondary)]">{label}</span>
      <div className="flex-1 h-5 rounded-full bg-[var(--color-bg)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            background: pct > 70 ? 'var(--color-accent-green)' : pct > 30 ? 'var(--color-accent)' : 'var(--color-text-secondary)',
          }}
        />
      </div>
      <span className="text-xs font-mono w-10 text-[var(--color-text-secondary)]">{pct}%</span>
    </div>
  );
}

export function OverviewPanel({ scenario, metrics, trace }: Props) {
  const scheduler = scenario.config.scheduler;
  const routing = scenario.config.routing ?? 'direct';
  const interference = scenario.config.interference ?? 'none';

  const simStart = useMemo(() => {
    const e = trace.find((t) => t.type === 'sim_start');
    return e && 'seed' in e ? e : null;
  }, [trace]);

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Title */}
      <div>
        <h2 className="text-2xl font-bold">{scenario.name}</h2>
        <div className="flex gap-3 mt-2 text-xs text-[var(--color-text-secondary)]">
          <span>Scheduler: <strong className="text-[var(--color-text)]">{scheduler}</strong></span>
          <span>Routing: <strong className="text-[var(--color-text)]">{routing}</strong></span>
          <span>Interference: <strong className="text-[var(--color-text)]">{interference}</strong></span>
          {simStart && <span>Seed: <strong className="text-[var(--color-text)]">{simStart.seed}</strong></span>}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard icon={<Clock size={14} />} label="Makespan" value={`${metrics.makespan.toFixed(3)}s`} />
        <StatCard icon={<Cpu size={14} />} label="Tasks" value={String(metrics.total_tasks)} />
        <StatCard icon={<ArrowRightLeft size={14} />} label="Transfers" value={String(metrics.total_transfers)} />
        <StatCard icon={<Zap size={14} />} label="Events" value={String(metrics.total_events)} />
        <StatCard icon={<Network size={14} />} label="Nodes" value={String(scenario.network.nodes.length)} />
        <StatCard icon={<GitBranch size={14} />} label="Links" value={String(scenario.network.links.length)} />
      </div>

      {/* Utilization */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
          <h3 className="text-sm font-semibold mb-3">Node Utilization</h3>
          <div className="space-y-2">
            {Object.entries(metrics.node_utilization).map(([id, val]) => (
              <UtilizationBar key={id} label={id} value={val} />
            ))}
          </div>
        </div>
        <div className="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
          <h3 className="text-sm font-semibold mb-3">Link Utilization</h3>
          <div className="space-y-2">
            {Object.entries(metrics.link_utilization).length > 0 ? (
              Object.entries(metrics.link_utilization).map(([id, val]) => (
                <UtilizationBar key={id} label={id} value={val} />
              ))
            ) : (
              <p className="text-xs text-[var(--color-text-secondary)]">No link utilization data (local transfers only)</p>
            )}
          </div>
        </div>
      </div>

      {/* WiFi info */}
      {metrics.rf_config && (
        <div className="p-4 rounded-xl bg-[var(--color-bg)] border border-[var(--color-border)]">
          <h3 className="text-sm font-semibold mb-2">WiFi Configuration</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {Object.entries(metrics.rf_config).map(([k, v]) => (
              <div key={k}>
                <span className="text-[var(--color-text-secondary)]">{k}: </span>
                <span className="font-mono">{String(v)}</span>
              </div>
            ))}
          </div>
          {metrics.carrier_sensing_range_m && (
            <p className="text-xs mt-2 text-[var(--color-text-secondary)]">
              Carrier sensing range: <strong className="text-[var(--color-text)]">{metrics.carrier_sensing_range_m.toFixed(1)}m</strong>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
