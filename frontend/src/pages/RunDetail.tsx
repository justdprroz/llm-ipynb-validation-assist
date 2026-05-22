import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { Text, Label, Flex, Button } from '@gravity-ui/uikit';
import { getRun, getRunResults, getViewerAdjustments, putViewerAdjustments } from '@/api/runs';
import ResultsMatrix from '@/components/ResultsMatrix';
import InsightsBar from '@/components/InsightsBar';
import TaskSummaryPanel from '@/components/TaskSummaryPanel';
import {
  mergeRunResults,
  filterExcludedFromSummary,
  buildAdjustedReportMarkdown,
  buildAdjustedReportTsv,
} from '@/lib/viewerMerge';
import type { Run, RunResult, ViewerAdjustmentPayload } from '@/types';
import { emptyViewerAdjustment } from '@/types';

type RunStatus = Run['status'];

const STATUS_THEME: Record<RunStatus, 'warning' | 'info' | 'success' | 'danger' | 'normal'> = {
  pending: 'warning',
  running: 'info',
  completed: 'success',
  failed: 'danger',
  partial: 'normal',
};

function formatDate(iso: string | null): string {
  if (!iso) return '-';
  return new Date(iso).toLocaleString();
}

function formatDuration(run: Run): string {
  if (!run.started_at) return '-';
  const end = run.finished_at ? new Date(run.finished_at) : new Date();
  const ms = end.getTime() - new Date(run.started_at).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function clonePayload(p: ViewerAdjustmentPayload): ViewerAdjustmentPayload {
  return {
    v: p.v,
    excluded_student_ids: [...p.excluded_student_ids],
    task_scores: Object.fromEntries(
      Object.entries(p.task_scores).map(([k, v]) => [k, { ...v }]),
    ),
  };
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const [run, setRun] = useState<Run | null>(null);
  const [results, setResults] = useState<RunResult[]>([]);
  const [adjustment, setAdjustment] = useState<ViewerAdjustmentPayload>(emptyViewerAdjustment());
  const [adjUpdatedAt, setAdjUpdatedAt] = useState<string | null>(null);
  const [adjActionMsg, setAdjActionMsg] = useState<string | null>(null);
  const [adjSaving, setAdjSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchRunAndResults = useCallback(async () => {
    if (!id) return;
    const [runData, resultsData] = await Promise.all([getRun(id), getRunResults(id)]);
    setRun(runData);
    setResults(resultsData);
  }, [id]);

  const fetchAdjustments = useCallback(async () => {
    if (!id) return;
    const adjRes = await getViewerAdjustments(id);
    setAdjustment(clonePayload(adjRes.payload));
    setAdjUpdatedAt(adjRes.updated_at);
  }, [id]);

  async function fetchAllInitial() {
    if (!id) return;
    try {
      await Promise.all([fetchRunAndResults(), fetchAdjustments()]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load run');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchAllInitial();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (!run) return;
    const active = run.status === 'pending' || run.status === 'running';
    if (active) {
      pollRef.current = setInterval(() => {
        fetchRunAndResults().catch(() => {});
      }, 3000);
    } else {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [run?.status, fetchRunAndResults]);

  const mergedResults = useMemo(
    () => mergeRunResults(results, adjustment),
    [results, adjustment],
  );

  const summaryResults = useMemo(
    () => filterExcludedFromSummary(mergedResults, adjustment.excluded_student_ids),
    [mergedResults, adjustment.excluded_student_ids],
  );

  const taskIds = useMemo(() => {
    if (results.length === 0) return [];
    const seen = new Set<string>();
    for (const r of results) {
      for (const t of r.tasks) seen.add(t.task_id);
    }
    return Array.from(seen).sort((a, b) => {
      const na = Number(a), nb = Number(b);
      if (!isNaN(na) && !isNaN(nb)) return na - nb;
      return a < b ? -1 : a > b ? 1 : 0;
    });
  }, [results]);

  const viewerToolsEnabled = Boolean(results.length > 0 && id);

  const handleToggleExcluded = useCallback((studentId: string) => {
    setAdjustment((prev) => {
      const ex = new Set(prev.excluded_student_ids);
      if (ex.has(studentId)) {
        ex.delete(studentId);
      } else {
        ex.add(studentId);
      }
      return { ...prev, excluded_student_ids: [...ex] };
    });
    setAdjActionMsg(null);
  }, []);

  const handleCommitTaskScore = useCallback((studentId: string, taskId: string, value: number | null) => {
    setAdjustment((prev) => {
      const ts = { ...prev.task_scores };
      const row = { ...(ts[studentId] ?? {}) };
      if (value === null) {
        delete row[taskId];
        if (Object.keys(row).length === 0) {
          delete ts[studentId];
        } else {
          ts[studentId] = row;
        }
      } else {
        row[taskId] = value;
        ts[studentId] = row;
      }
      return { ...prev, task_scores: ts };
    });
    setAdjActionMsg(null);
  }, []);

  async function handleSaveAdjustments() {
    if (!id) return;
    setAdjSaving(true);
    setAdjActionMsg(null);
    try {
      const res = await putViewerAdjustments(id, adjustment);
      setAdjustment(clonePayload(res.payload));
      setAdjUpdatedAt(res.updated_at);
      setAdjActionMsg('Saved.');
    } catch (e) {
      setAdjActionMsg(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setAdjSaving(false);
    }
  }

  async function handleResetAdjustments() {
    if (!id) return;
    const empty = emptyViewerAdjustment();
    setAdjSaving(true);
    setAdjActionMsg(null);
    try {
      const res = await putViewerAdjustments(id, empty);
      setAdjustment(clonePayload(res.payload));
      setAdjUpdatedAt(res.updated_at);
      setAdjActionMsg('Reset to defaults (saved).');
    } catch (e) {
      setAdjActionMsg(e instanceof Error ? e.message : 'Reset failed');
    } finally {
      setAdjSaving(false);
    }
  }

  async function handleCopyReport() {
    if (!id || taskIds.length === 0) return;
    const md = buildAdjustedReportMarkdown(
      mergedResults,
      taskIds,
      adjustment.excluded_student_ids,
      id,
    );
    try {
      await navigator.clipboard.writeText(md);
      setAdjActionMsg('Markdown copied to clipboard.');
    } catch {
      setAdjActionMsg('Clipboard not available.');
    }
  }

  function handleDownloadTsv() {
    if (!id || taskIds.length === 0) return;
    const tsv = buildAdjustedReportTsv(mergedResults, taskIds, adjustment.excluded_student_ids, id);
    const blob = new Blob([tsv], { type: 'text/tab-separated-values;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run-${id.slice(0, 8)}-adjusted.tsv`;
    a.click();
    URL.revokeObjectURL(url);
    setAdjActionMsg('TSV downloaded.');
  }

  if (loading) {
    return <Text color="secondary">Loading...</Text>;
  }

  if (error) {
    return <Text color="danger">{error}</Text>;
  }

  if (!run) {
    return <Text color="secondary">Run not found.</Text>;
  }

  return (
    <div>
      <Flex justifyContent="space-between" alignItems="center" style={{ marginBottom: 8 }}>
        <Text variant="header-2">Run Detail</Text>
        <Label theme={STATUS_THEME[run.status]} size="m">
          {run.status}
        </Label>
      </Flex>

      <div
        style={{
          background: 'var(--g-color-base-float)',
          borderRadius: 8,
          padding: '16px 20px',
          marginBottom: 24,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
          gap: '12px 24px',
        }}
      >
        <div>
          <Text variant="body-2" color="secondary">
            Pipeline
          </Text>
          <Text variant="body-2">{run.pipeline_name ?? run.pipeline_id}</Text>
        </div>
        <div>
          <Text variant="body-2" color="secondary">
            Homework
          </Text>
          <Text variant="body-2">{run.homework_name ?? run.homework_id}</Text>
        </div>
        <div>
          <Text variant="body-2" color="secondary">
            Inference profile
          </Text>
          <Text variant="body-2">
            {run.inference_profile_name ??
              (run.inference_profile_id ? `${run.inference_profile_id.slice(0, 8)}…` : '—')}
          </Text>
        </div>
        <div>
          <Text variant="body-2" color="secondary">
            Provider / model
          </Text>
          <Text variant="body-2">
            {run.inference_provider && run.inference_model
              ? `${run.inference_provider} / ${run.inference_model}`
              : run.inference_profile_id
                ? '(profile unavailable or deleted)'
                : '—'}
          </Text>
        </div>
        {run.inference_is_dummy ? (
          <div>
            <Text variant="body-2" color="secondary" style={{ display: 'block', marginBottom: 4 }}>
              Profile type
            </Text>
            <Label theme="warning" size="s">
              Dummy (no API calls)
            </Label>
          </div>
        ) : null}
        <div>
          <Text variant="body-2" color="secondary">
            Created
          </Text>
          <Text variant="body-2">{formatDate(run.created_at)}</Text>
        </div>
        <div>
          <Text variant="body-2" color="secondary">
            Started
          </Text>
          <Text variant="body-2">{formatDate(run.started_at)}</Text>
        </div>
        <div>
          <Text variant="body-2" color="secondary">
            Finished
          </Text>
          <Text variant="body-2">{formatDate(run.finished_at)}</Text>
        </div>
        <div>
          <Text variant="body-2" color="secondary">
            Duration
          </Text>
          <Text variant="body-2">{formatDuration(run)}</Text>
        </div>
      </div>

      {run.error_message && (
        <div
          style={{
            background: 'var(--g-color-base-danger-light)',
            border: '1px solid var(--g-color-line-danger)',
            borderRadius: 8,
            padding: '12px 16px',
            marginBottom: 24,
          }}
        >
          <Text variant="subheader-1" color="danger" style={{ display: 'block', marginBottom: 4 }}>
            Error
          </Text>
          <Text variant="body-2">{run.error_message}</Text>
        </div>
      )}

      {viewerToolsEnabled && (
        <div
          style={{
            marginBottom: 16,
            padding: '12px 16px',
            background: 'var(--g-color-base-float)',
            borderRadius: 8,
          }}
        >
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>
            Viewer adjustments
          </Text>
          <Text variant="caption-2" color="secondary" style={{ display: 'block', marginBottom: 12 }}>
            Exclude students from summaries/export; override task scores (0–1). Blur a cell to apply.
            Save persists to the server. Original run results are never modified.
          </Text>
          <Flex gap={2} wrap="wrap" alignItems="center">
            <Button view="action" size="m" disabled={adjSaving} onClick={() => handleSaveAdjustments()}>
              Save adjustments
            </Button>
            <Button view="outlined" size="m" disabled={adjSaving} onClick={() => handleResetAdjustments()}>
              Reset and save
            </Button>
            <Button view="outlined" size="m" onClick={() => handleCopyReport()}>
              Copy markdown report
            </Button>
            <Button view="outlined" size="m" onClick={() => handleDownloadTsv()}>
              Download TSV
            </Button>
            {adjUpdatedAt && (
              <Text variant="caption-1" color="secondary">
                Last saved: {formatDate(adjUpdatedAt)}
              </Text>
            )}
          </Flex>
          {adjActionMsg && (
            <Text variant="body-2" style={{ marginTop: 8 }}>
              {adjActionMsg}
            </Text>
          )}
        </div>
      )}

      <InsightsBar results={mergedResults} />
      <TaskSummaryPanel resultsForSummary={summaryResults} taskIds={taskIds} />
      <ResultsMatrix
        results={mergedResults}
        baseResults={results}
        adjustmentEnabled={viewerToolsEnabled}
        adjustment={adjustment}
        onToggleExcluded={viewerToolsEnabled ? handleToggleExcluded : undefined}
        onCommitTaskScore={viewerToolsEnabled ? handleCommitTaskScore : undefined}
      />
    </div>
  );
}
