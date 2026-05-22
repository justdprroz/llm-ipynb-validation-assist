import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Text, Flex, Card, Loader, Label, Button } from '@gravity-ui/uikit';
import { listRealms } from '@/api/realms';
import { listPipelines } from '@/api/pipelines';
import { listRuns } from '@/api/runs';
import type { Realm, Pipeline, Run } from '@/types';

function statusTheme(status: Run['status']): 'info' | 'success' | 'danger' | 'warning' | 'normal' {
  switch (status) {
    case 'completed': return 'success';
    case 'failed': return 'danger';
    case 'running': return 'info';
    case 'partial': return 'warning';
    default: return 'normal';
  }
}

export default function Dashboard() {
  const [realms, setRealms] = useState<Realm[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listRealms(), listPipelines(), listRuns()])
      .then(([r, p, ru]) => {
        setRealms(r);
        setPipelines(p);
        setRuns(ru);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : 'Failed to load data'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <Flex justifyContent="center" style={{ paddingTop: 64 }}>
        <Loader size="l" />
      </Flex>
    );
  }

  if (error) {
    return (
      <Flex direction="column" gap={3}>
        <Text variant="header-2">Dashboard</Text>
        <Text color="danger">{error}</Text>
      </Flex>
    );
  }

  const completed = runs.filter((r) => r.status === 'completed').length;
  const failed = runs.filter((r) => r.status === 'failed').length;
  const recent = [...runs]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  const summaryCards = [
    { label: 'Realms', value: realms.length },
    { label: 'Pipelines', value: pipelines.length },
    { label: 'Total Runs', value: runs.length },
    { label: 'Completed', value: completed },
    { label: 'Failed', value: failed },
  ];

  return (
    <Flex direction="column" gap={6}>
      <Flex justifyContent="space-between" alignItems="center">
        <Text variant="header-2">Dashboard</Text>
        <Link to="/runs" style={{ textDecoration: 'none' }}>
          <Button view="action" size="m">
            New Run
          </Button>
        </Link>
      </Flex>

      <Flex gap={4} wrap="wrap">
        {summaryCards.map((card) => (
          <Card key={card.label} style={{ padding: '20px 28px', minWidth: 120, textAlign: 'center' }}>
            <Text variant="display-2" color="primary">
              {card.value}
            </Text>
            <Text variant="body-1" color="secondary">
              {card.label}
            </Text>
          </Card>
        ))}
      </Flex>

      <Flex direction="column" gap={3}>
        <Text variant="header-1">Recent Runs</Text>
        {recent.length === 0 ? (
          <Text color="secondary">No runs yet.</Text>
        ) : (
          <Flex direction="column" gap={2}>
            {recent.map((run) => (
              <Card key={run.id} style={{ padding: '12px 16px' }}>
                <Flex justifyContent="space-between" alignItems="center">
                  <Flex direction="column" gap={1}>
                    <Text variant="body-2" color="primary">
                      <Link to={`/runs/${run.id}`} style={{ color: 'inherit', textDecoration: 'none' }}>
                        {run.id}
                      </Link>
                    </Text>
                    <Text variant="body-1" color="secondary">
                      Pipeline: {run.pipeline_name ?? run.pipeline_id}
                    </Text>
                    <Text variant="body-1" color="secondary">
                      Inference:{' '}
                      {run.inference_profile_name
                        ? `${run.inference_profile_name} (${run.inference_provider ?? '?'}/${run.inference_model ?? '?'})`
                        : run.inference_profile_id
                          ? `${run.inference_profile_id.slice(0, 8)}…`
                          : '—'}
                    </Text>
                    <Text variant="body-1" color="secondary">
                      {new Date(run.created_at).toLocaleString()}
                    </Text>
                  </Flex>
                  <Label theme={statusTheme(run.status)}>{run.status}</Label>
                </Flex>
              </Card>
            ))}
          </Flex>
        )}
      </Flex>
    </Flex>
  );
}
