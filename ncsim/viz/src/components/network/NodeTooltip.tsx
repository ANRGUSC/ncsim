interface Props {
  nodeId: string;
  capacity: number;
  utilization: number;
  x: number;
  y: number;
}

export function NodeTooltip({ nodeId, capacity, utilization, x, y }: Props) {
  return (
    <div
      className="absolute pointer-events-none z-50 px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] shadow-lg text-xs"
      style={{ left: x + 12, top: y - 10 }}
    >
      <div className="font-bold mb-1">{nodeId}</div>
      <div className="text-[var(--color-text-secondary)]">
        Capacity: <span className="font-mono text-[var(--color-text)]">{capacity}</span> CU/s
      </div>
      <div className="text-[var(--color-text-secondary)]">
        Utilization: <span className="font-mono text-[var(--color-text)]">{(utilization * 100).toFixed(1)}%</span>
      </div>
    </div>
  );
}
