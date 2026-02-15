import type { NodeDef, LinkDef } from '../../types/scenario';

export type TopologyPreset = 'line' | 'ring' | 'star' | 'mesh' | 'grid' | 'custom';

export interface TopologyParams {
  nodeCount: number;
  defaultCapacity: number;
  defaultBandwidth: number;
  defaultLatency: number;
}

function makeNode(id: string, capacity: number, x: number, y: number): NodeDef {
  return { id, compute_capacity: capacity, position: { x, y } };
}

/** Generate a bidirectional link pair (a→b and b→a). */
function makeBiLink(a: string, b: string, bw: number, lat: number): LinkDef[] {
  return [
    { id: `l${a}_${b}`, from: a, to: b, bandwidth: bw, latency: lat },
    { id: `l${b}_${a}`, from: b, to: a, bandwidth: bw, latency: lat },
  ];
}

/** Line: n0 - n1 - n2 - ... */
export function generateLine(p: TopologyParams): { nodes: NodeDef[]; links: LinkDef[] } {
  const nodes: NodeDef[] = [];
  const links: LinkDef[] = [];
  const spacing = 10;

  for (let i = 0; i < p.nodeCount; i++) {
    nodes.push(makeNode(`n${i}`, p.defaultCapacity, i * spacing, 0));
  }
  for (let i = 0; i < p.nodeCount - 1; i++) {
    links.push(...makeBiLink(`n${i}`, `n${i + 1}`, p.defaultBandwidth, p.defaultLatency));
  }
  return { nodes, links };
}

/** Ring: n0 - n1 - ... - n(k-1) - n0 */
export function generateRing(p: TopologyParams): { nodes: NodeDef[]; links: LinkDef[] } {
  const nodes: NodeDef[] = [];
  const links: LinkDef[] = [];
  const radius = p.nodeCount * 3;

  for (let i = 0; i < p.nodeCount; i++) {
    const angle = (2 * Math.PI * i) / p.nodeCount - Math.PI / 2;
    const x = Math.round(radius * Math.cos(angle) * 10) / 10;
    const y = Math.round(radius * Math.sin(angle) * 10) / 10;
    nodes.push(makeNode(`n${i}`, p.defaultCapacity, x, y));
  }
  for (let i = 0; i < p.nodeCount; i++) {
    const j = (i + 1) % p.nodeCount;
    links.push(...makeBiLink(`n${i}`, `n${j}`, p.defaultBandwidth, p.defaultLatency));
  }
  return { nodes, links };
}

/** Star: n0 at center, n1..nk around it */
export function generateStar(p: TopologyParams): { nodes: NodeDef[]; links: LinkDef[] } {
  const nodes: NodeDef[] = [];
  const links: LinkDef[] = [];
  const radius = p.nodeCount * 3;

  nodes.push(makeNode('n0', p.defaultCapacity, 0, 0));

  for (let i = 1; i < p.nodeCount; i++) {
    const angle = (2 * Math.PI * (i - 1)) / (p.nodeCount - 1) - Math.PI / 2;
    const x = Math.round(radius * Math.cos(angle) * 10) / 10;
    const y = Math.round(radius * Math.sin(angle) * 10) / 10;
    nodes.push(makeNode(`n${i}`, p.defaultCapacity, x, y));
    links.push(...makeBiLink('n0', `n${i}`, p.defaultBandwidth, p.defaultLatency));
  }
  return { nodes, links };
}

/** Mesh: fully connected */
export function generateMesh(p: TopologyParams): { nodes: NodeDef[]; links: LinkDef[] } {
  const nodes: NodeDef[] = [];
  const links: LinkDef[] = [];
  const radius = p.nodeCount * 3;

  for (let i = 0; i < p.nodeCount; i++) {
    const angle = (2 * Math.PI * i) / p.nodeCount - Math.PI / 2;
    const x = Math.round(radius * Math.cos(angle) * 10) / 10;
    const y = Math.round(radius * Math.sin(angle) * 10) / 10;
    nodes.push(makeNode(`n${i}`, p.defaultCapacity, x, y));
  }
  for (let i = 0; i < p.nodeCount; i++) {
    for (let j = i + 1; j < p.nodeCount; j++) {
      links.push(...makeBiLink(`n${i}`, `n${j}`, p.defaultBandwidth, p.defaultLatency));
    }
  }
  return { nodes, links };
}

/** Grid: rows x cols arrangement */
export function generateGrid(p: TopologyParams): { nodes: NodeDef[]; links: LinkDef[] } {
  const nodes: NodeDef[] = [];
  const links: LinkDef[] = [];
  const cols = Math.ceil(Math.sqrt(p.nodeCount));
  const spacing = 10;

  let idx = 0;
  for (let r = 0; idx < p.nodeCount; r++) {
    for (let c = 0; c < cols && idx < p.nodeCount; c++, idx++) {
      nodes.push(makeNode(`n${idx}`, p.defaultCapacity, c * spacing, r * spacing));
    }
  }

  for (let i = 0; i < nodes.length; i++) {
    const row = Math.floor(i / cols);
    const col = i % cols;
    // Right neighbor
    if (col + 1 < cols && i + 1 < nodes.length && Math.floor((i + 1) / cols) === row) {
      links.push(...makeBiLink(`n${i}`, `n${i + 1}`, p.defaultBandwidth, p.defaultLatency));
    }
    // Down neighbor
    if (i + cols < nodes.length) {
      links.push(...makeBiLink(`n${i}`, `n${i + cols}`, p.defaultBandwidth, p.defaultLatency));
    }
  }
  return { nodes, links };
}

export function generateTopology(preset: TopologyPreset, params: TopologyParams): { nodes: NodeDef[]; links: LinkDef[] } {
  switch (preset) {
    case 'line': return generateLine(params);
    case 'ring': return generateRing(params);
    case 'star': return generateStar(params);
    case 'mesh': return generateMesh(params);
    case 'grid': return generateGrid(params);
    case 'custom': return { nodes: [], links: [] };
  }
}
