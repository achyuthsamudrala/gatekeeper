import type {
  PipelineRunSummary,
  PipelineRunDetail,
  GatePolicyResult,
  CanarySnapshot,
  AuditLogEntry,
  TriggerRequest,
  TriggerResponse,
  RegistryInfo,
  RunFilters,
  APIError as APIErrorType,
} from './types';
import { APIError } from './types';

const BASE = import.meta.env.VITE_API_URL ?? '';

function toQuery(filters?: RunFilters): string {
  if (!filters) return '';
  const params = new URLSearchParams();
  if (filters.model_name) params.set('model_name', filters.model_name);
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  return params.toString();
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new APIError(response.status, body as Record<string, unknown>);
  }
  return response.json() as Promise<T>;
}

export const api = {
  getPipelineRuns: (filters?: RunFilters) =>
    apiFetch<PipelineRunSummary[]>(`/api/v1/pipeline/runs?${toQuery(filters)}`),
  getPipelineRun: (id: string) =>
    apiFetch<PipelineRunDetail>(`/api/v1/pipeline/runs/${id}`),
  getGateReport: (id: string) =>
    apiFetch<GatePolicyResult>(`/api/v1/pipeline/runs/${id}/report`),
  getCanarySnapshots: (id: string) =>
    apiFetch<CanarySnapshot[]>(`/api/v1/pipeline/runs/${id}/canary`),
  getAuditLog: (id: string) =>
    apiFetch<AuditLogEntry[]>(`/api/v1/pipeline/runs/${id}/audit`),
  triggerPipeline: (body: TriggerRequest) =>
    apiFetch<TriggerResponse>('/api/v1/pipeline/trigger', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  promotePipeline: (id: string, reason: string) =>
    apiFetch<void>(`/api/v1/pipeline/runs/${id}/promote`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  rollbackPipeline: (id: string, reason: string) =>
    apiFetch<void>(`/api/v1/pipeline/runs/${id}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),
  getRegistries: () => apiFetch<RegistryInfo>('/api/v1/system/registries'),
};
