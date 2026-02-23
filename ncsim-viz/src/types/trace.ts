interface BaseEvent {
  seq: number;
  sim_time: number;
  type: string;
}

export interface SimStartEvent extends BaseEvent {
  type: 'sim_start';
  trace_version: string;
  seed: number;
  scenario: string;
  scenario_hash: string;
}

export interface SimEndEvent extends BaseEvent {
  type: 'sim_end';
  status: string;
  makespan: number;
  total_events: number;
}

export interface DagInjectEvent extends BaseEvent {
  type: 'dag_inject';
  dag_id: string;
  task_ids: string[];
}

export interface TaskScheduledEvent extends BaseEvent {
  type: 'task_scheduled';
  dag_id: string;
  task_id: string;
  node_id: string;
}

export interface TaskStartEvent extends BaseEvent {
  type: 'task_start';
  dag_id: string;
  task_id: string;
  node_id: string;
}

export interface TaskCompleteEvent extends BaseEvent {
  type: 'task_complete';
  dag_id: string;
  task_id: string;
  node_id: string;
  duration: number;
}

export interface TransferStartEvent extends BaseEvent {
  type: 'transfer_start';
  dag_id: string;
  from_task: string;
  to_task: string;
  link_id: string;
  data_size: number;
  route?: string[];
}

export interface TransferCompleteEvent extends BaseEvent {
  type: 'transfer_complete';
  dag_id: string;
  from_task: string;
  to_task: string;
  link_id: string;
  duration: number;
  route?: string[];
}

export type TraceEvent =
  | SimStartEvent
  | SimEndEvent
  | DagInjectEvent
  | TaskScheduledEvent
  | TaskStartEvent
  | TaskCompleteEvent
  | TransferStartEvent
  | TransferCompleteEvent;

export type TraceEventType = TraceEvent['type'];
