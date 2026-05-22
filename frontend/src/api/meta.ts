import { apiGet } from './client';

export interface PipelineRunDefaultsResponse {
  defaults: Record<string, unknown>;
  description: string;
}

export function getPipelineRunDefaults(): Promise<PipelineRunDefaultsResponse> {
  return apiGet<PipelineRunDefaultsResponse>('/meta/pipeline-run-defaults');
}
