export interface Realm {
  id: string;
  name: string;
  created_at: string;
  homeworks: Homework[];
}

export interface Homework {
  id: string;
  realm_id: string;
  name: string;
  student_count: number;
  gold_count: number;
}

export interface FileEntry {
  name: string;
  path: string;
}

export interface Pipeline {
  id: string;
  name: string;
  version: string;
  source: string;
  source_path: string;
  entry_module: string;
  entry_function: string;
  description: string | null;
  installed_at: string;
  status: 'installed' | 'broken' | 'pending';
}

export interface Run {
  id: string;
  pipeline_id: string | null;
  homework_id: string;
  inference_profile_id: string | null;
  inference_profile_name?: string | null;
  inference_provider?: string | null;
  inference_model?: string | null;
  inference_is_dummy?: boolean | null;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial';
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  run_metadata: Record<string, unknown> | null;
  pipeline_config?: Record<string, unknown> | null;
  pipeline_name?: string;
  homework_name?: string;
}

export interface TaskResult {
  task_id: string;
  score: number;
  max_score: number;
  status: 'pass' | 'fail' | 'partial' | 'error' | 'skipped';
  comment: string | null;
}

export interface RunResult {
  id: string;
  run_id: string;
  student_id: string;
  total_score: number;
  tasks: TaskResult[];
  report: string | null;
  metadata: Record<string, unknown> | null;
}

export interface ViewerAdjustmentPayload {
  v: number;
  excluded_student_ids: string[];
  task_scores: Record<string, Record<string, number>>;
}

export function emptyViewerAdjustment(): ViewerAdjustmentPayload {
  return { v: 1, excluded_student_ids: [], task_scores: {} };
}

export interface ViewerAdjustmentResponse {
  payload: ViewerAdjustmentPayload;
  updated_at: string | null;
}

export interface GitCredential {
  id: string;
  host: string;
  token_preview: string;
  description: string | null;
  created_at: string;
}

export interface InferenceProfile {
  id: string;
  name: string;
  provider: string;
  model: string;
  api_key_preview: string;
  yc_folder: string | null;
  description: string | null;
  is_dummy: boolean;
  created_at: string;
  temperature: number | null;
  top_p: number | null;
  seed: number | null;
  effort: string | null;
  max_tokens: number | null;
  openrouter_provider: Record<string, unknown> | null;
}

export interface CompareEntry {
  student_id: string;
  run_a_score: number | null;
  run_b_score: number | null;
  run_a_tasks: TaskResult[];
  run_b_tasks: TaskResult[];
}

export interface CompareResponse {
  run_a: Run;
  run_b: Run;
  entries: CompareEntry[];
}

export interface NotebookCell {
  cell_type: 'code' | 'markdown' | 'raw';
  source: string;
  outputs: Record<string, unknown>[];
}

export interface NotebookContent {
  cells: NotebookCell[];
  metadata: Record<string, unknown>;
}

export interface FileContent {
  path: string;
  filename: string;
  content_type: 'notebook' | 'text';
  notebook: NotebookContent | null;
  text: string | null;
}
