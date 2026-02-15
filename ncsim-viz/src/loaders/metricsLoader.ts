import type { MetricsData } from '../types/metrics';

export function parseMetrics(jsonText: string): MetricsData {
  const data = JSON.parse(jsonText) as MetricsData;
  if (typeof data.makespan !== 'number') {
    throw new Error('Invalid metrics: missing makespan');
  }
  return data;
}
