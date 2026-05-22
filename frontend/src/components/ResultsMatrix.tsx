import { useState, Fragment, type CSSProperties, type MouseEvent } from 'react';
import { Text } from '@gravity-ui/uikit';
import type { RunResult, ViewerAdjustmentPayload } from '@/types';
import { isCellOverridden } from '@/lib/viewerMerge';

interface ResultsMatrixProps {
  results: RunResult[];
  /** Original API results (before merge) for baseline when highlighting overrides. */
  baseResults?: RunResult[];
  adjustmentEnabled?: boolean;
  adjustment?: ViewerAdjustmentPayload;
  onToggleExcluded?: (studentId: string) => void;
  onCommitTaskScore?: (studentId: string, taskId: string, value: number | null) => void;
}

function scoreColor(score: number): string {
  const r = score < 0.5 ? 255 : Math.round(255 * (1 - score) * 2);
  const g = score > 0.5 ? 255 : Math.round(255 * score * 2);
  return `rgba(${r}, ${g}, 0, 0.3)`;
}

type SortKey = 'student_id' | 'total_score' | string;
type SortDir = 'asc' | 'desc';

function baseScoreFor(
  baseResults: RunResult[] | undefined,
  studentId: string,
  taskId: string,
): number | undefined {
  if (!baseResults) return undefined;
  const r = baseResults.find((x) => x.student_id === studentId);
  const t = r?.tasks.find((x) => x.task_id === taskId);
  return t?.score;
}

export default function ResultsMatrix({
  results,
  baseResults,
  adjustmentEnabled = false,
  adjustment,
  onToggleExcluded,
  onCommitTaskScore,
}: ResultsMatrixProps) {
  const [sortKey, setSortKey] = useState<SortKey>('student_id');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (results.length === 0) {
    return <Text color="secondary">No results.</Text>;
  }

  const seen = new Set<string>();
  for (const r of results) {
    for (const t of r.tasks) seen.add(t.task_id);
  }
  const taskIds = Array.from(seen).sort((a, b) => {
    const na = Number(a), nb = Number(b);
    if (!isNaN(na) && !isNaN(nb)) return na - nb;
    return a < b ? -1 : a > b ? 1 : 0;
  });
  const excluded = new Set(adjustment?.excluded_student_ids ?? []);
  const colCount = taskIds.length + 2 + (adjustmentEnabled ? 1 : 0);

  function handleHeaderClick(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  function sortedResults(): RunResult[] {
    return [...results].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1;

      if (sortKey === 'student_id') {
        return a.student_id < b.student_id ? -dir : a.student_id > b.student_id ? dir : 0;
      }

      let av: number;
      let bv: number;

      if (sortKey === 'total_score') {
        av = a.total_score;
        bv = b.total_score;
      } else {
        av = a.tasks.find((t) => t.task_id === sortKey)?.score ?? -1;
        bv = b.tasks.find((t) => t.task_id === sortKey)?.score ?? -1;
      }

      return (av - bv) * dir;
    });
  }

  function toggleExpand(studentId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(studentId)) {
        next.delete(studentId);
      } else {
        next.add(studentId);
      }
      return next;
    });
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return null;
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function rowClick(e: MouseEvent, studentId: string) {
    if ((e.target as HTMLElement).closest('input,button,textarea,select')) {
      return;
    }
    toggleExpand(studentId);
  }

  const headerStyle: CSSProperties = {
    padding: '8px 12px',
    textAlign: 'left',
    cursor: 'pointer',
    userSelect: 'none',
    borderBottom: '2px solid var(--g-color-line-generic)',
    whiteSpace: 'nowrap',
    fontSize: 13,
    fontWeight: 600,
    color: 'var(--g-color-text-primary)',
  };

  const cellStyle: CSSProperties = {
    padding: '8px 12px',
    borderBottom: '1px solid var(--g-color-line-generic)',
    fontSize: 13,
  };

  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          borderCollapse: 'collapse',
          width: '100%',
          background: 'var(--g-color-base-float)',
          borderRadius: 8,
          overflow: 'hidden',
        }}
      >
        <thead>
          <tr>
            {adjustmentEnabled && (
              <th style={{ ...headerStyle, cursor: 'default', width: 72 }} title="Exclude from aggregates / export">
                Out
              </th>
            )}
            <th style={headerStyle} onClick={() => handleHeaderClick('student_id')}>
              Student{sortIndicator('student_id')}
            </th>
            {taskIds.map((id) => (
              <th
                key={id}
                style={{ ...headerStyle, textAlign: 'center' }}
                onClick={() => handleHeaderClick(id)}
              >
                {id}
                {sortIndicator(id)}
              </th>
            ))}
            <th
              style={{ ...headerStyle, textAlign: 'center' }}
              onClick={() => handleHeaderClick('total_score')}
            >
              Total{sortIndicator('total_score')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedResults().map((result) => {
            const isExpanded = expanded.has(result.student_id);
            const isExcluded = excluded.has(result.student_id);
            const rowMuted = adjustmentEnabled && isExcluded ? { opacity: 0.45 } : {};
            return (
              <Fragment key={result.student_id}>
                <tr style={{ cursor: 'pointer', ...rowMuted }} onClick={(e) => rowClick(e, result.student_id)}>
                  {adjustmentEnabled && adjustment && onToggleExcluded && (
                    <td
                      style={{ ...cellStyle, textAlign: 'center', cursor: 'default' }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={isExcluded}
                        title="Exclude from per-task summary and from export table"
                        aria-label={`Exclude ${result.student_id}`}
                        onChange={() => onToggleExcluded(result.student_id)}
                      />
                    </td>
                  )}
                  <td style={cellStyle}>
                    <Text variant="body-2">{result.student_id}</Text>
                  </td>
                  {taskIds.map((taskId) => {
                    const task = result.tasks.find((t) => t.task_id === taskId);
                    const score = task?.score ?? 0;
                    const overridden =
                      adjustment && isCellOverridden(adjustment, result.student_id, taskId);
                    const base = baseScoreFor(baseResults, result.student_id, taskId);
                    const showDiff =
                      overridden && base !== undefined && Math.abs(base - score) > 1e-6;

                    if (adjustmentEnabled && adjustment && onCommitTaskScore) {
                      return (
                        <td
                          key={taskId}
                          style={{
                            ...cellStyle,
                            textAlign: 'center',
                            background: scoreColor(score),
                            boxShadow: overridden ? 'inset 0 0 0 2px var(--g-color-line-brand)' : undefined,
                            cursor: 'default',
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <input
                            type="number"
                            min={0}
                            max={1}
                            step={0.01}
                            defaultValue={Number(score.toFixed(4))}
                            key={`${result.student_id}-${taskId}-${score.toFixed(4)}`}
                            title={
                              showDiff
                                ? `Original ${base?.toFixed(2)} → adjusted (blur to apply)`
                                : '0–1; blur to apply. Clear field + blur to reset override.'
                            }
                            style={{
                              width: 72,
                              padding: '4px 6px',
                              fontSize: 13,
                              borderRadius: 4,
                              border: '1px solid var(--g-color-line-generic)',
                              background: 'var(--g-color-base-background)',
                            }}
                            onBlur={(e) => {
                              const raw = e.target.value.trim();
                              if (raw === '') {
                                onCommitTaskScore(result.student_id, taskId, null);
                                return;
                              }
                              const v = Number(raw);
                              if (Number.isNaN(v)) {
                                onCommitTaskScore(result.student_id, taskId, null);
                                return;
                              }
                              onCommitTaskScore(result.student_id, taskId, Math.min(1, Math.max(0, v)));
                            }}
                          />
                        </td>
                      );
                    }

                    return (
                      <td
                        key={taskId}
                        style={{
                          ...cellStyle,
                          textAlign: 'center',
                          background: scoreColor(score),
                        }}
                      >
                        <Text variant="body-2">{score.toFixed(2)}</Text>
                      </td>
                    );
                  })}
                  <td
                    style={{
                      ...cellStyle,
                      textAlign: 'center',
                      background: scoreColor(result.total_score),
                      fontWeight: 600,
                    }}
                  >
                    <Text variant="body-2">{result.total_score.toFixed(2)}</Text>
                  </td>
                </tr>
                {isExpanded && (
                  <tr key={`${result.student_id}-detail`}>
                    <td
                      colSpan={colCount}
                      style={{
                        ...cellStyle,
                        background: 'var(--g-color-base-simple-hover)',
                        padding: '16px 20px',
                      }}
                    >
                      {result.tasks.some((t) => t.comment) && (
                        <div style={{ marginBottom: 12 }}>
                          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>
                            Task comments
                          </Text>
                          {result.tasks.filter((t) => t.comment).map((t) => (
                            <div key={t.task_id} style={{ marginBottom: 10 }}>
                              <Text variant="body-2" style={{ fontWeight: 600 }}>
                                {t.task_id} — {t.score.toFixed(2)}
                              </Text>
                              <pre
                                style={{
                                  margin: '4px 0 0 0',
                                  whiteSpace: 'pre-wrap',
                                  fontFamily: 'monospace',
                                  fontSize: 12,
                                  color: 'var(--g-color-text-primary)',
                                }}
                              >
                                {t.comment}
                              </pre>
                            </div>
                          ))}
                        </div>
                      )}
                      {result.report && (
                        <div style={{ marginBottom: 12 }}>
                          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 6 }}>
                            Report
                          </Text>
                          <pre
                            style={{
                              margin: 0,
                              whiteSpace: 'pre-wrap',
                              fontFamily: 'monospace',
                              fontSize: 12,
                              color: 'var(--g-color-text-primary)',
                            }}
                          >
                            {result.report}
                          </pre>
                        </div>
                      )}
                      {result.metadata && (
                        <div>
                          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 6 }}>
                            Metadata
                          </Text>
                          <pre
                            style={{
                              margin: 0,
                              whiteSpace: 'pre-wrap',
                              fontFamily: 'monospace',
                              fontSize: 12,
                              color: 'var(--g-color-text-primary)',
                            }}
                          >
                            {JSON.stringify(result.metadata, null, 2)}
                          </pre>
                        </div>
                      )}
                      {!result.tasks.some((t) => t.comment) && !result.report && !result.metadata && (
                        <Text color="secondary">No additional data.</Text>
                      )}
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
