import { useMemo, useEffect, useCallback, useState } from 'react';
import type { Scenario } from '../../types/scenario';
import type { TraceEvent } from '../../types/trace';
import type { MetricsData } from '../../types/metrics';
import { usePlayback } from '../../hooks/usePlayback';
import { deriveState } from '../../engine/SimulationState';
import { NetworkView } from '../network/NetworkView';
import { GanttChart } from '../gantt/GanttChart';
import { TimelineControls } from './TimelineControls';
import { EventLog } from './EventLog';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface Props {
  scenario: Scenario;
  trace: TraceEvent[];
  metrics: MetricsData;
}

export function SimulationView({ scenario, trace, metrics }: Props) {
  const playback = usePlayback(trace, metrics.makespan);
  const [showLog, setShowLog] = useState(true);

  const simState = useMemo(
    () => deriveState(trace, playback.currentTime),
    [trace, playback.currentTime]
  );

  // Keyboard shortcuts for playback
  const handleKey = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      switch (e.key) {
        case ' ':
          e.preventDefault();
          playback.togglePlay();
          break;
        case 'ArrowRight':
          e.preventDefault();
          if (e.shiftKey) playback.seek(playback.currentTime + metrics.makespan * 0.1);
          else playback.stepForward();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          if (e.shiftKey) playback.seek(playback.currentTime - metrics.makespan * 0.1);
          else playback.stepBackward();
          break;
        case 'Home':
          playback.seek(0);
          break;
        case 'End':
          playback.seek(metrics.makespan);
          break;
        case '=':
        case '+':
          playback.speedUp();
          break;
        case '-':
          playback.speedDown();
          break;
      }
    },
    [playback, metrics.makespan]
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleKey]);

  // Summary of active state for legend
  const runningNodes = useMemo(() => {
    const items: Array<{ nodeId: string; task: string }> = [];
    for (const [id, ns] of simState.nodes) {
      if (ns.status === 'running' && ns.currentTask) {
        items.push({ nodeId: id, task: ns.currentTask });
      }
    }
    return items;
  }, [simState]);

  const activeTransfers = useMemo(() => {
    const items: Array<{ linkId: string; from: string; to: string }> = [];
    for (const [id, ls] of simState.links) {
      for (const t of ls.activeTransfers) {
        items.push({ linkId: id, from: t.fromTask, to: t.toTask });
      }
    }
    return items;
  }, [simState]);

  return (
    <div className="flex flex-col h-full">
      {/* Main content: network + gantt */}
      <div className="flex-1 flex min-h-0">
        {/* Network view (left 55%) */}
        <div className="w-[55%] border-r border-[var(--color-border)] relative">
          <NetworkView
            scenario={scenario}
            metrics={metrics}
            simState={simState}
          />
          {/* Live status legend */}
          <div className="absolute bottom-2 left-2 text-xs space-y-1 pointer-events-none">
            {runningNodes.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {runningNodes.map((r) => (
                  <span key={r.nodeId} className="px-2 py-1 rounded-md font-bold bg-[var(--color-accent-yellow)]/25 border border-[var(--color-accent-yellow)]/60 text-[var(--color-accent-yellow)]">
                    {r.nodeId}: {r.task}
                  </span>
                ))}
              </div>
            )}
            {activeTransfers.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {activeTransfers.map((t, i) => (
                  <span key={i} className="px-2 py-1 rounded-md font-bold bg-[var(--color-accent-magenta)]/20 border border-[var(--color-accent-magenta)]/50 text-[var(--color-accent-magenta)]">
                    {t.from}→{t.to}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right side: gantt + event log */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Gantt chart */}
          <div className="flex-1 min-h-[200px] overflow-auto">
            <GanttChart
              trace={trace}
              scenario={scenario}
              metrics={metrics}
              currentTime={playback.currentTime}
              maxTime={metrics.makespan}
            />
          </div>

          {/* Event log (collapsible) */}
          <div className="border-t border-[var(--color-border)]">
            <button
              onClick={() => setShowLog(!showLog)}
              className="w-full flex items-center justify-between px-3 py-1 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-border)]/50"
            >
              <span>Event Log ({simState.eventsProcessed} / {trace.length})</span>
              {showLog ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
            </button>
            {showLog && (
              <div className="h-48 border-t border-[var(--color-border)]">
                <EventLog
                  trace={trace}
                  currentIndex={playback.eventIndex}
                  onJump={playback.seek}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Timeline controls */}
      <TimelineControls
        currentTime={playback.currentTime}
        makespan={metrics.makespan}
        playing={playback.playing}
        speed={playback.speed}
        eventIndex={playback.eventIndex}
        totalEvents={trace.length}
        onTogglePlay={playback.togglePlay}
        onSeek={playback.seek}
        onStepForward={playback.stepForward}
        onStepBackward={playback.stepBackward}
        onSpeedUp={playback.speedUp}
        onSpeedDown={playback.speedDown}
        onSetSpeed={playback.setSpeed}
      />
    </div>
  );
}
