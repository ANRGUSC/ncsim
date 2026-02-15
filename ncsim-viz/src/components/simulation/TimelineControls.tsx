import { Play, Pause, SkipBack, SkipForward, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface Props {
  currentTime: number;
  makespan: number;
  playing: boolean;
  speed: number;
  eventIndex: number;
  totalEvents: number;
  onTogglePlay: () => void;
  onSeek: (time: number) => void;
  onStepForward: () => void;
  onStepBackward: () => void;
  onSpeedUp: () => void;
  onSpeedDown: () => void;
  onSetSpeed: (speed: number) => void;
}

const SPEED_OPTIONS = [0.25, 0.5, 1, 2, 5, 10];

export function TimelineControls({
  currentTime, makespan, playing, speed,
  eventIndex, totalEvents,
  onTogglePlay, onSeek, onStepForward, onStepBackward,
  onSpeedUp, onSpeedDown, onSetSpeed,
}: Props) {
  return (
    <div className="border-t border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-2">
      {/* Scrubber */}
      <div className="mb-2">
        <input
          type="range"
          min={0}
          max={makespan}
          step={makespan / 1000}
          value={currentTime}
          onChange={(e) => onSeek(parseFloat(e.target.value))}
          className="w-full h-2 rounded-full appearance-none cursor-pointer accent-[var(--color-accent)]"
          style={{
            background: `linear-gradient(to right, var(--color-accent) ${(currentTime / makespan) * 100}%, var(--color-border) ${(currentTime / makespan) * 100}%)`,
          }}
        />
      </div>

      <div className="flex items-center justify-between">
        {/* Transport controls */}
        <div className="flex items-center gap-1">
          <button onClick={() => onSeek(0)} className="p-1.5 rounded hover:bg-[var(--color-border)]" title="Jump to start (Home)">
            <ChevronsLeft size={16} />
          </button>
          <button onClick={onStepBackward} className="p-1.5 rounded hover:bg-[var(--color-border)]" title="Step backward (Left)">
            <SkipBack size={16} />
          </button>
          <button
            onClick={onTogglePlay}
            className="p-2 rounded-lg bg-[var(--color-accent)] text-[var(--color-bg)] hover:opacity-90"
            title="Play/Pause (Space)"
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <button onClick={onStepForward} className="p-1.5 rounded hover:bg-[var(--color-border)]" title="Step forward (Right)">
            <SkipForward size={16} />
          </button>
          <button onClick={() => onSeek(makespan)} className="p-1.5 rounded hover:bg-[var(--color-border)]" title="Jump to end (End)">
            <ChevronsRight size={16} />
          </button>
        </div>

        {/* Time display */}
        <div className="text-sm font-mono text-[var(--color-text-secondary)]">
          <span className="text-[var(--color-text)]">{currentTime.toFixed(3)}s</span>
          {' / '}
          {makespan.toFixed(3)}s
          <span className="ml-3 text-xs">
            Event {eventIndex + 1} / {totalEvents}
          </span>
        </div>

        {/* Speed controls */}
        <div className="flex items-center gap-1">
          <button onClick={onSpeedDown} className="px-1.5 py-0.5 rounded text-xs hover:bg-[var(--color-border)]" title="Slow down (-)">-</button>
          <div className="flex gap-0.5">
            {SPEED_OPTIONS.map((s) => (
              <button
                key={s}
                onClick={() => onSetSpeed(s)}
                className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                  speed === s
                    ? 'bg-[var(--color-accent)] text-[var(--color-bg)]'
                    : 'hover:bg-[var(--color-border)] text-[var(--color-text-secondary)]'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>
          <button onClick={onSpeedUp} className="px-1.5 py-0.5 rounded text-xs hover:bg-[var(--color-border)]" title="Speed up (+)">+</button>
        </div>
      </div>
    </div>
  );
}
