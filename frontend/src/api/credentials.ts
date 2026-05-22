import { apiGet, apiPost, apiDelete } from './client';
import type { GitCredential } from '@/types';

export function listCredentials(): Promise<GitCredential[]> {
  return apiGet<GitCredential[]>('/credentials');
}

export function createCredential(data: { host: string; token: string; description?: string }): Promise<GitCredential> {
  return apiPost<GitCredential>('/credentials', data);
}

export function deleteCredential(id: string): Promise<void> {
  return apiDelete(`/credentials/${id}`);
}
