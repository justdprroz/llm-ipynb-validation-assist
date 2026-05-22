import { apiGet, apiPost, apiDelete, apiUpload } from './client';
import type { Pipeline } from '@/types';

export function listPipelines(): Promise<Pipeline[]> {
  return apiGet<Pipeline[]>('/pipelines');
}

export function getPipeline(id: string): Promise<Pipeline> {
  return apiGet<Pipeline>(`/pipelines/${id}`);
}

export function installPipeline(request: {
  source_type: string;
  source_path: string;
}): Promise<Pipeline> {
  return apiPost<Pipeline>('/pipelines/install', request);
}

export function deletePipeline(id: string): Promise<void> {
  return apiDelete(`/pipelines/${id}`);
}

export function uploadPipeline(file: File): Promise<Pipeline> {
  const formData = new FormData();
  formData.append('file', file);
  return apiUpload<Pipeline>('/pipelines/upload', formData);
}
