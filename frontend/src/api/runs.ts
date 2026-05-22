import { apiGet, apiPost, apiPut } from './client';
import type { Run, RunResult, CompareResponse, ViewerAdjustmentPayload, ViewerAdjustmentResponse } from '@/types';

interface RunFilters {
  pipeline_id?: string;
  homework_id?: string;
  status?: string;
}

export function listRuns(filters?: RunFilters): Promise<Run[]> {
  const params = new URLSearchParams();
  if (filters?.pipeline_id) params.set('pipeline_id', filters.pipeline_id);
  if (filters?.homework_id) params.set('homework_id', filters.homework_id);
  if (filters?.status) params.set('status', filters.status);
  const query = params.toString();
  return apiGet<Run[]>(`/runs${query ? `?${query}` : ''}`);
}

export function getRun(id: string): Promise<Run> {
  return apiGet<Run>(`/runs/${id}`);
}

export function getRunResults(id: string): Promise<RunResult[]> {
  return apiGet<RunResult[]>(`/runs/${id}/results`);
}

export function createRun(
  pipelineId: string,
  homeworkId: string,
  inferenceProfileId?: string | null,
  pipelineName?: string,
  pipelineVersion?: string,
  pipelineConfig?: Record<string, unknown> | null,
): Promise<Run> {
  return apiPost<Run>('/runs', {
    pipeline_id: pipelineId,
    pipeline_name: pipelineName,
    pipeline_version: pipelineVersion,
    homework_id: homeworkId,
    inference_profile_id: inferenceProfileId ?? undefined,
    pipeline_config: pipelineConfig ?? undefined,
  });
}

export function compareRuns(runIds: string[]): Promise<CompareResponse> {
  const params = new URLSearchParams({ run_ids: runIds.join(',') });
  return apiGet<CompareResponse>(`/compare?${params.toString()}`);
}

export function getViewerAdjustments(runId: string): Promise<ViewerAdjustmentResponse> {
  return apiGet<ViewerAdjustmentResponse>(`/runs/${runId}/viewer-adjustments`);
}

export function putViewerAdjustments(
  runId: string,
  payload: ViewerAdjustmentPayload,
): Promise<ViewerAdjustmentResponse> {
  return apiPut<ViewerAdjustmentResponse>(`/runs/${runId}/viewer-adjustments`, payload);
}
