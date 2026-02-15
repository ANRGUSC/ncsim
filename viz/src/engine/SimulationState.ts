import type { TraceEvent, TaskStartEvent, TaskCompleteEvent, TransferStartEvent, TransferCompleteEvent, TaskScheduledEvent } from '../types/trace';

export interface NodeState {
  status: 'idle' | 'running';
  currentTask: string | null;
  queuedTasks: string[];
  completedTasks: string[];
}

export interface LinkTransfer {
  fromTask: string;
  toTask: string;
  dataSize: number;
  startTime: number;
  endTime: number;
  progress: number;
}

export interface LinkState {
  activeTransfers: LinkTransfer[];
}

export interface TaskState {
  status: 'pending' | 'scheduled' | 'running' | 'complete';
  nodeId: string | null;
  startTime: number | null;
  endTime: number | null;
}

export interface SimState {
  nodes: Map<string, NodeState>;
  links: Map<string, LinkState>;
  tasks: Map<string, TaskState>;
  currentTime: number;
  eventsProcessed: number;
}

export function deriveState(trace: TraceEvent[], currentTime: number): SimState {
  const nodes = new Map<string, NodeState>();
  const links = new Map<string, LinkState>();
  const tasks = new Map<string, TaskState>();

  let eventsProcessed = 0;

  for (const event of trace) {
    if (event.sim_time > currentTime) break;
    eventsProcessed++;

    switch (event.type) {
      case 'task_scheduled': {
        const e = event as TaskScheduledEvent;
        tasks.set(e.task_id, {
          status: 'scheduled',
          nodeId: e.node_id,
          startTime: null,
          endTime: null,
        });
        if (!nodes.has(e.node_id)) {
          nodes.set(e.node_id, { status: 'idle', currentTask: null, queuedTasks: [], completedTasks: [] });
        }
        break;
      }
      case 'task_start': {
        const e = event as TaskStartEvent;
        const task = tasks.get(e.task_id);
        if (task) {
          task.status = 'running';
          task.startTime = e.sim_time;
        }
        const node = nodes.get(e.node_id);
        if (node) {
          node.status = 'running';
          node.currentTask = e.task_id;
          node.queuedTasks = node.queuedTasks.filter((t) => t !== e.task_id);
        }
        break;
      }
      case 'task_complete': {
        const e = event as TaskCompleteEvent;
        const task = tasks.get(e.task_id);
        if (task) {
          task.status = 'complete';
          task.endTime = e.sim_time;
        }
        const node = nodes.get(e.node_id);
        if (node) {
          node.completedTasks.push(e.task_id);
          if (node.currentTask === e.task_id) {
            node.currentTask = null;
            node.status = 'idle';
          }
        }
        break;
      }
      case 'transfer_start': {
        const e = event as TransferStartEvent;
        const transferInfo: LinkTransfer = {
          fromTask: e.from_task,
          toTask: e.to_task,
          dataSize: e.data_size,
          startTime: e.sim_time,
          endTime: Infinity,
          progress: 0,
        };
        // Add transfer to all links in the route (multi-hop) or just the primary link
        const routeLinks = e.route && e.route.length > 0 ? e.route : [e.link_id];
        for (const lid of routeLinks) {
          if (!links.has(lid)) {
            links.set(lid, { activeTransfers: [] });
          }
          links.get(lid)!.activeTransfers.push({ ...transferInfo });
        }
        break;
      }
      case 'transfer_complete': {
        const e = event as TransferCompleteEvent;
        const completeLinks = e.route && e.route.length > 0 ? e.route : [e.link_id];
        for (const lid of completeLinks) {
          const link = links.get(lid);
          if (link) {
            link.activeTransfers = link.activeTransfers.filter(
              (t) => !(t.fromTask === e.from_task && t.toTask === e.to_task)
            );
          }
        }
        break;
      }
    }
  }

  // Update transfer end times and progress from remaining trace events
  for (const event of trace) {
    if (event.type === 'transfer_complete') {
      const e = event as TransferCompleteEvent;
      const updateLinks = e.route && e.route.length > 0 ? e.route : [e.link_id];
      for (const lid of updateLinks) {
        const link = links.get(lid);
        if (link) {
          for (const t of link.activeTransfers) {
            if (t.fromTask === e.from_task && t.toTask === e.to_task) {
              t.endTime = e.sim_time;
              const elapsed = currentTime - t.startTime;
              const duration = t.endTime - t.startTime;
              t.progress = duration > 0 ? Math.min(elapsed / duration, 1) : 1;
            }
          }
        }
      }
    }
  }

  return { nodes, links, tasks, currentTime, eventsProcessed };
}

export function getTaskAssignments(trace: TraceEvent[]): Map<string, string> {
  const assignments = new Map<string, string>();
  for (const event of trace) {
    if (event.type === 'task_scheduled') {
      const e = event as TaskScheduledEvent;
      assignments.set(e.task_id, e.node_id);
    }
  }
  return assignments;
}

export interface TaskTiming {
  taskId: string;
  nodeId: string;
  startTime: number;
  endTime: number;
  duration: number;
}

export interface TransferTiming {
  fromTask: string;
  toTask: string;
  linkId: string;
  startTime: number;
  endTime: number;
  duration: number;
  dataSize: number;
}

export function extractTimings(trace: TraceEvent[]): {
  taskTimings: TaskTiming[];
  transferTimings: TransferTiming[];
} {
  const taskTimings: TaskTiming[] = [];
  const transferTimings: TransferTiming[] = [];
  const taskStarts = new Map<string, { time: number; nodeId: string }>();
  const transferStarts = new Map<string, { time: number; linkId: string; dataSize: number }>();

  for (const event of trace) {
    switch (event.type) {
      case 'task_start': {
        const e = event as TaskStartEvent;
        taskStarts.set(e.task_id, { time: e.sim_time, nodeId: e.node_id });
        break;
      }
      case 'task_complete': {
        const e = event as TaskCompleteEvent;
        const start = taskStarts.get(e.task_id);
        if (start) {
          taskTimings.push({
            taskId: e.task_id,
            nodeId: e.node_id,
            startTime: start.time,
            endTime: e.sim_time,
            duration: e.duration,
          });
        }
        break;
      }
      case 'transfer_start': {
        const e = event as TransferStartEvent;
        const key = `${e.from_task}->${e.to_task}`;
        transferStarts.set(key, { time: e.sim_time, linkId: e.link_id, dataSize: e.data_size });
        break;
      }
      case 'transfer_complete': {
        const e = event as TransferCompleteEvent;
        const key = `${e.from_task}->${e.to_task}`;
        const start = transferStarts.get(key);
        if (start) {
          transferTimings.push({
            fromTask: e.from_task,
            toTask: e.to_task,
            linkId: start.linkId,
            startTime: start.time,
            endTime: e.sim_time,
            duration: e.duration,
            dataSize: start.dataSize,
          });
        }
        break;
      }
    }
  }

  return { taskTimings, transferTimings };
}
