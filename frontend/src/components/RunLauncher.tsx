import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Modal, Button, Select, Text, Flex } from '@gravity-ui/uikit';
import { getPipelineRunDefaults } from '@/api/meta';
import { listInferenceProfiles } from '@/api/inferenceProfiles';
import { listPipelines } from '@/api/pipelines';
import { listRealms } from '@/api/realms';
import { createRun } from '@/api/runs';
import type { Pipeline, Realm, Homework, InferenceProfile } from '@/types';

interface RunLauncherProps {
  open: boolean;
  onClose: () => void;
}

/** Mirrors ``PIPELINE_RUN_CONFIG_DEFAULTS`` when the meta endpoint is unreachable. */
const FALLBACK_PIPELINE_DEFAULTS: Record<string, unknown> = {
  debug: false,
  retry: 3,
  concurrency: 8,
};

export default function RunLauncher({ open, onClose }: RunLauncherProps) {
  const navigate = useNavigate();

  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [realms, setRealms] = useState<Realm[]>([]);
  const [selectedPipelineId, setSelectedPipelineId] = useState<string>('');
  const [selectedRealmId, setSelectedRealmId] = useState<string>('');
  const [selectedHomeworkId, setSelectedHomeworkId] = useState<string>('');
  const [inferenceProfiles, setInferenceProfiles] = useState<InferenceProfile[]>([]);
  const [selectedInferenceProfileId, setSelectedInferenceProfileId] = useState<string>('');
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pipelineConfigText, setPipelineConfigText] = useState(() =>
    JSON.stringify(FALLBACK_PIPELINE_DEFAULTS, null, 2),
  );
  const [pipelineConfigHint, setPipelineConfigHint] = useState<string>('');

  useEffect(() => {
    if (!open) return;
    setSelectedPipelineId('');
    setSelectedRealmId('');
    setSelectedHomeworkId('');
    setSelectedInferenceProfileId('');
    setError(null);
    setPipelineConfigText(JSON.stringify(FALLBACK_PIPELINE_DEFAULTS, null, 2));
    setPipelineConfigHint('');

    Promise.all([
      listPipelines(),
      listRealms(),
      listInferenceProfiles(),
      getPipelineRunDefaults().catch(() => null),
    ]).then(([pl, rl, ip, meta]) => {
      setPipelines(pl.filter((p) => p.status === 'installed'));
      setRealms(rl);
      setInferenceProfiles(ip);
      if (meta) {
        setPipelineConfigText(JSON.stringify(meta.defaults, null, 2));
        setPipelineConfigHint(meta.description);
      }
    });
  }, [open]);

  const selectedRealm: Realm | undefined = realms.find((r) => r.id === selectedRealmId);
  const homeworks: Homework[] = selectedRealm?.homeworks ?? [];

  const canLaunch = !!selectedPipelineId && !!selectedHomeworkId && !launching;

  async function handleLaunch() {
    if (!canLaunch) return;
    setLaunching(true);
    setError(null);
    try {
      const trimmed = pipelineConfigText.trim();
      let pipelineConfig: Record<string, unknown> | undefined;
      if (trimmed) {
        let parsed: unknown;
        try {
          parsed = JSON.parse(trimmed);
        } catch {
          throw new Error('Pipeline config is not valid JSON');
        }
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error('Pipeline config must be a JSON object');
        }
        pipelineConfig = parsed as Record<string, unknown>;
      }

      const pl = pipelines.find((p) => p.id === selectedPipelineId);
      const run = await createRun(
        selectedPipelineId,
        selectedHomeworkId,
        selectedInferenceProfileId || null,
        pl?.name,
        pl?.version,
        pipelineConfig,
      );
      onClose();
      navigate(`/runs/${run.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Launch failed');
      setLaunching(false);
    }
  }

  const pipelineOptions = pipelines.map((p) => ({
    value: p.id,
    content: `${p.name} v${p.version}`,
  }));

  const realmOptions = realms.map((r) => ({
    value: r.id,
    content: r.name,
  }));

  const homeworkOptions = homeworks.map((hw) => ({
    value: hw.id,
    content: hw.name,
  }));

  const inferenceOptions = [
    { value: '', content: 'None' },
    ...inferenceProfiles.map((p) => ({
      value: p.id,
      content: `${p.name}${p.is_dummy ? ' (dummy)' : ''}`,
    })),
  ];

  return (
    <Modal open={open} onClose={onClose}>
      <div style={{ padding: 24, minWidth: 520 }}>
        <Text variant="header-2" style={{ display: 'block', marginBottom: 20 }}>
          New Run
        </Text>

        <Flex direction="column" gap={4}>
          <Flex direction="column" gap={1}>
            <Text variant="subheader-1">Pipeline</Text>
            <Select
              value={selectedPipelineId ? [selectedPipelineId] : []}
              onUpdate={(vals) => setSelectedPipelineId(vals[0] ?? '')}
              options={pipelineOptions}
              placeholder="Select pipeline..."
              width="max"
              disabled={pipelineOptions.length === 0}
            />
            {pipelineOptions.length === 0 && (
              <Text variant="body-2" color="secondary">
                No installed pipelines.
              </Text>
            )}
          </Flex>

          <Flex direction="column" gap={1}>
            <Text variant="subheader-1">Realm</Text>
            <Select
              value={selectedRealmId ? [selectedRealmId] : []}
              onUpdate={(vals) => {
                setSelectedRealmId(vals[0] ?? '');
                setSelectedHomeworkId('');
              }}
              options={realmOptions}
              placeholder="Select realm..."
              width="max"
              disabled={realmOptions.length === 0}
            />
          </Flex>

          <Flex direction="column" gap={1}>
            <Text variant="subheader-1">Homework</Text>
            <Select
              value={selectedHomeworkId ? [selectedHomeworkId] : []}
              onUpdate={(vals) => setSelectedHomeworkId(vals[0] ?? '')}
              options={homeworkOptions}
              placeholder="Select homework..."
              width="max"
              disabled={!selectedRealmId || homeworkOptions.length === 0}
            />
          </Flex>

          <Flex direction="column" gap={1}>
            <Text variant="subheader-1">Inference profile (optional)</Text>
            <Select
              value={selectedInferenceProfileId ? [selectedInferenceProfileId] : ['']}
              onUpdate={(vals) => setSelectedInferenceProfileId(vals[0] === '' ? '' : (vals[0] ?? ''))}
              options={inferenceOptions}
              placeholder="None"
              width="max"
            />
          </Flex>

          <details style={{ marginTop: 4 }}>
            <summary style={{ cursor: 'pointer', fontWeight: 500 }}>Advanced pipeline config (JSON) — operational only</summary>
            {pipelineConfigHint ? (
              <Text variant="body-2" color="secondary" style={{ display: 'block', marginTop: 8 }}>
                {pipelineConfigHint}
              </Text>
            ) : null}
            <textarea
              value={pipelineConfigText}
              onChange={(e) => setPipelineConfigText(e.target.value)}
              spellCheck={false}
              rows={14}
              style={{
                width: '100%',
                marginTop: 8,
                fontFamily: 'ui-monospace, monospace',
                fontSize: 13,
                padding: 10,
                boxSizing: 'border-box',
              }}
            />
          </details>

          {error && (
            <Text color="danger" variant="body-2">
              {error}
            </Text>
          )}

          <Flex gap={3} justifyContent="flex-end">
            <Button view="flat" onClick={onClose} disabled={launching}>
              Cancel
            </Button>
            <Button view="action" onClick={handleLaunch} disabled={!canLaunch} loading={launching}>
              Launch
            </Button>
          </Flex>
        </Flex>
      </div>
    </Modal>
  );
}
