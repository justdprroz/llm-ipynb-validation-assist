import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Text, Flex, Loader, Button, Select } from '@gravity-ui/uikit';
import { listRuns, compareRuns } from '@/api/runs';
import type { Run, CompareResponse } from '@/types';

function scoreColor(score: number): string {
  const r = score < 0.5 ? 255 : Math.round(255 * (1 - score) * 2);
  const g = score > 0.5 ? 255 : Math.round(255 * score * 2);
  return `rgba(${r}, ${g}, 0, 0.3)`;
}

function deltaColor(a: number | null, b: number | null): string | undefined {
  if (a === null || b === null) return undefined;
  const diff = b - a;
  if (Math.abs(diff) < 0.001) return undefined;
  return diff > 0 ? 'rgba(0, 200, 80, 0.18)' : 'rgba(220, 50, 50, 0.18)';
}

function ScoreCell({ score }: { score: number | null }) {
  if (score === null) {
    return (
      <td style={{ padding: '6px 12px', textAlign: 'center', color: 'var(--g-color-text-secondary)' }}>
        —
      </td>
    );
  }
  return (
    <td
      style={{
        padding: '6px 12px',
        textAlign: 'center',
        background: scoreColor(score),
        fontVariantNumeric: 'tabular-nums',
      }}
    >
      {score.toFixed(3)}
    </td>
  );
}

interface RunSelectorProps {
  runs: Run[];
  loading: boolean;
}

function RunSelector({ runs, loading }: RunSelectorProps) {
  const navigate = useNavigate();
  const [runA, setRunA] = useState('');
  const [runB, setRunB] = useState('');

  const options = runs.map((r) => {
    const inf =
      r.inference_profile_name ??
      (r.inference_profile_id ? `${r.inference_profile_id.slice(0, 8)}…` : null);
    const infPart = inf ? ` · ${inf}` : '';
    return {
      value: r.id,
      content: `${r.pipeline_name ?? r.pipeline_id}${infPart} — ${new Date(r.created_at).toLocaleString()} [${r.id.slice(0, 8)}]`,
    };
  });

  function handleCompare() {
    if (runA && runB) {
      navigate(`/compare?run_ids=${runA},${runB}`);
    }
  }

  if (loading) {
    return (
      <Flex justifyContent="center" style={{ paddingTop: 64 }}>
        <Loader size="l" />
      </Flex>
    );
  }

  return (
    <Flex direction="column" gap={4} style={{ maxWidth: 560 }}>
      <Text variant="header-2">Compare Runs</Text>
      <Text color="secondary">Select two completed runs to compare.</Text>
      <Flex direction="column" gap={2}>
        <Text variant="subheader-2">Run A</Text>
        <Select
          options={options}
          value={runA ? [runA] : []}
          onUpdate={(vals) => setRunA(vals[0] ?? '')}
          placeholder="Select run A"
          width="max"
        />
      </Flex>
      <Flex direction="column" gap={2}>
        <Text variant="subheader-2">Run B</Text>
        <Select
          options={options}
          value={runB ? [runB] : []}
          onUpdate={(vals) => setRunB(vals[0] ?? '')}
          placeholder="Select run B"
          width="max"
        />
      </Flex>
      <Button view="action" size="m" disabled={!runA || !runB} onClick={handleCompare}>
        Compare
      </Button>
    </Flex>
  );
}

export default function Compare() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const runIdsParam = searchParams.get('run_ids');
  const runIds = runIdsParam ? runIdsParam.split(',').filter(Boolean) : [];

  const [allRuns, setAllRuns] = useState<Run[]>([]);
  const [allRunsLoading, setAllRunsLoading] = useState(true);
  const [data, setData] = useState<CompareResponse | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listRuns({ status: 'completed' })
      .then(setAllRuns)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load runs'))
      .finally(() => setAllRunsLoading(false));
  }, []);

  useEffect(() => {
    if (runIds.length < 2) return;
    setCompareLoading(true);
    setError(null);
    compareRuns(runIds.slice(0, 2))
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Comparison failed'))
      .finally(() => setCompareLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runIdsParam]);

  if (runIds.length < 2) {
    return <RunSelector runs={allRuns} loading={allRunsLoading} />;
  }

  if (compareLoading) {
    return (
      <Flex justifyContent="center" style={{ paddingTop: 64 }}>
        <Loader size="l" />
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex direction="column" gap={3}>
        <Text variant="header-2">Compare Runs</Text>
        <Text color="danger">{error}</Text>
        <Button view="normal" onClick={() => navigate('/compare')}>
          Back to selector
        </Button>
      </Flex>
    );
  }

  if (!data) return null;

  const { run_a, run_b, entries } = data;

  const allTaskIds = Array.from(
    new Set([
      ...entries.flatMap((e) => e.run_a_tasks.map((t) => t.task_id)),
      ...entries.flatMap((e) => e.run_b_tasks.map((t) => t.task_id)),
    ]),
  ).sort();

  return (
    <Flex direction="column" gap={4}>
      <Flex justifyContent="space-between" alignItems="center">
        <Text variant="header-2">Compare Runs</Text>
        <Button view="normal" size="m" onClick={() => navigate('/compare')}>
          Change runs
        </Button>
      </Flex>

      <Flex gap={6}>
        <Flex direction="column" gap={1} style={{ flex: 1 }}>
          <Text variant="subheader-2" color="secondary">Run A</Text>
          <Text variant="body-2">{run_a.pipeline_name ?? run_a.pipeline_id}</Text>
          <Text variant="body-1" color="secondary">
            {run_a.inference_profile_name
              ? `${run_a.inference_profile_name} · ${run_a.inference_provider ?? '?'}/${run_a.inference_model ?? '?'}${run_a.inference_is_dummy ? ' · dummy' : ''}`
              : run_a.inference_profile_id
                ? `Profile id ${run_a.inference_profile_id.slice(0, 8)}…`
                : 'No inference profile'}
          </Text>
          <Text variant="body-1" color="secondary">{new Date(run_a.created_at).toLocaleString()}</Text>
          <Text variant="body-1" color="secondary">{run_a.id}</Text>
        </Flex>
        <Flex direction="column" gap={1} style={{ flex: 1 }}>
          <Text variant="subheader-2" color="secondary">Run B</Text>
          <Text variant="body-2">{run_b.pipeline_name ?? run_b.pipeline_id}</Text>
          <Text variant="body-1" color="secondary">
            {run_b.inference_profile_name
              ? `${run_b.inference_profile_name} · ${run_b.inference_provider ?? '?'}/${run_b.inference_model ?? '?'}${run_b.inference_is_dummy ? ' · dummy' : ''}`
              : run_b.inference_profile_id
                ? `Profile id ${run_b.inference_profile_id.slice(0, 8)}…`
                : 'No inference profile'}
          </Text>
          <Text variant="body-1" color="secondary">{new Date(run_b.created_at).toLocaleString()}</Text>
          <Text variant="body-1" color="secondary">{run_b.id}</Text>
        </Flex>
      </Flex>

      <div style={{ overflowX: 'auto' }}>
        <table
          style={{
            borderCollapse: 'collapse',
            width: '100%',
            fontSize: 13,
            fontFamily: 'var(--g-font-family-monospace, monospace)',
          }}
        >
          <thead>
            <tr style={{ background: 'var(--g-color-base-float)' }}>
              <th style={{ padding: '8px 12px', textAlign: 'left', borderBottom: '1px solid var(--g-color-line-generic)', fontWeight: 600 }}>
                Student
              </th>
              <th style={{ padding: '8px 12px', textAlign: 'center', borderBottom: '1px solid var(--g-color-line-generic)', fontWeight: 600 }}>
                Total A
              </th>
              <th style={{ padding: '8px 12px', textAlign: 'center', borderBottom: '1px solid var(--g-color-line-generic)', fontWeight: 600 }}>
                Total B
              </th>
              <th style={{ padding: '8px 12px', textAlign: 'center', borderBottom: '1px solid var(--g-color-line-generic)', fontWeight: 600 }}>
                Delta
              </th>
              {allTaskIds.map((tid) => (
                <th
                  key={tid}
                  colSpan={2}
                  style={{ padding: '8px 12px', textAlign: 'center', borderBottom: '1px solid var(--g-color-line-generic)', fontWeight: 600 }}
                >
                  {tid}
                </th>
              ))}
            </tr>
            {allTaskIds.length > 0 && (
              <tr style={{ background: 'var(--g-color-base-float)' }}>
                <td />
                <td />
                <td />
                <td />
                {allTaskIds.map((tid) => (
                  <>
                    <td
                      key={`${tid}-a`}
                      style={{ padding: '4px 8px', textAlign: 'center', fontSize: 11, color: 'var(--g-color-text-secondary)', borderBottom: '1px solid var(--g-color-line-generic)' }}
                    >
                      A
                    </td>
                    <td
                      key={`${tid}-b`}
                      style={{ padding: '4px 8px', textAlign: 'center', fontSize: 11, color: 'var(--g-color-text-secondary)', borderBottom: '1px solid var(--g-color-line-generic)' }}
                    >
                      B
                    </td>
                  </>
                ))}
              </tr>
            )}
          </thead>
          <tbody>
            {entries.map((entry) => {
              const taskMapA = Object.fromEntries(entry.run_a_tasks.map((t) => [t.task_id, t.score]));
              const taskMapB = Object.fromEntries(entry.run_b_tasks.map((t) => [t.task_id, t.score]));
              const delta =
                entry.run_a_score !== null && entry.run_b_score !== null
                  ? entry.run_b_score - entry.run_a_score
                  : null;

              return (
                <tr key={entry.student_id} style={{ borderBottom: '1px solid var(--g-color-line-generic)' }}>
                  <td style={{ padding: '6px 12px', whiteSpace: 'nowrap' }}>{entry.student_id}</td>
                  <ScoreCell score={entry.run_a_score} />
                  <ScoreCell score={entry.run_b_score} />
                  <td
                    style={{
                      padding: '6px 12px',
                      textAlign: 'center',
                      background: deltaColor(entry.run_a_score, entry.run_b_score),
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {delta !== null ? (delta >= 0 ? '+' : '') + delta.toFixed(3) : '—'}
                  </td>
                  {allTaskIds.map((tid) => (
                    <>
                      <ScoreCell key={`${entry.student_id}-${tid}-a`} score={taskMapA[tid] ?? null} />
                      <ScoreCell key={`${entry.student_id}-${tid}-b`} score={taskMapB[tid] ?? null} />
                    </>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Flex>
  );
}
