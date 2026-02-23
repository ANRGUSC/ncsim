import { useState, useCallback } from 'react';
import type { RunRequest, RunResponse } from '../types/api';

export function useRunExperiment() {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResponse | null>(null);

  const run = useCallback(async (req: RunRequest): Promise<RunResponse | null> => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }
      const data: RunResponse = await res.json();
      setResult(data);
      if (data.error) {
        setError(data.error);
      }
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to run experiment';
      setError(msg);
      return null;
    } finally {
      setRunning(false);
    }
  }, []);

  const reset = useCallback(() => {
    setRunning(false);
    setError(null);
    setResult(null);
  }, []);

  return { run, running, error, result, reset };
}
