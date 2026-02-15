import { useState, useCallback } from 'react';
import type { Scenario } from '../types/scenario';
import type { TraceEvent } from '../types/trace';
import type { MetricsData } from '../types/metrics';
import { parseScenario, parseTrace, parseMetrics } from '../loaders';

export interface SimulationData {
  scenario: Scenario;
  trace: TraceEvent[];
  metrics: MetricsData;
}

export function useSimulation() {
  const [data, setData] = useState<SimulationData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const loadFiles = useCallback(async (files: FileList | File[]) => {
    setLoading(true);
    setError(null);
    try {
      let scenarioText: string | null = null;
      let traceText: string | null = null;
      let metricsText: string | null = null;

      for (const file of files) {
        const text = await file.text();
        const name = file.name.toLowerCase();
        if (name.endsWith('.yaml') || name.endsWith('.yml')) {
          scenarioText = text;
        } else if (name.endsWith('.jsonl') || name.includes('trace')) {
          traceText = text;
        } else if (name.endsWith('.json') && (name.includes('metric') || name.includes('result'))) {
          metricsText = text;
        } else if (name.endsWith('.json')) {
          metricsText = text;
        }
      }

      if (!scenarioText) throw new Error('Missing scenario YAML file (.yaml/.yml)');
      if (!traceText) throw new Error('Missing trace file (.jsonl)');
      if (!metricsText) throw new Error('Missing metrics file (.json)');

      const scenario = parseScenario(scenarioText);
      const trace = parseTrace(traceText);
      const metrics = parseMetrics(metricsText);

      setData({ scenario, trace, metrics });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error loading files');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadFromTexts = useCallback(
    (scenarioText: string, traceText: string, metricsText: string) => {
      setLoading(true);
      setError(null);
      try {
        const scenario = parseScenario(scenarioText);
        const trace = parseTrace(traceText);
        const metrics = parseMetrics(metricsText);
        setData({ scenario, trace, metrics });
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error parsing data');
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const clear = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return { data, error, loading, loadFiles, loadFromTexts, clear };
}
