export interface Position {
  x: number;
  y: number;
}

export interface NodeDef {
  id: string;
  compute_capacity: number;
  position: Position;
}

export interface LinkDef {
  id: string;
  from: string;
  to: string;
  bandwidth: number;
  latency: number;
  derive_bandwidth?: boolean;
}

export interface NetworkDef {
  nodes: NodeDef[];
  links: LinkDef[];
}

export interface TaskDef {
  id: string;
  compute_cost: number;
  pinned_to?: string;
}

export interface EdgeDef {
  from: string;
  to: string;
  data_size: number;
}

export interface DagDef {
  id: string;
  inject_at: number;
  tasks: TaskDef[];
  edges: EdgeDef[];
}

export interface RFConfig {
  tx_power_dBm: number;
  freq_ghz: number;
  path_loss_exponent: number;
  noise_floor_dBm: number;
  cca_threshold_dBm: number;
  channel_width_mhz: number;
  wifi_standard: string;
  shadow_fading_sigma: number;
  rts_cts: boolean;
}

export interface ScenarioConfig {
  scheduler: string;
  scheduler_options?: Record<string, string | number | boolean | null>;
  seed: number;
  routing?: string;
  interference?: string;
  interference_radius?: number;
  rf?: Partial<RFConfig>;
}

export interface Scenario {
  name: string;
  network: NetworkDef;
  dags: DagDef[];
  config: ScenarioConfig;
}
