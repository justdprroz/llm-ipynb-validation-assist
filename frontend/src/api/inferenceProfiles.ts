import { apiGet, apiPost, apiDelete } from './client';
import type { InferenceProfile } from '@/types';

export function listInferenceProfiles(): Promise<InferenceProfile[]> {
  return apiGet<InferenceProfile[]>('/settings/inference-profiles');
}

export function createInferenceProfile(data: {
  name: string;
  provider: string;
  model: string;
  api_key: string;
  yc_folder?: string;
  description?: string;
  is_dummy?: boolean;
  temperature?: number;
  top_p?: number;
  seed?: number | null;
  effort?: string;
  max_tokens?: number;
  openrouter_provider?: Record<string, unknown>;
}): Promise<InferenceProfile> {
  return apiPost<InferenceProfile>('/settings/inference-profiles', data);
}

export function deleteInferenceProfile(id: string): Promise<void> {
  return apiDelete(`/settings/inference-profiles/${id}`);
}
