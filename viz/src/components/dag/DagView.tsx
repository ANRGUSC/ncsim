import { useRef, useEffect, useState, useMemo, useCallback } from 'react';
import * as d3 from 'd3';
import dagre from 'dagre';
import type { Scenario } from '../../types/scenario';
import type { TraceEvent } from '../../types/trace';
import { getTaskAssignments, extractTimings } from '../../engine/SimulationState';
import { nodeColor } from '../../theme/colors';
import { TaskTooltip } from './TaskTooltip';

interface Props {
  scenario: Scenario;
  trace: TraceEvent[];
}

interface TooltipState {
  taskId: string;
  computeCost: number;
  nodeId: string | null;
  startTime: number | null;
  endTime: number | null;
  x: number;
  y: number;
}

export function DagView({ scenario, trace }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [dark, setDark] = useState(document.documentElement.classList.contains('dark'));

  useEffect(() => {
    const obs = new MutationObserver(() => setDark(document.documentElement.classList.contains('dark')));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  const assignments = useMemo(() => getTaskAssignments(trace), [trace]);
  const { taskTimings } = useMemo(() => extractTimings(trace), [trace]);
  const timingMap = useMemo(() => {
    const m = new Map<string, { start: number; end: number }>();
    for (const t of taskTimings) m.set(t.taskId, { start: t.startTime, end: t.endTime });
    return m;
  }, [taskTimings]);

  // Build node index: nodeId → index for coloring
  const nodeIndex = useMemo(() => {
    const m = new Map<string, number>();
    scenario.network.nodes.forEach((n, i) => m.set(n.id, i));
    return m;
  }, [scenario]);

  const dag = scenario.dags[0];

  const draw = useCallback(() => {
    if (!svgRef.current || !containerRef.current || !dag) return;

    const width = containerRef.current.clientWidth;
    const height = containerRef.current.clientHeight;
    const svg = d3.select(svgRef.current);
    svg.attr('width', width).attr('height', height);
    svg.selectAll('*').remove();

    // Build dagre graph
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: 'LR', ranksep: 80, nodesep: 40, marginx: 40, marginy: 40 });
    g.setDefaultEdgeLabel(() => ({}));

    for (const task of dag.tasks) {
      g.setNode(task.id, { label: task.id, width: 100, height: 50 });
    }
    for (const edge of dag.edges) {
      g.setEdge(edge.from, edge.to);
    }

    dagre.layout(g);

    // Create a zoomable group
    const zoomG = svg.append('g');
    const zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on('zoom', (event) => zoomG.attr('transform', event.transform));
    svg.call(zoomBehavior);

    // Arrow marker
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 0 10 7')
      .attr('refX', 10).attr('refY', 3.5)
      .attr('markerWidth', 8).attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('polygon')
      .attr('points', '0 0, 10 3.5, 0 7')
      .attr('fill', dark ? '#8888aa' : '#666680');

    // Draw edges
    for (const edge of dag.edges) {
      const e = g.edge(edge.from, edge.to);
      if (!e || !e.points) continue;
      const line = d3.line<{ x: number; y: number }>()
        .x((d) => d.x).y((d) => d.y)
        .curve(d3.curveBasis);

      zoomG.append('path')
        .attr('d', line(e.points)!)
        .attr('fill', 'none')
        .attr('stroke', dark ? '#8888aa' : '#999')
        .attr('stroke-width', 1.5)
        .attr('marker-end', 'url(#arrowhead)');

      // Edge label (data_size)
      const midpoint = e.points[Math.floor(e.points.length / 2)];
      zoomG.append('text')
        .attr('x', midpoint.x).attr('y', midpoint.y - 8)
        .attr('text-anchor', 'middle')
        .attr('fill', dark ? '#8888aa' : '#666680')
        .attr('font-size', 9)
        .text(`${edge.data_size} MB`);
    }

    // Draw task nodes
    for (const task of dag.tasks) {
      const node = g.node(task.id);
      if (!node) continue;

      const assigned = assignments.get(task.id);
      const idx = assigned ? (nodeIndex.get(assigned) ?? 0) : 0;
      const fill = assigned ? nodeColor(idx, dark) : (dark ? '#333355' : '#ddd');

      const taskG = zoomG.append('g')
        .attr('transform', `translate(${node.x - 50},${node.y - 25})`)
        .attr('cursor', 'pointer');

      taskG.append('rect')
        .attr('width', 100).attr('height', 50)
        .attr('rx', 8).attr('ry', 8)
        .attr('fill', fill)
        .attr('fill-opacity', 0.2)
        .attr('stroke', fill)
        .attr('stroke-width', 2);

      taskG.append('text')
        .attr('x', 50).attr('y', 20)
        .attr('text-anchor', 'middle')
        .attr('fill', dark ? '#e0e0ff' : '#1a1a2e')
        .attr('font-size', 12)
        .attr('font-weight', 600)
        .text(task.id);

      taskG.append('text')
        .attr('x', 50).attr('y', 37)
        .attr('text-anchor', 'middle')
        .attr('fill', dark ? '#8888aa' : '#666680')
        .attr('font-size', 10)
        .text(`${task.compute_cost} CU`);

      // Assigned node badge
      if (assigned) {
        taskG.append('text')
          .attr('x', 50).attr('y', -6)
          .attr('text-anchor', 'middle')
          .attr('fill', fill)
          .attr('font-size', 9)
          .attr('font-weight', 600)
          .text(assigned);
      }

      // Tooltip interaction
      taskG.on('mouseenter', (event: MouseEvent) => {
        const timing = timingMap.get(task.id);
        setTooltip({
          taskId: task.id,
          computeCost: task.compute_cost,
          nodeId: assigned ?? null,
          startTime: timing?.start ?? null,
          endTime: timing?.end ?? null,
          x: event.clientX,
          y: event.clientY,
        });
      }).on('mouseleave', () => setTooltip(null));
    }

    // Fit to view
    const graphBounds = g.graph();
    if (graphBounds.width && graphBounds.height) {
      const scale = Math.min(width / (graphBounds.width + 100), height / (graphBounds.height + 100), 1.5);
      const tx = (width - graphBounds.width * scale) / 2;
      const ty = (height - graphBounds.height * scale) / 2;
      svg.call(zoomBehavior.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
    }
  }, [dag, assignments, nodeIndex, timingMap, dark]);

  useEffect(() => {
    draw();
    const obs = new ResizeObserver(() => draw());
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [draw]);

  if (!dag) {
    return <div className="p-6 text-[var(--color-text-secondary)]">No DAG found in scenario</div>;
  }

  return (
    <div ref={containerRef} className="relative w-full h-full min-h-[400px]">
      <svg ref={svgRef} className="w-full h-full" />
      {tooltip && <TaskTooltip {...tooltip} />}
    </div>
  );
}
