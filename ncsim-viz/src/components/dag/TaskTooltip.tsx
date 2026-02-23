interface Props {
  taskId: string;
  computeCost: number;
  nodeId: string | null;
  startTime: number | null;
  endTime: number | null;
  x: number;
  y: number;
}

export function TaskTooltip({ taskId, computeCost, nodeId, startTime, endTime, x, y }: Props) {
  return (
    <div
      className="absolute pointer-events-none z-50 px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] shadow-lg text-xs"
      style={{ left: x + 12, top: y - 10 }}
    >
      <div className="font-bold mb-1">{taskId}</div>
      <div className="text-[var(--color-text-secondary)]">
        Compute: <span className="font-mono text-[var(--color-text)]">{computeCost}</span> CU
      </div>
      {nodeId && (
        <div className="text-[var(--color-text-secondary)]">
          Assigned: <span className="font-mono text-[var(--color-text)]">{nodeId}</span>
        </div>
      )}
      {startTime != null && (
        <div className="text-[var(--color-text-secondary)]">
          Start: <span className="font-mono text-[var(--color-text)]">{startTime.toFixed(3)}s</span>
        </div>
      )}
      {endTime != null && (
        <div className="text-[var(--color-text-secondary)]">
          End: <span className="font-mono text-[var(--color-text)]">{endTime.toFixed(3)}s</span>
        </div>
      )}
    </div>
  );
}
