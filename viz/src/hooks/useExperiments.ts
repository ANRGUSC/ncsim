import { useState, useEffect, useCallback } from 'react';
import type { ExperimentSummary } from '../types/api';

export function useExperiments() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/experiments');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ExperimentSummary[] = await res.json();
      setExperiments(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch experiments');
      setExperiments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return { experiments, loading, error, refresh };
}
