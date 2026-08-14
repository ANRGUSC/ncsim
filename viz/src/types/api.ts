export interface RunRequest {
  name: string;
  scenario_yaml: string;
}

export interface RunResponse {
  status: string;
  scenario_yaml: string;
  trace_jsonl: string;
  metrics_json: string;
  error: string | null;
}

export interface ExperimentSummary {
  name: string;
  scenario_name: string;
  makespan: number | null;
  total_tasks: number | null;
  total_transfers: number | null;
  scheduler: string | null;
  status: string | null;
  seed: number | null;
}

export interface ExperimentFiles {
  name: string;
  scenario_yaml?: string;
  trace_jsonl?: string;
  metrics_json?: string;
}

export type SchedulerOptionValue = string | number | boolean | null;

export interface SchedulerOptionDefinition {
  name: string;
  label: string;
  type: 'string' | 'integer' | 'number' | 'boolean';
  default: SchedulerOptionValue;
  description: string;
  nullable: boolean;
  choices: SchedulerOptionValue[];
  minimum: number | null;
  maximum: number | null;
}

export interface SchedulerDefinition {
  name: string;
  label: string;
  kind: 'saga' | 'builtin';
  description: string;
  options: SchedulerOptionDefinition[];
}
