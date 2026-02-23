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
