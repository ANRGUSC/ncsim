import { Plus, Trash2 } from 'lucide-react';
import type { TaskDef, EdgeDef } from '../../types/scenario';
import type { DagPreset, DagParams } from './dagPresets';
import { generateDag } from './dagPresets';

const PRESETS: { value: DagPreset; label: string }[] = [
  { value: 'chain', label: 'Chain' },
  { value: 'fork_join', label: 'Fork-Join' },
  { value: 'diamond', label: 'Diamond' },
  { value: 'parallel', label: 'Parallel (independent)' },
  { value: 'custom', label: 'Custom' },
];

interface Props {
  preset: DagPreset;
  params: DagParams;
  tasks: TaskDef[];
  edges: EdgeDef[];
  onPresetChange: (preset: DagPreset) => void;
  onParamsChange: (params: DagParams) => void;
  onTasksChange: (tasks: TaskDef[]) => void;
  onEdgesChange: (edges: EdgeDef[]) => void;
}

export function DagSection({
  preset, params, tasks, edges,
  onPresetChange, onParamsChange, onTasksChange, onEdgesChange,
}: Props) {
  const handlePresetChange = (newPreset: DagPreset) => {
    onPresetChange(newPreset);
    if (newPreset !== 'custom') {
      const { tasks: t, edges: e } = generateDag(newPreset, params);
      onTasksChange(t);
      onEdgesChange(e);
    }
  };

  const handleParamChange = (key: keyof DagParams, value: number) => {
    const newParams = { ...params, [key]: value };
    onParamsChange(newParams);
    if (preset !== 'custom') {
      const { tasks: t, edges: e } = generateDag(preset, newParams);
      onTasksChange(t);
      onEdgesChange(e);
    }
  };

  const updateTask = (idx: number, field: keyof TaskDef, value: string | number) => {
    const updated = [...tasks];
    const task = { ...updated[idx] };
    if (field === 'compute_cost') task.compute_cost = Number(value);
    else if (field === 'id') task.id = String(value);
    else if (field === 'pinned_to') task.pinned_to = value ? String(value) : undefined;
    updated[idx] = task;
    onTasksChange(updated);
  };

  const addTask = () => {
    const id = `T${tasks.length}`;
    onTasksChange([...tasks, { id, compute_cost: params.defaultComputeCost }]);
  };

  const removeTask = (idx: number) => {
    onTasksChange(tasks.filter((_, i) => i !== idx));
  };

  const updateEdge = (idx: number, field: keyof EdgeDef, value: string | number) => {
    const updated = [...edges];
    const edge = { ...updated[idx] };
    if (field === 'data_size') edge.data_size = Number(value);
    else edge[field] = String(value);
    updated[idx] = edge;
    onEdgesChange(updated);
  };

  const addEdge = () => {
    const from = tasks.length > 0 ? tasks[0].id : 'T0';
    const to = tasks.length > 1 ? tasks[1].id : 'T1';
    onEdgesChange([...edges, { from, to, data_size: params.defaultDataSize }]);
  };

  const removeEdge = (idx: number) => {
    onEdgesChange(edges.filter((_, i) => i !== idx));
  };

  return (
    <section>
      <h3 className="text-base font-semibold mb-3">DAG Structure</h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Preset</span>
          <select
            value={preset}
            onChange={(e) => handlePresetChange(e.target.value as DagPreset)}
            className="input-field"
          >
            {PRESETS.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Task count</span>
          <input
            type="range"
            min={2} max={20} value={params.taskCount}
            onChange={(e) => handleParamChange('taskCount', Number(e.target.value))}
            className="mt-1"
          />
          <span className="text-xs text-center">{params.taskCount}</span>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Default cost (CU)</span>
          <input
            type="number" min={1} step={10} value={params.defaultComputeCost}
            onChange={(e) => handleParamChange('defaultComputeCost', Number(e.target.value))}
            className="input-field"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-[var(--color-text-secondary)]">Default data (MB)</span>
          <input
            type="number" min={0.1} step={10} value={params.defaultDataSize}
            onChange={(e) => handleParamChange('defaultDataSize', Number(e.target.value))}
            className="input-field"
          />
        </label>
      </div>

      {/* Tasks table */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">Tasks ({tasks.length})</span>
          <button onClick={addTask} className="btn-small"><Plus size={14} /> Add</button>
        </div>
        {tasks.length > 0 && (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th><th>Compute Cost</th><th>Pinned To</th><th></th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((t, i) => (
                  <tr key={i}>
                    <td><input value={t.id} onChange={(e) => updateTask(i, 'id', e.target.value)} className="input-cell" /></td>
                    <td><input type="number" value={t.compute_cost} onChange={(e) => updateTask(i, 'compute_cost', e.target.value)} className="input-cell" /></td>
                    <td><input value={t.pinned_to || ''} onChange={(e) => updateTask(i, 'pinned_to', e.target.value)} className="input-cell" placeholder="(none)" /></td>
                    <td><button onClick={() => removeTask(i)} className="text-red-400 hover:text-red-300 p-1"><Trash2 size={14} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edges table */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium">Edges ({edges.length})</span>
          <button onClick={addEdge} className="btn-small"><Plus size={14} /> Add</button>
        </div>
        {edges.length > 0 && (
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>From</th><th>To</th><th>Data Size (MB)</th><th></th>
                </tr>
              </thead>
              <tbody>
                {edges.map((e, i) => (
                  <tr key={i}>
                    <td><input value={e.from} onChange={(ev) => updateEdge(i, 'from', ev.target.value)} className="input-cell w-20" /></td>
                    <td><input value={e.to} onChange={(ev) => updateEdge(i, 'to', ev.target.value)} className="input-cell w-20" /></td>
                    <td><input type="number" value={e.data_size} onChange={(ev) => updateEdge(i, 'data_size', ev.target.value)} className="input-cell" /></td>
                    <td><button onClick={() => removeEdge(i)} className="text-red-400 hover:text-red-300 p-1"><Trash2 size={14} /></button></td>
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
