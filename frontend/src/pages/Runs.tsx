import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Text, Button, Select, Label, Flex, Table } from '@gravity-ui/uikit';
import type { TableColumnConfig } from '@gravity-ui/uikit';
import { listRuns } from '@/api/runs';
import { listPipelines } from '@/api/pipelines';
import RunLauncher from '@/components/RunLauncher';
import type { Run, Pipeline } from '@/types';

type RunStatus = Run['status'];

const STATUS_THEME: Record<RunStatus, 'warning' | 'info' | 'success' | 'danger' | 'normal'> = {
  pending: 'warning',
  running: 'info',
  completed: 'success',
  failed: 'danger',
  partial: 'normal',
};

function formatDuration(run: Run): string {
  if (!run.started_at) return '-';
  const end = run.finished_at ? new Date(run.finished_at) : new Date();
  const ms = end.getTime() - new Date(run.started_at).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString();
}

const STATUS_OPTIONS = [
  { value: '', content: 'All statuses' },
  { value: 'pending', content: 'Pending' },
  { value: 'running', content: 'Running' },
  { value: 'completed', content: 'Completed' },
  { value: 'failed', content: 'Failed' },
  { value: 'partial', content: 'Partial' },
];

const COLUMNS: TableColumnConfig<Run>[] = [
  {
    id: 'pipeline_name',
    name: 'Pipeline',
    template: (run) => run.pipeline_name ?? run.pipeline_id,
  },
  {
    id: 'homework_name',
    name: 'Homework',
    template: (run) => run.homework_name ?? run.homework_id,
  },
  {
    id: 'inference',
    name: 'Inference',
    template: (run) => {
      if (run.inference_profile_name) {
        const p = run.inference_provider ?? '?';
        const m = run.inference_model ?? '?';
        const d = run.inference_is_dummy ? ' · dummy' : '';
        return `${run.inference_profile_name} (${p}/${m})${d}`;
      }
      if (run.inference_profile_id) {
        return `${run.inference_profile_id.slice(0, 8)}…`;
      }
      return '—';
    },
  },
  {
    id: 'status',
    name: 'Status',
    template: (run) => (
      <Label theme={STATUS_THEME[run.status]}>{run.status}</Label>
    ),
  },
  {
    id: 'created_at',
    name: 'Created',
    template: (run) => formatDate(run.created_at),
  },
  {
    id: 'duration',
    name: 'Duration',
    template: (run) => formatDuration(run),
  },
];

export default function Runs() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<Run[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [filterPipeline, setFilterPipeline] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [launcherOpen, setLauncherOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function fetchRuns() {
    try {
      const data = await listRuns({
        pipeline_id: filterPipeline || undefined,
        status: filterStatus || undefined,
      });
      setRuns(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    fetchRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterPipeline, filterStatus]);

  useEffect(() => {
    listPipelines().then(setPipelines).catch(() => {});
  }, []);

  useEffect(() => {
    const hasActive = runs.some((r) => r.status === 'pending' || r.status === 'running');
    if (hasActive) {
      pollRef.current = setInterval(() => {
        fetchRuns();
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs]);

  const pipelineOptions = [
    { value: '', content: 'All pipelines' },
    ...pipelines.map((p) => ({ value: p.id, content: p.name })),
  ];

  return (
    <div>
      <Flex justifyContent="space-between" alignItems="center" style={{ marginBottom: 20 }}>
        <Text variant="header-2">Runs</Text>
        <Button view="action" onClick={() => setLauncherOpen(true)}>
          New Run
        </Button>
      </Flex>

      <Flex gap={3} style={{ marginBottom: 16 }}>
        <Select
          value={filterPipeline ? [filterPipeline] : ['']}
          onUpdate={(vals) => setFilterPipeline(vals[0] === '' ? '' : vals[0])}
          options={pipelineOptions}
          width={200}
        />
        <Select
          value={filterStatus ? [filterStatus] : ['']}
          onUpdate={(vals) => setFilterStatus(vals[0] === '' ? '' : vals[0])}
          options={STATUS_OPTIONS}
          width={160}
        />
      </Flex>

      {error && (
        <Text color="danger" style={{ marginBottom: 12 }}>
          {error}
        </Text>
      )}

      {loading ? (
        <Text color="secondary">Loading...</Text>
      ) : (
        <Table
          columns={COLUMNS}
          data={runs}
          getRowId={(run) => run.id}
          onRowClick={(run) => navigate(`/runs/${run.id}`)}
        />
      )}

      <RunLauncher open={launcherOpen} onClose={() => setLauncherOpen(false)} />
    </div>
  );
}
