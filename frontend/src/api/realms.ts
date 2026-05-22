import { apiGet, apiDelete, apiUpload } from './client';
import type { Realm, Homework, FileContent, FileEntry } from '@/types';

export function listRealms(): Promise<Realm[]> {
  return apiGet<Realm[]>('/realms');
}

export function getRealm(id: string): Promise<Realm> {
  return apiGet<Realm>(`/realms/${id}`);
}

export function getHomework(
  realmId: string,
  hwId: string,
): Promise<Homework & { student_files: FileEntry[]; gold_files: FileEntry[] }> {
  return apiGet(`/realms/${realmId}/homeworks/${hwId}`);
}

export function uploadRealm(file: File, name: string): Promise<Realm> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('name', name);
  return apiUpload<Realm>('/realms/upload', formData);
}

export function deleteRealm(id: string): Promise<void> {
  return apiDelete(`/realms/${id}`);
}

export function getHomeworkFile(realmId: string, hwId: string, filePath: string): Promise<FileContent> {
  return apiGet<FileContent>(`/realms/${realmId}/homeworks/${hwId}/files/${filePath}`);
}

export function uploadGoldFile(
  realmId: string,
  hwId: string,
  file: File,
): Promise<{ homework_id: string; path: string; filename: string }> {
  const formData = new FormData();
  formData.append('file', file);
  return apiUpload(`/realms/${realmId}/homeworks/${hwId}/gold`, formData);
}
