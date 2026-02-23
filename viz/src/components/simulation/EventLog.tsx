import { useRef, useEffect } from 'react';
import type { TraceEvent } from '../../types/trace';

interface Props {
  trace: TraceEvent[];
  currentIndex: number;
  onJump: (time: number) => void;
}

const EVENT_COLORS: Record<string, string> = {
  sim_start: 'text-[var(--color-text-secondary)]',
  sim_end: 'text-[var(--color-text-secondary)]',
  dag_inject: 'text-[var(--color-accent-yellow)]',
  task_scheduled: 'text-[var(--color-text-secondary)]',
  task_start: 'text-[var(--color-accent-green)]',
  task_complete: 'text-[var(--color-accent)]',
  transfer_start: 'text-[var(--color-accent-magenta)]',
  transfer_complete: 'text-[var(--color-accent-magenta)]',
};

function eventSummary(e: TraceEvent): string {
  switch (e.type) {
    case 'sim_start': return 'Simulation started';
    case 'sim_end': return `Simulation ended (${e.status})`;
    case 'dag_inject': return `DAG ${e.dag_id} injected (${e.task_ids.length} tasks)`;
    case 'task_scheduled': return `${e.task_id} → ${e.node_id}`;
    case 'task_start': return `${e.task_id} started on ${e.node_id}`;
    case 'task_complete': return `${e.task_id} done (${e.duration.toFixed(3)}s)`;
    case 'transfer_start': return `${e.from_task}→${e.to_task} (${e.data_size} MB)`;
    case 'transfer_complete': return `${e.from_task}→${e.to_task} done (${e.duration.toFixed(3)}s)`;
    default: return (e as TraceEvent).type;
  }
}

export function EventLog({ trace, currentIndex, onJump }: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [currentIndex]);

  return (
    <div ref={listRef} className="h-full overflow-auto text-xs font-mono">
      {trace.map((e, i) => (
        <div
          key={e.seq}
          ref={i === currentIndex ? activeRef : null}
          onClick={() => onJump(e.sim_time)}
          className={`flex items-center gap-2 px-3 py-1 cursor-pointer transition-colors ${
            i === currentIndex
              ? 'bg-[var(--color-accent)]/15 border-l-2 border-[var(--color-accent)]'
              : i <= currentIndex
              ? 'hover:bg-[var(--color-border)]/50'
              : 'opacity-40 hover:opacity-70'
          }`}
        >
          <span className="w-8 text-right text-[var(--color-text-secondary)]">{e.seq}</span>
          <span className="w-16 text-right text-[var(--color-text-secondary)]">{e.sim_time.toFixed(3)}s</span>
          <span className={`w-32 ${EVENT_COLORS[e.type] ?? ''}`}>{e.type}</span>
          <span className="flex-1 truncate">{eventSummary(e)}</span>
        </div>
      ))}
    </div>
  );
}
