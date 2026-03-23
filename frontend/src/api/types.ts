export interface PipelineRunSummary {
  id: string;
  model_name: string;
  candidate_version: string;
  champion_version: string | null;
  offline_status: string;
  online_status: string;
  triggered_by: string;
  registry_type: string;
  serving_type: string;
  model_type: string;
  offline_gates_passed: number;
  offline_gates_total: number;
  online_gates_passed: number;
  online_gates_total: number;
  github_context: Record<string, string> | null;
  created_at: string;
  updated_at: string;
}

export interface GateResultResponse {
  id: string;
  pipeline_run_id: string;
  phase: string;
  gate_name: string;
  gate_type: string;
  metric_name: string;
  metric_value: number | null;
  threshold: number | null;
  comparator: string | null;
  passed: boolean | null;
  blocking: boolean;
  skip_reason: string | null;
  detail: Record<string, unknown> | null;
  evaluated_at: string;
}

export interface CanarySnapshot {
  id: string;
  pipeline_run_id: string;
  timestamp: string;
  champion_latency_p50_ms: number | null;
  champion_latency_p95_ms: number | null;
  challenger_latency_p50_ms: number | null;
  challenger_latency_p95_ms: number | null;
  champion_error_rate: number | null;
  challenger_error_rate: number | null;
  detail: Record<string, unknown> | null;
}

export interface AuditLogEntry {
  id: string;
  pipeline_run_id: string;
  phase: string;
  action: string;
  actor: string;
  detail: Record<string, unknown> | null;
  created_at: string;
}

export interface PipelineRunDetail extends PipelineRunSummary {
  gate_results: GateResultResponse[];
  canary_snapshots: CanarySnapshot[];
  audit_log: AuditLogEntry[];
}

export interface GatePolicyResult {
  pipeline_run_id: string;
  offline: {
    phase: string;
    overall_passed: boolean;
    gates: Array<{
      gate_name: string;
      passed: boolean | null;
      metric_value?: number | null;
      threshold?: number | null;
      comparator?: string | null;
      blocking: boolean;
      skip_reason?: string | null;
    }>;
  };
  online: {
    phase: string;
    overall_passed: boolean;
    gates: Array<{
      gate_name: string;
      passed: boolean | null;
      metric_value?: number | null;
      threshold?: number | null;
      comparator?: string | null;
      blocking: boolean;
      skip_reason?: string | null;
    }>;
  };
}

export interface TriggerRequest {
  model_name: string;
  candidate_version: string;
  phase: string;
  gatekeeper_yaml: string;
  triggered_by?: string;
  pipeline_run_id?: string;
  github_context?: Record<string, string>;
}

export interface TriggerResponse {
  pipeline_run_id: string;
  status: string;
  report_url: string;
}

export interface RegistryInfo {
  evaluators: string[];
  model_types: string[];
  dataset_formats: string[];
  drift_methods: string[];
  inference_encodings: string[];
  judge_modalities: string[];
}

export interface RunFilters {
  model_name?: string;
  limit?: number;
}

export class APIError extends Error {
  constructor(
    public status: number,
    public body: Record<string, unknown>,
  ) {
    super(`API error ${status}: ${JSON.stringify(body)}`);
  }
}
