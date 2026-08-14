import { useState, useMemo, useEffect } from 'react';
import { ArrowLeft, Play, Loader2, AlertCircle } from 'lucide-react';
import yaml from 'js-yaml';
import type { NodeDef, LinkDef, TaskDef, EdgeDef } from '../../types/scenario';
import type {
  SchedulerDefinition,
  SchedulerOptionDefinition,
  SchedulerOptionValue,
} from '../../types/api';
import { TopologySection } from './TopologySection';
import { DagSection } from './DagSection';
import { InterferenceSection } from './InterferenceSection';
import type { RFFormState } from './InterferenceSection';
import { YamlPreview } from './YamlPreview';
import { useRunExperiment } from '../../hooks/useRunExperiment';
import type { TopologyPreset, TopologyParams, RFParams } from './topologyPresets';
import type { DagPreset, DagParams } from './dagPresets';
import { generateTopology } from './topologyPresets';
import { generateDag } from './dagPresets';

interface Props {
  onBack: () => void;
  onLoadResults: (scenario: string, trace: string, metrics: string) => void;
}

const DEFAULT_TOPO_PARAMS: TopologyParams = {
  nodeCount: 3,
  defaultCapacity: 100,
  defaultBandwidth: 100,
  defaultLatency: 0.001,
};

const DEFAULT_DAG_PARAMS: DagParams = {
  taskCount: 3,
  defaultComputeCost: 100,
  defaultDataSize: 50,
};

const DEFAULT_RF: RFFormState = {
  tx_power_dBm: 20,
  freq_ghz: 5.0,
  path_loss_exponent: 3.0,
  noise_floor_dBm: -95,
  cca_threshold_dBm: -82,
  channel_width_mhz: 20,
  wifi_standard: 'ax',
  shadow_fading_sigma: 0,
  rts_cts: false,
};

const FALLBACK_SCHEDULERS: SchedulerDefinition[] = [
  { name: 'heft', label: 'HEFT', kind: 'saga', description: '', options: [] },
  { name: 'cpop', label: 'CPOP', kind: 'saga', description: '', options: [] },
  { name: 'round_robin', label: 'Round Robin', kind: 'builtin', description: '', options: [] },
  { name: 'manual', label: 'Manual', kind: 'builtin', description: '', options: [] },
];

export function ExperimentForm({ onBack, onLoadResults }: Props) {
  // Basic config
  const [name, setName] = useState('my-experiment');
  const [scheduler, setScheduler] = useState('heft');
  const [schedulers, setSchedulers] = useState<SchedulerDefinition[]>(FALLBACK_SCHEDULERS);
  const [schedulerOptions, setSchedulerOptions] = useState<Record<string, SchedulerOptionValue>>({});
  const [routing, setRouting] = useState('direct');
  const [seed, setSeed] = useState(42);

  // Interference
  const [interference, setInterference] = useState('none');
  const [interferenceRadius, setInterferenceRadius] = useState(15);
  const [rf, setRf] = useState<RFFormState>(DEFAULT_RF);

  // Topology
  const [topoPreset, setTopoPreset] = useState<TopologyPreset>('line');
  const [topoParams, setTopoParams] = useState<TopologyParams>(DEFAULT_TOPO_PARAMS);
  const initialTopo = generateTopology('line', DEFAULT_TOPO_PARAMS);
  const [nodes, setNodes] = useState<NodeDef[]>(initialTopo.nodes);
  const [links, setLinks] = useState<LinkDef[]>(initialTopo.links);

  // DAG
  const [dagPreset, setDagPreset] = useState<DagPreset>('chain');
  const [dagParams, setDagParams] = useState<DagParams>(DEFAULT_DAG_PARAMS);
  const initialDag = generateDag('chain', DEFAULT_DAG_PARAMS);
  const [tasks, setTasks] = useState<TaskDef[]>(initialDag.tasks);
  const [edges, setEdges] = useState<EdgeDef[]>(initialDag.edges);

  // RF params subset for radio range calculation
  const rfParams: RFParams = useMemo(() => ({
    tx_power_dBm: rf.tx_power_dBm,
    freq_ghz: rf.freq_ghz,
    path_loss_exponent: rf.path_loss_exponent,
    noise_floor_dBm: rf.noise_floor_dBm,
  }), [rf.tx_power_dBm, rf.freq_ghz, rf.path_loss_exponent, rf.noise_floor_dBm]);

  // Regenerate random topology when RF params or seed change
  useEffect(() => {
    if (topoPreset === 'random') {
      const { nodes: n, links: l } = generateTopology('random', topoParams, rfParams, seed);
      setNodes(n);
      setLinks(l);
    }
  }, [rfParams, seed, topoPreset]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    let cancelled = false;
    fetch('/api/schedulers')
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<SchedulerDefinition[]>;
      })
      .then((catalog) => {
        if (!cancelled) setSchedulers(catalog);
      })
      .catch(() => {
        // Keep the core fallback choices when the backend is not yet running.
      });
    return () => { cancelled = true; };
  }, []);

  const selectedScheduler = useMemo(
    () => schedulers.find((entry) => entry.name === scheduler),
    [schedulers, scheduler],
  );

  const handleSchedulerChange = (name: string) => {
    const definition = schedulers.find((entry) => entry.name === name);
    setScheduler(name);
    setSchedulerOptions(Object.fromEntries(
      (definition?.options ?? []).map((option) => [option.name, option.default]),
    ));
  };

  const updateSchedulerOption = (
    option: SchedulerOptionDefinition,
    rawValue: string,
  ) => {
    let value: SchedulerOptionValue = rawValue;
    if (rawValue === '' && option.nullable) {
      value = null;
    } else if (option.type === 'integer') {
      value = Number.parseInt(rawValue, 10);
    } else if (option.type === 'number') {
      value = Number.parseFloat(rawValue);
    } else if (option.type === 'boolean') {
      value = rawValue === 'true';
    }
    setSchedulerOptions((current) => ({ ...current, [option.name]: value }));
  };

  // Run state
  const { run, running, error: runError } = useRunExperiment();

  // Generate YAML
  const scenarioYaml = useMemo(() => {
    const scenario: Record<string, unknown> = {
      name: name || 'Experiment',
      network: {
        nodes: nodes.map((n) => ({
          id: n.id,
          compute_capacity: n.compute_capacity,
          position: { x: n.position.x, y: n.position.y },
        })),
        links: links.map((l) => ({
          id: l.id,
          from: l.from,
          to: l.to,
          bandwidth: l.bandwidth,
          latency: l.latency,
        })),
      },
      dags: [
        {
          id: 'dag_1',
          inject_at: 0.0,
          tasks: tasks.map((t) => {
            const task: Record<string, unknown> = { id: t.id, compute_cost: t.compute_cost };
            if (t.pinned_to) task.pinned_to = t.pinned_to;
            return task;
          }),
          edges: edges.map((e) => ({
            from: e.from,
            to: e.to,
            data_size: e.data_size,
          })),
        },
      ],
      config: {
        scheduler,
        ...(selectedScheduler?.options.length && { scheduler_options: schedulerOptions }),
        seed,
        routing,
        ...(interference !== 'none' && { interference }),
        ...(interference === 'proximity' && { interference_radius: interferenceRadius }),
        ...((interference === 'csma_clique' || interference === 'csma_bianchi') && {
          rf: {
            tx_power_dBm: rf.tx_power_dBm,
            freq_ghz: rf.freq_ghz,
            path_loss_exponent: rf.path_loss_exponent,
            noise_floor_dBm: rf.noise_floor_dBm,
            cca_threshold_dBm: rf.cca_threshold_dBm,
            channel_width_mhz: rf.channel_width_mhz,
            wifi_standard: rf.wifi_standard,
            shadow_fading_sigma: rf.shadow_fading_sigma,
            rts_cts: rf.rts_cts,
          },
        }),
      },
    };

    return yaml.dump({ scenario }, { lineWidth: 120, noRefs: true });
  }, [name, nodes, links, tasks, edges, scheduler, selectedScheduler, schedulerOptions, seed, routing, interference, interferenceRadius, rf]);

  const handleRun = async () => {
    const result = await run({ name, scenario_yaml: scenarioYaml });
    if (result && result.status !== 'error' && result.trace_jsonl && result.metrics_json) {
      onLoadResults(result.scenario_yaml, result.trace_jsonl, result.metrics_json);
    }
  };

  return (
    <div className="min-h-[80vh] p-8 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={onBack}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-text)] hover:bg-[var(--color-surface)] transition-colors"
        >
          <ArrowLeft size={16} />
          Back
        </button>
        <div>
          <h1 className="text-2xl font-bold">Configure & Run</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Build a scenario, run ncsim, and visualize results
          </p>
        </div>
      </div>

      <div className="space-y-8">
        {/* Basic config */}
        <section>
          <h3 className="text-base font-semibold mb-3">Basic Configuration</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Experiment name</span>
              <input
                type="text" value={name}
                onChange={(e) => setName(e.target.value)}
                className="input-field"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Scheduler</span>
              <select value={scheduler} onChange={(e) => handleSchedulerChange(e.target.value)} className="input-field">
                <optgroup label="SAGA static batch">
                  {schedulers.filter((entry) => entry.kind === 'saga').map((entry) => (
                    <option key={entry.name} value={entry.name}>{entry.label}</option>
                  ))}
                </optgroup>
                <optgroup label="Built in">
                  {schedulers.filter((entry) => entry.kind === 'builtin').map((entry) => (
                    <option key={entry.name} value={entry.name}>{entry.label}</option>
                  ))}
                </optgroup>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Routing</span>
              <select value={routing} onChange={(e) => setRouting(e.target.value)} className="input-field">
                <option value="direct">Direct</option>
                <option value="widest_path">Widest Path</option>
                <option value="shortest_path">Shortest Path</option>
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-[var(--color-text-secondary)]">Seed</span>
              <input
                type="number" value={seed}
                onChange={(e) => setSeed(Number(e.target.value))}
                className="input-field"
              />
            </label>
          </div>
          {selectedScheduler && selectedScheduler.options.length > 0 && (
            <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
              <h4 className="text-sm font-medium mb-3">{selectedScheduler.label} options</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {selectedScheduler.options.map((option) => (
                  <label key={option.name} className="flex flex-col gap-1">
                    <span className="text-xs text-[var(--color-text-secondary)]" title={option.description}>
                      {option.label}
                    </span>
                    {option.choices.length > 0 ? (
                      <select
                        value={String(schedulerOptions[option.name] ?? option.default ?? '')}
                        onChange={(event) => updateSchedulerOption(option, event.target.value)}
                        className="input-field"
                      >
                        {option.choices.map((choice) => (
                          <option key={String(choice)} value={String(choice)}>{String(choice)}</option>
                        ))}
                      </select>
                    ) : option.type === 'boolean' ? (
                      <select
                        value={String(schedulerOptions[option.name] ?? option.default)}
                        onChange={(event) => updateSchedulerOption(option, event.target.value)}
                        className="input-field"
                      >
                        <option value="true">Enabled</option>
                        <option value="false">Disabled</option>
                      </select>
                    ) : (
                      <input
                        type={option.type === 'string' ? 'text' : 'number'}
                        step={option.type === 'integer' ? 1 : 'any'}
                        min={option.minimum ?? undefined}
                        max={option.maximum ?? undefined}
                        value={String(schedulerOptions[option.name] ?? option.default ?? '')}
                        placeholder={option.nullable ? 'Default' : undefined}
                        onChange={(event) => updateSchedulerOption(option, event.target.value)}
                        className="input-field"
                        title={option.description}
                      />
                    )}
                  </label>
                ))}
              </div>
            </div>
          )}
          {scheduler === 'manual' && (
            <p className="text-xs text-[var(--color-text-secondary)] mt-2 italic">
              Assign each task to a node using the "Pinned To" column in the DAG Structure section below.
            </p>
          )}
        </section>

        <InterferenceSection
          interference={interference}
          interferenceRadius={interferenceRadius}
          rf={rf}
          onInterferenceChange={setInterference}
          onRadiusChange={setInterferenceRadius}
          onRfChange={setRf}
        />

        <TopologySection
          preset={topoPreset}
          params={topoParams}
          nodes={nodes}
          links={links}
          rfParams={rfParams}
          seed={seed}
          onPresetChange={setTopoPreset}
          onParamsChange={setTopoParams}
          onNodesChange={setNodes}
          onLinksChange={setLinks}
        />

        <DagSection
          preset={dagPreset}
          params={dagParams}
          tasks={tasks}
          edges={edges}
          nodes={nodes}
          scheduler={scheduler}
          onPresetChange={setDagPreset}
          onParamsChange={setDagParams}
          onTasksChange={setTasks}
          onEdgesChange={setEdges}
        />

        <YamlPreview yaml={scenarioYaml} />

        {/* Run button */}
        <div className="flex flex-col items-center gap-3 pt-4 border-t border-[var(--color-border)]">
          <button
            onClick={handleRun}
            disabled={running || nodes.length === 0 || tasks.length === 0}
            className="flex items-center gap-2 px-8 py-3 rounded-xl bg-[var(--color-accent)] text-[var(--color-bg)] font-semibold text-base hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {running ? (
              <><Loader2 size={20} className="animate-spin" /> Running...</>
            ) : (
              <><Play size={20} /> Run Experiment</>
            )}
          </button>

          {runError && (
            <div className="p-3 rounded-lg bg-red-500/10 border border-red-500/30 flex items-center gap-2 text-red-400 max-w-lg">
              <AlertCircle size={16} />
              <span className="text-sm">{runError}</span>
            </div>
          )}

          <p className="text-xs text-[var(--color-text-secondary)]">
            Results are saved under viz/public/sample-runs
          </p>
        </div>
      </div>
    </div>
  );
}
