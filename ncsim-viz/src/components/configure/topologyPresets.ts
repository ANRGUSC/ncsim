import type { NodeDef, LinkDef } from '../../types/scenario';

export type TopologyPreset = 'line' | 'ring' | 'star' | 'mesh' | 'grid' | 'random' | 'custom';

/** Subset of RF params needed for radio range calculation. */
export interface RFParams {
  tx_power_dBm: number;
  freq_ghz: number;
  path_loss_exponent: number;
  noise_floor_dBm: number;
}

/** Friis free-space path loss at reference distance d0: PL(d0) = 20*log10(4*pi*d0*f/c) */
function friisReferenceLoss(freq_ghz: number, d0: number = 1.0): number {
  const freq_hz = freq_ghz * 1e9;
  const c = 3e8;
  return 20 * Math.log10(4 * Math.PI * d0 * freq_hz / c);
}

/**
 * Maximum distance at which minimum SNR (5 dB) is met.
 * Port of ncsim/ncsim/models/wifi.py:communication_range()
 */
export function computeRadioRange(rf: RFParams, minSnrDB: number = 5.0, d0: number = 1.0): number {
  const pl_d0 = friisReferenceLoss(rf.freq_ghz, d0);
  const maxPathLoss = rf.tx_power_dBm - rf.noise_floor_dBm - minSnrDB;
  if (maxPathLoss <= pl_d0) return d0;
  const exponent = (maxPathLoss - pl_d0) / (10 * rf.path_loss_exponent);
  return d0 * (10 ** exponent);
}

/** Mulberry32 seeded PRNG — returns a function that yields [0, 1) on each call. */
function mulberry32(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s = (s + 0x6D2B79F5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

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

/** Random: nodes placed randomly, links between pairs within radio range. */
export function generateRandom(
  p: TopologyParams,
  rfParams: RFParams,
  seed: number,
): { nodes: NodeDef[]; links: LinkDef[] } {
  const nodes: NodeDef[] = [];
  const links: LinkDef[] = [];
  const range = computeRadioRange(rfParams);
  const areaSize = 2 * range;
  const rand = mulberry32(seed);

  for (let i = 0; i < p.nodeCount; i++) {
    const x = Math.round(rand() * areaSize * 10) / 10;
    const y = Math.round(rand() * areaSize * 10) / 10;
    nodes.push(makeNode(`n${i}`, p.defaultCapacity, x, y));
  }

  for (let i = 0; i < p.nodeCount; i++) {
    for (let j = i + 1; j < p.nodeCount; j++) {
      const dx = nodes[i].position.x - nodes[j].position.x;
      const dy = nodes[i].position.y - nodes[j].position.y;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist <= range) {
        links.push(...makeBiLink(`n${i}`, `n${j}`, p.defaultBandwidth, p.defaultLatency));
      }
    }
  }
  return { nodes, links };
}

export function generateTopology(
  preset: TopologyPreset,
  params: TopologyParams,
  rfParams?: RFParams,
  seed?: number,
): { nodes: NodeDef[]; links: LinkDef[] } {
  switch (preset) {
    case 'line': return generateLine(params);
    case 'ring': return generateRing(params);
    case 'star': return generateStar(params);
    case 'mesh': return generateMesh(params);
    case 'grid': return generateGrid(params);
    case 'random': return generateRandom(params, rfParams!, seed ?? 42);
    case 'custom': return { nodes: [], links: [] };
  }
}
