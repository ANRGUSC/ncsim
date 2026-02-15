import { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import * as d3 from 'd3';
import type { TraceEvent } from '../../types/trace';
import type { Scenario } from '../../types/scenario';
import type { MetricsData } from '../../types/metrics';
import { extractTimings, getTaskAssignments } from '../../engine/SimulationState';
import { nodeColor } from '../../theme/colors';

interface Props {
  trace: TraceEvent[];
  scenario: Scenario;
  metrics: MetricsData;
  currentTime?: number;
  maxTime?: number;
}

export function GanttChart({ trace, scenario, metrics, currentTime, maxTime }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dark, setDark] = useState(document.documentElement.classList.contains('dark'));
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);

  useEffect(() => {
    const obs = new MutationObserver(() => setDark(document.documentElement.classList.contains('dark')));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  const { taskTimings, transferTimings } = useMemo(() => extractTimings(trace), [trace]);
  const assignments = useMemo(() => getTaskAssignments(trace), [trace]);
  const makespan = maxTime ?? metrics.makespan;

  const nodeIds = useMemo(() => scenario.network.nodes.map((n) => n.id), [scenario]);
  const nodeIndex = useMemo(() => {
    const m = new Map<string, number>();
    nodeIds.forEach((id, i) => m.set(id, i));
    return m;
  }, [nodeIds]);

  const draw = useCallback(() => {
    if (!svgRef.current || !containerRef.current) return;

    const width = containerRef.current.clientWidth;
    const margin = { top: 30, right: 20, bottom: 30, left: 70 };
    const rowHeight = 40;
    const height = margin.top + margin.bottom + nodeIds.length * rowHeight;

    const svg = d3.select(svgRef.current);
    svg.attr('width', width).attr('height', height);
    svg.selectAll('*').remove();

    const xScale = d3.scaleLinear()
      .domain([0, makespan])
      .range([margin.left, width - margin.right]);

    const yScale = d3.scaleBand<string>()
      .domain(nodeIds)
      .range([margin.top, height - margin.bottom])
      .padding(0.2);

    // Background rows
    svg.selectAll('.row-bg')
      .data(nodeIds)
      .enter()
      .append('rect')
      .attr('x', margin.left)
      .attr('y', (d: string) => yScale(d)!)
      .attr('width', width - margin.left - margin.right)
      .attr('height', yScale.bandwidth())
      .attr('fill', (_d: string, i: number) => i % 2 === 0 ? (dark ? '#0e0e24' : '#f0f1f5') : 'transparent');

    // X axis
    svg.append('g')
      .attr('transform', `translate(0,${height - margin.bottom})`)
      .call(d3.axisBottom(xScale).ticks(10).tickFormat((d) => `${d}s`))
      .attr('color', dark ? '#8888aa' : '#666680')
      .selectAll('text').attr('font-size', 10);

    // X axis top
    svg.append('g')
      .attr('transform', `translate(0,${margin.top})`)
      .call(d3.axisTop(xScale).ticks(10).tickFormat((d) => `${d}s`))
      .attr('color', dark ? '#8888aa' : '#666680')
      .selectAll('text').attr('font-size', 10);

    // Y axis
    const yAxis = svg.append('g')
      .attr('transform', `translate(${margin.left},0)`)
      .call(d3.axisLeft(yScale))
      .attr('color', dark ? '#8888aa' : '#666680');
    yAxis.selectAll('text').attr('font-size', 11).attr('font-weight', 600);

    // Filter timings up to currentTime if provided
    const filteredTasks = currentTime != null
      ? taskTimings.filter((t) => t.startTime <= currentTime)
      : taskTimings;
    const filteredTransfers = currentTime != null
      ? transferTimings.filter((t) => t.startTime <= currentTime)
      : transferTimings;

    // Task bars
    svg.selectAll('.task-bar')
      .data(filteredTasks)
      .enter()
      .append('rect')
      .attr('class', 'task-bar')
      .attr('x', (d) => xScale(d.startTime))
      .attr('y', (d) => yScale(d.nodeId)! + yScale.bandwidth() * 0.05)
      .attr('width', (d) => {
        const end = currentTime != null ? Math.min(d.endTime, currentTime) : d.endTime;
        return Math.max(xScale(end) - xScale(d.startTime), 2);
      })
      .attr('height', yScale.bandwidth() * 0.55)
      .attr('rx', 4)
      .attr('fill', (d) => nodeColor(nodeIndex.get(d.nodeId) ?? 0, dark))
      .attr('fill-opacity', 0.8)
      .attr('cursor', 'pointer')
      .on('mouseenter', (event: MouseEvent, d) => {
        setTooltip({
          text: `${d.taskId} on ${d.nodeId}\n${d.startTime.toFixed(3)}s → ${d.endTime.toFixed(3)}s (${d.duration.toFixed(3)}s)`,
          x: event.clientX,
          y: event.clientY,
        });
      })
      .on('mouseleave', () => setTooltip(null));

    // Task labels
    svg.selectAll('.task-label')
      .data(filteredTasks)
      .enter()
      .append('text')
      .attr('x', (d) => xScale(d.startTime) + 4)
      .attr('y', (d) => yScale(d.nodeId)! + yScale.bandwidth() * 0.35)
      .attr('fill', dark ? '#0a0a1a' : '#fff')
      .attr('font-size', 10)
      .attr('font-weight', 600)
      .text((d) => {
        const barWidth = xScale(d.endTime) - xScale(d.startTime);
        return barWidth > 30 ? d.taskId : '';
      });

    // Transfer bars (below task bars, hatched style)
    svg.selectAll('.transfer-bar')
      .data(filteredTransfers)
      .enter()
      .append('rect')
      .attr('class', 'transfer-bar')
      .attr('x', (d) => xScale(d.startTime))
      .attr('y', (d) => {
        const srcNode = assignments.get(d.fromTask);
        return yScale(srcNode ?? nodeIds[0])! + yScale.bandwidth() * 0.6;
      })
      .attr('width', (d) => {
        const end = currentTime != null ? Math.min(d.endTime, currentTime) : d.endTime;
        return Math.max(xScale(end) - xScale(d.startTime), 2);
      })
      .attr('height', yScale.bandwidth() * 0.35)
      .attr('rx', 2)
      .attr('fill', dark ? '#ff00ff' : '#a855f7')
      .attr('fill-opacity', 0.4)
      .attr('stroke', dark ? '#ff00ff' : '#a855f7')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '4 2')
      .attr('cursor', 'pointer')
      .on('mouseenter', (event: MouseEvent, d) => {
        setTooltip({
          text: `${d.fromTask}→${d.toTask} via ${d.linkId}\n${d.dataSize} MB, ${d.startTime.toFixed(3)}s → ${d.endTime.toFixed(3)}s`,
          x: event.clientX,
          y: event.clientY,
        });
      })
      .on('mouseleave', () => setTooltip(null));

    // Current time playhead
    if (currentTime != null && currentTime <= makespan) {
      svg.append('line')
        .attr('x1', xScale(currentTime))
        .attr('x2', xScale(currentTime))
        .attr('y1', margin.top)
        .attr('y2', height - margin.bottom)
        .attr('stroke', dark ? '#ff3333' : '#dc2626')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', '4 2');
    }
  }, [taskTimings, transferTimings, assignments, nodeIds, nodeIndex, makespan, currentTime, dark]);

  useEffect(() => {
    draw();
    const obs = new ResizeObserver(() => draw());
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [draw]);

  return (
    <div ref={containerRef} className="relative w-full h-full min-h-[300px] overflow-auto">
      <svg ref={svgRef} />
      {tooltip && (
        <div
          className="absolute pointer-events-none z-50 px-3 py-2 rounded-lg bg-[var(--color-bg)] border border-[var(--color-border)] shadow-lg text-xs whitespace-pre"
          style={{ left: tooltip.x + 12, top: tooltip.y - 10 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}
