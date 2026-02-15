import { useRef, useEffect, useState, useCallback } from 'react';
import * as d3 from 'd3';
import type { Scenario, NodeDef } from '../../types/scenario';
import type { MetricsData } from '../../types/metrics';
import type { SimState } from '../../engine/SimulationState';
import { nodeColor } from '../../theme/colors';
import { NodeTooltip } from './NodeTooltip';

interface Props {
  scenario: Scenario;
  metrics: MetricsData;
  /** Live simulation state for animated mode. If null, shows static utilization view. */
  simState?: SimState | null;
}

interface TooltipState {
  nodeId: string;
  capacity: number;
  utilization: number;
  x: number;
  y: number;
}

export function NetworkView({ scenario, metrics, simState }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const [dark, setDark] = useState(document.documentElement.classList.contains('dark'));

  useEffect(() => {
    const obs = new MutationObserver(() => {
      setDark(document.documentElement.classList.contains('dark'));
    });
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return () => obs.disconnect();
  }, []);

  const draw = useCallback(() => {
    const svg = d3.select(svgRef.current);
    const container = containerRef.current;
    if (!svg.node() || !container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;
    svg.attr('width', width).attr('height', height);
    svg.selectAll('*').remove();

    const { nodes, links } = scenario.network;
    if (nodes.length === 0) return;

    const animated = !!simState;

    // Compute layout bounds
    const xs = nodes.map((n) => n.position.x);
    const ys = nodes.map((n) => n.position.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const rangeX = maxX - minX || 1;
    const rangeY = maxY - minY || 1;

    const padding = animated ? 100 : 80;
    const scaleX = (x: number) => padding + ((x - minX) / rangeX) * (width - 2 * padding);
    const scaleY = (y: number) => padding + ((y - minY) / rangeY) * (height - 2 * padding);

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const maxCap = Math.max(...nodes.map((n) => n.compute_capacity));
    const maxBw = Math.max(...links.map((l) => l.bandwidth), 1);
    const nodeR = (d: NodeDef) => 12 + (d.compute_capacity / maxCap) * 14;

    // Active state lookup
    const activeLinks = new Set<string>();
    const activeNodes = new Set<string>();
    const nodeTaskMap = new Map<string, string>();
    const nodeCompletedMap = new Map<string, number>();

    if (simState) {
      for (const [id, ls] of simState.links) {
        if (ls.activeTransfers.length > 0) activeLinks.add(id);
      }
      for (const [id, ns] of simState.nodes) {
        if (ns.status === 'running') {
          activeNodes.add(id);
          if (ns.currentTask) nodeTaskMap.set(id, ns.currentTask);
        }
        if (ns.completedTasks.length > 0) {
          nodeCompletedMap.set(id, ns.completedTasks.length);
        }
      }
    }

    // Defs for filters and animations
    const defs = svg.append('defs');

    // Glow filter for active nodes
    const glowFilter = defs.append('filter').attr('id', 'glow');
    glowFilter.append('feGaussianBlur').attr('stdDeviation', '6').attr('result', 'blur');
    glowFilter.append('feMerge').selectAll('feMergeNode')
      .data(['blur', 'SourceGraphic']).enter()
      .append('feMergeNode').attr('in', (d: string) => d);

    // Animated dash pattern for active links
    if (animated) {
      const style = svg.append('style');
      style.text(`
        @keyframes dash-flow {
          to { stroke-dashoffset: -24; }
        }
        .link-active {
          animation: dash-flow 0.6s linear infinite;
        }
        @keyframes pulse-ring {
          0% { r: ${26}; opacity: 0.8; }
          100% { r: ${36}; opacity: 0; }
        }
        .pulse-ring {
          animation: pulse-ring 1.2s ease-out infinite;
        }
      `);
    }

    // Zoom
    const g = svg.append('g');
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 5])
      .on('zoom', (event) => g.attr('transform', event.transform));
    (svg as unknown as d3.Selection<SVGSVGElement, unknown, null, undefined>).call(zoom);

    // === DRAW LINKS ===
    for (const link of links) {
      const fromN = nodeMap.get(link.from);
      const toN = nodeMap.get(link.to);
      if (!fromN || !toN) continue;

      const x1 = scaleX(fromN.position.x), y1 = scaleY(fromN.position.y);
      const x2 = scaleX(toN.position.x), y2 = scaleY(toN.position.y);
      const isActive = activeLinks.has(link.id);
      const thickness = Math.max(2, (link.bandwidth / maxBw) * 8);

      // Base link line
      g.append('line')
        .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
        .attr('stroke', dark ? '#1e1e3f' : '#e2e4ea')
        .attr('stroke-width', thickness)
        .attr('stroke-opacity', 0.5);

      if (isActive) {
        // Bright glow underneath
        g.append('line')
          .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
          .attr('stroke', dark ? '#ff00ff' : '#a855f7')
          .attr('stroke-width', thickness + 4)
          .attr('stroke-opacity', 0.3)
          .attr('filter', 'url(#glow)');

        // Animated dashed line on top
        g.append('line')
          .attr('class', 'link-active')
          .attr('x1', x1).attr('y1', y1).attr('x2', x2).attr('y2', y2)
          .attr('stroke', dark ? '#ff00ff' : '#a855f7')
          .attr('stroke-width', thickness)
          .attr('stroke-dasharray', '8 4')
          .attr('stroke-linecap', 'round');

        // Transfer label on link
        const linkState = simState?.links.get(link.id);
        if (linkState && linkState.activeTransfers.length > 0) {
          const t = linkState.activeTransfers[0];
          const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
          // Background
          g.append('rect')
            .attr('x', mx - 40).attr('y', my - 20)
            .attr('width', 80).attr('height', 18)
            .attr('rx', 4)
            .attr('fill', dark ? '#1a0030' : '#f3e8ff')
            .attr('stroke', dark ? '#ff00ff' : '#a855f7')
            .attr('stroke-width', 1);
          g.append('text')
            .attr('x', mx).attr('y', my - 8)
            .attr('text-anchor', 'middle')
            .attr('fill', dark ? '#ff88ff' : '#7c3aed')
            .attr('font-size', 10)
            .attr('font-weight', 600)
            .text(`${t.fromTask}→${t.toTask}`);
        }
      } else if (!animated) {
        // Static mode: show bandwidth label
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        g.append('text')
          .attr('x', mx).attr('y', my - 8)
          .attr('text-anchor', 'middle')
          .attr('fill', dark ? '#8888aa' : '#666680')
          .attr('font-size', 10)
          .text(`${link.bandwidth} MB/s`);
      }
    }

    // === DRAW NODES ===
    for (let i = 0; i < nodes.length; i++) {
      const node = nodes[i];
      const cx = scaleX(node.position.x);
      const cy = scaleY(node.position.y);
      const r = nodeR(node);
      const isRunning = activeNodes.has(node.id);
      const completed = nodeCompletedMap.get(node.id) ?? 0;
      const taskName = nodeTaskMap.get(node.id);

      const ng = g.append('g').attr('transform', `translate(${cx},${cy})`);

      if (isRunning) {
        // Pulsing outer ring
        ng.append('circle')
          .attr('class', 'pulse-ring')
          .attr('r', r + 14)
          .attr('fill', 'none')
          .attr('stroke', dark ? '#ffd700' : '#d97706')
          .attr('stroke-width', 3);

        // Static glow ring
        ng.append('circle')
          .attr('r', r + 8)
          .attr('fill', dark ? '#ffd700' : '#d97706')
          .attr('fill-opacity', 0.15)
          .attr('stroke', dark ? '#ffd700' : '#d97706')
          .attr('stroke-width', 2.5)
          .attr('filter', 'url(#glow)');
      }

      // Node fill color
      let fill: string;
      if (animated) {
        if (isRunning) {
          fill = dark ? '#ffd700' : '#d97706'; // bright gold when running
        } else if (completed > 0) {
          fill = dark ? '#00cc66' : '#16a34a'; // green when has completed tasks
        } else {
          fill = dark ? '#2a2a4a' : '#d4d4dc'; // dim when idle/unused
        }
      } else {
        const util = metrics.node_utilization[node.id] ?? 0;
        if (util > 0.5) fill = dark ? '#00ff88' : '#16a34a';
        else if (util > 0.1) fill = nodeColor(i, dark);
        else fill = dark ? '#333355' : '#c4c4d4';
      }

      // Main circle
      ng.append('circle')
        .attr('r', r)
        .attr('fill', fill)
        .attr('stroke', isRunning ? (dark ? '#ffd700' : '#d97706') : (dark ? '#e0e0ff' : '#1a1a2e'))
        .attr('stroke-width', isRunning ? 3 : 1.5)
        .attr('cursor', 'pointer')
        .on('mouseenter', (event: MouseEvent) => {
          setTooltip({
            nodeId: node.id,
            capacity: node.compute_capacity,
            utilization: metrics.node_utilization[node.id] ?? 0,
            x: event.clientX, y: event.clientY,
          });
        })
        .on('mousemove', (event: MouseEvent) => {
          setTooltip({
            nodeId: node.id,
            capacity: node.compute_capacity,
            utilization: metrics.node_utilization[node.id] ?? 0,
            x: event.clientX, y: event.clientY,
          });
        })
        .on('mouseleave', () => setTooltip(null));

      // Node ID label (above)
      ng.append('text')
        .attr('dy', -(r + 6))
        .attr('text-anchor', 'middle')
        .attr('fill', dark ? '#e0e0ff' : '#1a1a2e')
        .attr('font-size', 12)
        .attr('font-weight', 700)
        .text(node.id);

      if (animated) {
        // Running: show task name INSIDE the node
        if (isRunning && taskName) {
          ng.append('text')
            .attr('dy', 4)
            .attr('text-anchor', 'middle')
            .attr('fill', dark ? '#0a0a1a' : '#ffffff')
            .attr('font-size', 11)
            .attr('font-weight', 700)
            .text(taskName);
        }

        // Completed count badge (below)
        if (completed > 0 && !isRunning) {
          ng.append('text')
            .attr('dy', 5)
            .attr('text-anchor', 'middle')
            .attr('fill', dark ? '#0a0a1a' : '#ffffff')
            .attr('font-size', 10)
            .attr('font-weight', 600)
            .text(`✓${completed}`);
        }
      } else {
        // Static: show capacity below
        ng.append('text')
          .attr('dy', r + 14)
          .attr('text-anchor', 'middle')
          .attr('fill', dark ? '#8888aa' : '#666680')
          .attr('font-size', 9)
          .text(`${node.compute_capacity} CU/s`);
      }
    }
  }, [scenario, metrics, simState, dark]);

  useEffect(() => {
    draw();
    const resizeObs = new ResizeObserver(() => draw());
    if (containerRef.current) resizeObs.observe(containerRef.current);
    return () => resizeObs.disconnect();
  }, [draw]);

  return (
    <div ref={containerRef} className="relative w-full h-full min-h-[400px]">
      <svg ref={svgRef} className="w-full h-full" />
      {tooltip && <NodeTooltip {...tooltip} />}
    </div>
  );
}
