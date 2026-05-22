import { Card, Text, Flex } from '@gravity-ui/uikit';
import type { RunResult } from '@/types';

interface InsightsBarProps {
  results: RunResult[];
}

interface StatCardProps {
  label: string;
  value: string | number;
}

function StatCard({ label, value }: StatCardProps) {
  return (
    <Card style={{ padding: '16px 24px', minWidth: 140 }}>
      <Flex direction="column" gap={1}>
        <Text variant="body-2" color="secondary">
          {label}
        </Text>
        <Text variant="header-1">{value}</Text>
      </Flex>
    </Card>
  );
}

function taskAverages(results: RunResult[]): Record<string, number> {
  const sums: Record<string, number> = {};
  const counts: Record<string, number> = {};

  for (const result of results) {
    for (const task of result.tasks) {
      sums[task.task_id] = (sums[task.task_id] ?? 0) + task.score;
      counts[task.task_id] = (counts[task.task_id] ?? 0) + 1;
    }
  }

  const avgs: Record<string, number> = {};
  for (const id of Object.keys(sums)) {
    avgs[id] = sums[id] / counts[id];
  }
  return avgs;
}

export default function InsightsBar({ results }: InsightsBarProps) {
  if (results.length === 0) {
    return null;
  }

  const totalStudents = results.length;
  const avgScore = results.reduce((sum, r) => sum + r.total_score, 0) / totalStudents;
  const belowThreshold = results.filter((r) => r.total_score < 0.5).length;

  const avgs = taskAverages(results);
  const taskIds = Object.keys(avgs);

  let hardestTask = '-';
  let easiestTask = '-';

  if (taskIds.length > 0) {
    hardestTask = taskIds.reduce((a, b) => (avgs[a] < avgs[b] ? a : b));
    easiestTask = taskIds.reduce((a, b) => (avgs[a] > avgs[b] ? a : b));
  }

  return (
    <Flex gap={3} wrap="wrap" style={{ marginBottom: 24 }}>
      <StatCard label="Students" value={totalStudents} />
      <StatCard label="Avg Score" value={avgScore.toFixed(2)} />
      <StatCard label="Hardest Task" value={hardestTask} />
      <StatCard label="Easiest Task" value={easiestTask} />
      <StatCard label="Below 0.5" value={belowThreshold} />
    </Flex>
  );
}
