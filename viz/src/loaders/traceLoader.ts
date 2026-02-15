import type { TraceEvent } from '../types/trace';

export function parseTrace(jsonlText: string): TraceEvent[] {
  const lines = jsonlText.trim().split('\n');
  const events: TraceEvent[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    try {
      events.push(JSON.parse(line) as TraceEvent);
    } catch {
      throw new Error(`Invalid JSON on trace line ${i + 1}: ${line.slice(0, 80)}`);
    }
  }
  if (events.length === 0) {
    throw new Error('Trace file is empty');
  }
  if (events[0].type !== 'sim_start') {
    throw new Error('Trace must start with sim_start event');
  }
  return events;
}
