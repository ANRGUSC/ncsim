import type { TaskDef, EdgeDef } from '../../types/scenario';

export type DagPreset = 'chain' | 'fork_join' | 'diamond' | 'parallel' | 'custom';

export interface DagParams {
  taskCount: number;
  defaultComputeCost: number;
  defaultDataSize: number;
}

function makeTask(id: string, cost: number): TaskDef {
  return { id, compute_cost: cost };
}

function makeEdge(from: string, to: string, size: number): EdgeDef {
  return { from, to, data_size: size };
}

/** Chain: T0 → T1 → T2 → ... */
export function generateChain(p: DagParams): { tasks: TaskDef[]; edges: EdgeDef[] } {
  const tasks: TaskDef[] = [];
  const edges: EdgeDef[] = [];

  for (let i = 0; i < p.taskCount; i++) {
    tasks.push(makeTask(`T${i}`, p.defaultComputeCost));
  }
  for (let i = 0; i < p.taskCount - 1; i++) {
    edges.push(makeEdge(`T${i}`, `T${i + 1}`, p.defaultDataSize));
  }
  return { tasks, edges };
}

/** Fork-Join: T0 fans out to T1..T(k-2), all converge to T(k-1) */
export function generateForkJoin(p: DagParams): { tasks: TaskDef[]; edges: EdgeDef[] } {
  const tasks: TaskDef[] = [];
  const edges: EdgeDef[] = [];

  if (p.taskCount < 3) return generateChain(p);

  const middleCount = p.taskCount - 2;

  tasks.push(makeTask('T0', p.defaultComputeCost));
  for (let i = 1; i <= middleCount; i++) {
    tasks.push(makeTask(`T${i}`, p.defaultComputeCost));
    edges.push(makeEdge('T0', `T${i}`, p.defaultDataSize));
  }
  const sinkId = `T${middleCount + 1}`;
  tasks.push(makeTask(sinkId, p.defaultComputeCost));
  for (let i = 1; i <= middleCount; i++) {
    edges.push(makeEdge(`T${i}`, sinkId, p.defaultDataSize));
  }
  return { tasks, edges };
}

/** Diamond: T0 → T1, T2 → T3 (classic diamond shape, extended for more tasks) */
export function generateDiamond(p: DagParams): { tasks: TaskDef[]; edges: EdgeDef[] } {
  const tasks: TaskDef[] = [];
  const edges: EdgeDef[] = [];

  if (p.taskCount < 4) return generateChain(p);

  // Split into layers: source(1), layer1(half), layer2(rest), sink(1)
  const innerCount = p.taskCount - 2;
  const layer1Count = Math.ceil(innerCount / 2);
  const layer2Count = innerCount - layer1Count;

  tasks.push(makeTask('T0', p.defaultComputeCost));

  let idx = 1;
  const layer1Ids: string[] = [];
  for (let i = 0; i < layer1Count; i++, idx++) {
    const id = `T${idx}`;
    tasks.push(makeTask(id, p.defaultComputeCost));
    edges.push(makeEdge('T0', id, p.defaultDataSize));
    layer1Ids.push(id);
  }

  const layer2Ids: string[] = [];
  if (layer2Count > 0) {
    for (let i = 0; i < layer2Count; i++, idx++) {
      const id = `T${idx}`;
      tasks.push(makeTask(id, p.defaultComputeCost));
      // Connect each layer2 node to all layer1 nodes
      for (const l1 of layer1Ids) {
        edges.push(makeEdge(l1, id, p.defaultDataSize));
      }
      layer2Ids.push(id);
    }
  }

  const sinkId = `T${idx}`;
  tasks.push(makeTask(sinkId, p.defaultComputeCost));
  const lastLayer = layer2Ids.length > 0 ? layer2Ids : layer1Ids;
  for (const id of lastLayer) {
    edges.push(makeEdge(id, sinkId, p.defaultDataSize));
  }

  return { tasks, edges };
}

/** Parallel: all tasks are independent (no edges) */
export function generateParallel(p: DagParams): { tasks: TaskDef[]; edges: EdgeDef[] } {
  const tasks: TaskDef[] = [];
  for (let i = 0; i < p.taskCount; i++) {
    tasks.push(makeTask(`T${i}`, p.defaultComputeCost));
  }
  return { tasks, edges: [] };
}

export function generateDag(preset: DagPreset, params: DagParams): { tasks: TaskDef[]; edges: EdgeDef[] } {
  switch (preset) {
    case 'chain': return generateChain(params);
    case 'fork_join': return generateForkJoin(params);
    case 'diamond': return generateDiamond(params);
    case 'parallel': return generateParallel(params);
    case 'custom': return { tasks: [], edges: [] };
  }
}
