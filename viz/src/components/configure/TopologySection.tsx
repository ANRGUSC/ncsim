import { Plus, Trash2 } from 'lucide-react';
import type { NodeDef, LinkDef } from '../../types/scenario';
import type { TopologyPreset, TopologyParams, RFParams } from './topologyPresets';
import { generateTopology, computeRadioRange } from './topologyPresets';

const PRESETS: { value: TopologyPreset; label: string }[] = [
  { value: 'line', label: 'Line' },
  { value: 'ring', label: 'Ring' },
  { value: 'star', label: 'Star' },
  { value: 'mesh', label: 'Mesh (fully connected)' },
  { value: 'grid', label: 'Grid' },
  { value: 'random', label: 'Random (radio-range)' },
  { value: 'custom', label: 'Custom' },
];

interface Props {
  preset: TopologyPreset;
  params: TopologyParams;
  nodes: NodeDef[];
  links: LinkDef[];
  rfParams?: RFParams;
  seed?: number;
  deriveWirelessRates?: boolean;
  onPresetChange: (preset: TopologyPreset) => void;
  onParamsChange: (params: TopologyParams) => void;
  onNodesChange: (nodes: NodeDef[]) => void;
  onLinksChange: (links: LinkDef[]) => void;
}

export function TopologySection({
  preset, params, nodes, links, rfParams, seed, deriveWirelessRates = false,
  onPresetChange, onParamsChange, onNodesChange, onLinksChange,
}: Props) {
  const handlePresetChange = (newPreset: TopologyPreset) => {
    onPresetChange(newPreset);
    if (newPreset !== 'custom') {
      const { nodes: n, links: l } = generateTopology(newPreset, params, rfParams, seed);
      onNodesChange(n);
      onLinksChange(l);
    }
  };

  const handleParamChange = (key: keyof TopologyParams, value: number) => {
    const newParams = { ...params, [key]: value };
    onParamsChange(newParams);
    if (preset !== 'custom') {
      const { nodes: n, links: l } = generateTopology(preset, newParams, rfParams, seed);
      onNodesChange(n);
      onLinksChange(l);
    }
  };

  const radioRange = rfParams ? computeRadioRange(rfParams) : undefined;

  const updateNode = (idx: number, field: keyof NodeDef | 'x' | 'y', value: string | number) => {
    const updated = [...nodes];
    const node = { ...updated[idx] };
    if (field === 'x') node.position = { ...node.position, x: Number(value) };
    else if (field === 'y') node.position = { ...node.position, y: Number(value) };
    else if (field === 'compute_capacity') node.compute_capacity = Number(value);
    else if (field === 'id') node.id = String(value);
    updated[idx] = node;
    onNodesChange(updated);
  };

  const addNode = () => {
    const id = `n${nodes.length}`;
    onNodesChange([...nodes, { id, compute_capacity: params.defaultCapacity, position: { x: 0, y: 0 } }]);
  };

  const removeNode = (idx: number) => {
    onNodesChange(nodes.filter((_, i) => i !== idx));
  };

  const updateLink = (
    idx: number,
    field: Exclude<keyof LinkDef, 'derive_bandwidth'>,
    value: string | number,
  ) => {
    const updated = [...links];
    const link = { ...updated[idx] };
    if (field === 'bandwidth' || field === 'latency') link[field] = Number(value);
    else link[field] = String(value);
    updated[idx] = link;
    onLinksChange(updated);
  };

  const updateBandwidthMode = (idx: number, deriveBandwidth: boolean) => {
    const updated = [...links];
    updated[idx] = { ...updated[idx], derive_bandwidth: deriveBandwidth };
    onLinksChange(updated);
  };

  const addLink = () => {
    const id = `l${links.length}`;
    const from = nodes.length > 0 ? nodes[0].id : 'n0';
    const to = nodes.length > 1 ? nodes[1].id : 'n1';
    onLinksChange([...links, { id, from, to, bandwidth: params.defaultBandwidth, latency: params.defaultLatency }]);
  };

  const removeLink = (idx: number) => {
    onLinksChange(links.filter((_, i) => i !== idx));
  };

  return (
    <section>
      <h3 className="text-base font-semibold mb-3">Network Topology</h3>

      {preset === 'random' && radioRange !== undefined && (
        <p className="text-xs text-[var(--color-text-secondary)] mb-3 italic">
          Links auto-generated between nodes within radio range ({radioRange.toFixed(1)} m, from PHY config above).
        </p>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Preset</span>
          <select
            value={preset}
            onChange={(e) => handlePresetChange(e.target.value as TopologyPreset)}
            className="input-field"
          >
            {PRESETS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Node count</span>
          <input
            type="range"
            min={2} max={20} value={params.nodeCount}
            onChange={(e) => handleParamChange('nodeCount', Number(e.target.value))}
            className="mt-1"
          />
          <span className="text-xs text-center">{params.nodeCount}</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Default capacity</span>
          <input
            type="number" min={1} step={10} value={params.defaultCapacity}
            onChange={(e) => handleParamChange('defaultCapacity', Number(e.target.value))}
            className="input-field"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Default bandwidth</span>
          <input
            type="number" min={0.1} step={10} value={params.defaultBandwidth}
            onChange={(e) => handleParamChange('defaultBandwidth', Number(e.target.value))}
            className="input-field"
          />
        </label>
      </div>

      {/* Nodes table */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">Nodes ({nodes.length})</span>
          <button onClick={addNode} className="btn-small"><Plus size={14} /> Add</button>
        </div>
        {nodes.length > 0 && (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th><th>Capacity</th><th>X</th><th>Y</th><th></th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((n, i) => (
                  <tr key={i}>
                    <td><input value={n.id} onChange={(e) => updateNode(i, 'id', e.target.value)} className="input-cell" /></td>
                    <td><input type="number" value={n.compute_capacity} onChange={(e) => updateNode(i, 'compute_capacity', e.target.value)} className="input-cell" /></td>
                    <td><input type="number" value={n.position.x} onChange={(e) => updateNode(i, 'x', e.target.value)} className="input-cell w-16" /></td>
                    <td><input type="number" value={n.position.y} onChange={(e) => updateNode(i, 'y', e.target.value)} className="input-cell w-16" /></td>
                    <td><button onClick={() => removeNode(i)} className="text-red-400 hover:text-red-300 p-1"><Trash2 size={14} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Links table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">Links ({links.length})</span>
          <button onClick={addLink} className="btn-small"><Plus size={14} /> Add</button>
        </div>
        {links.length > 0 && (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th><th>From</th><th>To</th><th>Rate source</th><th>BW (MB/s)</th><th>Latency (s)</th><th></th>
                </tr>
              </thead>
              <tbody>
                {links.map((l, i) => (
                  <tr key={i}>
                    <td><input value={l.id} onChange={(e) => updateLink(i, 'id', e.target.value)} className="input-cell" /></td>
                    <td><input value={l.from} onChange={(e) => updateLink(i, 'from', e.target.value)} className="input-cell w-16" /></td>
                    <td><input value={l.to} onChange={(e) => updateLink(i, 'to', e.target.value)} className="input-cell w-16" /></td>
                    <td>
                      <select
                        value={l.derive_bandwidth ? 'auto' : 'fixed'}
                        onChange={(e) => updateBandwidthMode(i, e.target.value === 'auto')}
                        className="input-cell"
                      >
                        <option value="auto">
                          {deriveWirelessRates ? 'Auto (RF)' : 'Auto (default)'}
                        </option>
                        <option value="fixed">Fixed</option>
                      </select>
                    </td>
                    <td>
                      <input
                        type="number"
                        value={l.derive_bandwidth ? '' : l.bandwidth}
                        placeholder={deriveWirelessRates ? 'RF-derived' : `Default ${l.bandwidth}`}
                        disabled={l.derive_bandwidth}
                        onChange={(e) => updateLink(i, 'bandwidth', e.target.value)}
                        className="input-cell disabled:opacity-70"
                      />
                    </td>
                    <td><input type="number" step={0.001} value={l.latency} onChange={(e) => updateLink(i, 'latency', e.target.value)} className="input-cell" /></td>
                    <td><button onClick={() => removeLink(i)} className="text-red-400 hover:text-red-300 p-1"><Trash2 size={14} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
