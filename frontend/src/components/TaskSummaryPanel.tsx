import type { CSSProperties } from 'react';
import { Text } from '@gravity-ui/uikit';
import type { RunResult } from '@/types';
import { computeTaskColumnStats } from '@/lib/viewerMerge';

interface TaskSummaryPanelProps {
  /** Already merged + filtered (excluded students removed) for aggregates. */
  resultsForSummary: RunResult[];
  taskIds: string[];
}

export default function TaskSummaryPanel({ resultsForSummary, taskIds }: TaskSummaryPanelProps) {
  if (taskIds.length === 0 || resultsForSummary.length === 0) {
    return null;
  }

  const stats = computeTaskColumnStats(resultsForSummary, taskIds);

  const th: CSSProperties = {
    padding: '8px 12px',
    textAlign: 'left',
    borderBottom: '2px solid var(--g-color-line-generic)',
    fontSize: 12,
    fontWeight: 600,
  };
  const td: CSSProperties = {
    padding: '8px 12px',
    borderBottom: '1px solid var(--g-color-line-generic)',
    fontSize: 13,
  };

  return (
    <div style={{ marginBottom: 24 }}>
      <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>
        Per-task summary
      </Text>
      <Text variant="caption-2" color="secondary" style={{ display: 'block', marginBottom: 12 }}>
        Based on students not excluded from aggregates. Mean and pass rate use effective scores
        (0–1). Pass rate = share with score ≥ 1. Error counts use original task status = error.
      </Text>
      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            borderCollapse: 'collapse',
            width: '100%',
            maxWidth: 960,
            background: 'var(--g-color-base-float)',
            borderRadius: 8,
            overflow: 'hidden',
          }}
        >
          <thead>
            <tr>
              <th style={th}>Task</th>
              <th style={{ ...th, textAlign: 'right' }}>n</th>
              <th style={{ ...th, textAlign: 'right' }}>Mean</th>
              <th style={{ ...th, textAlign: 'right' }}>Pass rate</th>
              <th style={{ ...th, textAlign: 'right' }}>Pass</th>
              <th style={{ ...th, textAlign: 'right' }}>Partial</th>
              <th style={{ ...th, textAlign: 'right' }}>Fail</th>
              <th style={{ ...th, textAlign: 'right' }}>Error</th>
            </tr>
          </thead>
          <tbody>
            {stats.map((row) => (
              <tr key={row.task_id}>
                <td style={td}>
                  <Text variant="body-2">{row.task_id}</Text>
                </td>
                <td style={{ ...td, textAlign: 'right' }}>{row.n}</td>
                <td style={{ ...td, textAlign: 'right' }}>{row.mean.toFixed(2)}</td>
                <td style={{ ...td, textAlign: 'right' }}>{(row.pass_rate * 100).toFixed(0)}%</td>
                <td style={{ ...td, textAlign: 'right' }}>{row.pass}</td>
                <td style={{ ...td, textAlign: 'right' }}>{row.partial}</td>
                <td style={{ ...td, textAlign: 'right' }}>{row.fail}</td>
                <td style={{ ...td, textAlign: 'right' }}>{row.error}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
