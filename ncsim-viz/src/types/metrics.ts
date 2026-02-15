export interface MetricsData {
  scenario: string;
  seed: number;
  makespan: number;
  total_tasks: number;
  total_transfers: number;
  total_events: number;
  status: string;
  node_utilization: Record<string, number>;
  link_utilization: Record<string, number>;
  error_message?: string;
  // WiFi/interference fields (top-level in metrics JSON)
  rf_config?: Record<string, unknown>;
  carrier_sensing_range_m?: number;
  link_phy_rates_MBps?: Record<string, number>;
  max_clique_sizes?: Record<string, number>;
}
