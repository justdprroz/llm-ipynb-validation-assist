import { apiGet, apiPost } from './client';

export interface AnytaskSyncResult {
  course_id: string;
  synced_at: string;
  artifacts: string[];
  bucket: string;
}

export interface AnytaskCourseData {
  course_id: string;
  artifacts: {
    course: object | null;
    queue: object | null;
    gradebook: object | null;
  };
}

export function syncCourse(courseId: string): Promise<AnytaskSyncResult> {
  return apiPost<AnytaskSyncResult>(`/integrations/anytask/courses/${courseId}/sync`, {});
}

export function getSyncedCourse(courseId: string): Promise<AnytaskCourseData> {
  return apiGet<AnytaskCourseData>(`/integrations/anytask/courses/${courseId}`);
}

export interface RealmImportResult {
  realm_id: string;
  realm_name: string;
  homework_count: number;
  student_count: number;
}

export function importCourseAsRealm(
  courseId: string,
  realmName?: string,
): Promise<RealmImportResult> {
  return apiPost<RealmImportResult>(
    `/integrations/anytask/courses/${courseId}/import-realm`,
    { realm_name: realmName || null },
  );
}
