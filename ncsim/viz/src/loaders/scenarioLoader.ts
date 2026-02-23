import yaml from 'js-yaml';
import type { Scenario } from '../types/scenario';

/* eslint-disable @typescript-eslint/no-explicit-any */
export function parseScenario(yamlText: string): Scenario {
  const raw = yaml.load(yamlText) as any;
  if (!raw?.scenario) {
    throw new Error('Invalid scenario YAML: missing top-level "scenario" key');
  }
  const s = raw.scenario;

  const network = s.network;
  if (!network?.nodes || !network?.links) {
    throw new Error('Invalid scenario: missing network.nodes or network.links');
  }

  const dags = s.dags;
  if (!Array.isArray(dags) || dags.length === 0) {
    throw new Error('Invalid scenario: missing or empty dags array');
  }

  const config = s.config ?? {};

  return {
    name: s.name ?? 'Unnamed Scenario',
    network: {
      nodes: network.nodes.map((n: any) => ({
        id: n.id as string,
        compute_capacity: n.compute_capacity as number,
        position: n.position ?? { x: 0, y: 0 },
      })),
      links: network.links.map((l: any) => ({
        id: l.id as string,
        from: l.from as string,
        to: l.to as string,
        bandwidth: l.bandwidth ?? 100,
        latency: l.latency ?? 0.001,
      })),
    },
    dags: dags.map((d: any) => ({
      id: d.id as string,
      inject_at: d.inject_at ?? 0,
      tasks: (d.tasks ?? []).map((t: any) => ({
        id: t.id as string,
        compute_cost: t.compute_cost as number,
        pinned_to: t.pinned_to as string | undefined,
      })),
      edges: (d.edges ?? []).map((e: any) => ({
        from: e.from as string,
        to: e.to as string,
        data_size: e.data_size as number,
      })),
    })),
    config: {
      scheduler: config.scheduler ?? 'heft',
      seed: config.seed ?? 42,
      routing: config.routing,
      interference: config.interference,
      interference_radius: config.interference_radius,
      rf: config.rf,
    },
  };
}
