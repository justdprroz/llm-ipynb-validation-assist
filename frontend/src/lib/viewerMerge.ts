/**
 * Merge persisted viewer adjustments into run results.
 * Total score = mean of per-task scores (0–1), matching instant pipeline display.
 */
import type { RunResult, TaskResult, ViewerAdjustmentPayload } from '@/types';

function cloneTask(t: TaskResult): TaskResult {
  return { ...t };
}

/** Apply overrides and recompute `total_score` as mean of task scores. */
export function mergeRunResults(
  base: RunResult[],
  adj: ViewerAdjustmentPayload,
): RunResult[] {
  return base.map((r) => {
    const overrides = adj.task_scores[r.student_id] ?? {};
    const tasks = r.tasks.map((t) => {
      const o = overrides[t.task_id];
      if (o === undefined) {
        return cloneTask(t);
      }
      const score = Math.min(1, Math.max(0, o));
      return { ...t, score };
    });
    const total =
      tasks.length > 0 ? tasks.reduce((s, t) => s + t.score, 0) / tasks.length : 0;
    return {
      ...r,
      tasks,
      total_score: total,
    };
  });
}

export function filterExcludedFromSummary(
  merged: RunResult[],
  excludedStudentIds: string[],
): RunResult[] {
  const ex = new Set(excludedStudentIds);
  return merged.filter((r) => !ex.has(r.student_id));
}

export interface TaskColumnStats {
  task_id: string;
  n: number;
  mean: number;
  pass_rate: number;
  pass: number;
  partial: number;
  fail: number;
  error: number;
}

/**
 * Pass rate: fraction with effective score >= 1 (not using legacy status alone).
 * Error bucket: original `status === 'error'` (still counted in n unless you exclude — we count in n).
 */
export function computeTaskColumnStats(
  results: RunResult[],
  taskIds: string[],
): TaskColumnStats[] {
  return taskIds.map((taskId) => {
    let pass = 0;
    let partial = 0;
    let fail = 0;
    let error = 0;
    let sum = 0;
    const n = results.length;

    for (const r of results) {
      const t = r.tasks.find((x) => x.task_id === taskId);
      const score = t?.score ?? 0;
      sum += score;
      if (t?.status === 'error') {
        error += 1;
      } else if (score >= 1) {
        pass += 1;
      } else if (score > 0) {
        partial += 1;
      } else {
        fail += 1;
      }
    }

    const mean = n > 0 ? sum / n : 0;
    const pass_rate = n > 0 ? pass / n : 0;

    return {
      task_id: taskId,
      n,
      mean,
      pass_rate,
      pass,
      partial,
      fail,
      error,
    };
  });
}

/** TSV: header row + data; excludes students in `excludedStudentIds`. */
export function buildAdjustedReportTsv(
  merged: RunResult[],
  taskIds: string[],
  excludedStudentIds: string[],
  runId: string,
): string {
  const ex = new Set(excludedStudentIds);
  const rows = merged.filter((r) => !ex.has(r.student_id));
  const header = ['student_id', ...taskIds, 'total_score'].join('\t');
  const lines = rows.map((r) => {
    const cells = [r.student_id];
    for (const tid of taskIds) {
      const sc = r.tasks.find((t) => t.task_id === tid)?.score ?? 0;
      cells.push(String(sc));
    }
    cells.push(String(r.total_score));
    return cells.join('\t');
  });
  const note = `# Adjusted viewer export; run_id=${runId}; excluded=${excludedStudentIds.join(',')}`;
  return [note, header, ...lines].join('\n');
}

export function buildAdjustedReportMarkdown(
  merged: RunResult[],
  taskIds: string[],
  excludedStudentIds: string[],
  runId: string,
): string {
  const ex = new Set(excludedStudentIds);
  const rows = merged.filter((r) => !ex.has(r.student_id));
  const cols = ['student_id', ...taskIds, 'total_score'];
  const head = '| ' + cols.join(' | ') + ' |';
  const sep = '| ' + cols.map(() => '---').join(' | ') + ' |';
  const bodyLines = rows.map((r) => {
    const cells = [r.student_id];
    for (const tid of taskIds) {
      cells.push((r.tasks.find((t) => t.task_id === tid)?.score ?? 0).toFixed(2));
    }
    cells.push(r.total_score.toFixed(2));
    return '| ' + cells.join(' | ') + ' |';
  });
  const intro = [
    `Adjusted viewer export (run \`${runId}\`).`,
    excludedStudentIds.length
      ? `Excluded from table: ${excludedStudentIds.map((s) => `\`${s}\``).join(', ')}.`
      : '',
  ].filter(Boolean);
  return [...intro, '', head, sep, ...bodyLines].join('\n');
}

export function isCellOverridden(
  adj: ViewerAdjustmentPayload,
  studentId: string,
  taskId: string,
): boolean {
  return adj.task_scores[studentId]?.[taskId] !== undefined;
}
