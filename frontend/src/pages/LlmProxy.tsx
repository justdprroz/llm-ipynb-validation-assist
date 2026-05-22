import { useEffect, useState } from 'react';
import {
  Button,
  Checkbox,
  Dialog,
  Loader,
  Table,
  Text,
  TextInput,
} from '@gravity-ui/uikit';
import type { InferenceProfile } from '@/types';
import {
  listInferenceProfiles,
  createInferenceProfile,
  deleteInferenceProfile,
} from '@/api/inferenceProfiles';

export default function LlmProxy() {
  const [profiles, setProfiles] = useState<InferenceProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [healthStatus, setHealthStatus] = useState<string>('checking…');

  const [infName, setInfName] = useState('');
  const [infProvider, setInfProvider] = useState('or');
  const [infModel, setInfModel] = useState('');
  const [infKey, setInfKey] = useState('');
  const [infYc, setInfYc] = useState('');
  const [infDesc, setInfDesc] = useState('');
  const [infDummy, setInfDummy] = useState(false);
  const [infTemp, setInfTemp] = useState('0.0');
  const [infTopP, setInfTopP] = useState('1.0');
  const [infSeed, setInfSeed] = useState('42');
  const [infEffort, setInfEffort] = useState('normal');
  const [infMaxTokens, setInfMaxTokens] = useState('');
  const [infOrProvider, setInfOrProvider] = useState('');
  const [addingInf, setAddingInf] = useState(false);
  const [addInfError, setAddInfError] = useState<string | null>(null);

  const [deleteInfTarget, setDeleteInfTarget] = useState<InferenceProfile | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setProfiles(await listInferenceProfiles());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load inference profiles');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    fetch('/health')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(() => setHealthStatus('Backend reachable'))
      .catch(() => setHealthStatus('Backend unreachable'));
  }, []);

  async function handleAddInference() {
    if (!infName.trim() || !infModel.trim() || !infKey.trim()) return;
    setAddingInf(true);
    setAddInfError(null);
    try {
      const temperature = infTemp.trim() !== '' ? parseFloat(infTemp) : undefined;
      const top_p = infTopP.trim() !== '' ? parseFloat(infTopP) : undefined;
      const seed = infSeed.trim() !== '' ? parseInt(infSeed, 10) : undefined;
      const max_tokens = infMaxTokens.trim() !== '' ? parseInt(infMaxTokens, 10) : undefined;

      let openrouter_provider: Record<string, unknown> | undefined;
      if (infOrProvider.trim()) {
        try {
          openrouter_provider = JSON.parse(infOrProvider.trim()) as Record<string, unknown>;
        } catch {
          throw new Error('OpenRouter provider must be valid JSON (e.g. {"only":["Groq"],"allow_fallbacks":true})');
        }
      }

      await createInferenceProfile({
        name: infName.trim(),
        provider: infProvider,
        model: infModel.trim(),
        api_key: infKey.trim(),
        yc_folder: infYc.trim() || undefined,
        description: infDesc.trim() || undefined,
        is_dummy: infDummy,
        temperature,
        top_p,
        seed,
        effort: infEffort.trim() || undefined,
        max_tokens,
        openrouter_provider,
      });
      setInfName('');
      setInfModel('');
      setInfKey('');
      setInfYc('');
      setInfDesc('');
      setInfDummy(false);
      setInfTemp('0.0');
      setInfTopP('1.0');
      setInfSeed('42');
      setInfEffort('normal');
      setInfMaxTokens('');
      setInfOrProvider('');
      await load();
    } catch (e) {
      setAddInfError(e instanceof Error ? e.message : 'Failed to add profile');
    } finally {
      setAddingInf(false);
    }
  }

  async function handleDeleteInference() {
    if (!deleteInfTarget) return;
    setDeleting(true);
    try {
      await deleteInferenceProfile(deleteInfTarget.id);
      setDeleteInfTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
      setDeleteInfTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  const infColumns = [
    { id: 'name', name: 'Name', template: (row: InferenceProfile) => row.name },
    { id: 'provider', name: 'Provider', template: (row: InferenceProfile) => row.provider },
    { id: 'model', name: 'Model', template: (row: InferenceProfile) => row.model },
    {
      id: 'temperature',
      name: 'Temp',
      template: (row: InferenceProfile) => row.temperature != null ? String(row.temperature) : '0.0',
    },
    {
      id: 'effort',
      name: 'Effort',
      template: (row: InferenceProfile) => row.effort ?? 'normal',
    },
    {
      id: 'api_key_preview',
      name: 'API key',
      template: (row: InferenceProfile) => (
        <Text color="secondary" variant="body-1">{row.api_key_preview}</Text>
      ),
    },
    { id: 'is_dummy', name: 'Dummy', template: (row: InferenceProfile) => (row.is_dummy ? 'yes' : '—') },
    {
      id: 'actions',
      name: '',
      template: (row: InferenceProfile) => (
        <Button view="outlined-danger" size="s" onClick={() => setDeleteInfTarget(row)}>
          Delete
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Text variant="header-1" style={{ marginBottom: '8px', display: 'block' }}>
        LLM Proxy
      </Text>
      <Text color="secondary" style={{ marginBottom: '24px', display: 'block' }}>
        Inference profiles — {healthStatus}
      </Text>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          alignItems: 'flex-end',
          marginBottom: '24px',
          padding: '16px',
          border: '1px solid var(--g-color-line-generic)',
          borderRadius: '8px',
        }}
      >
        <div style={{ flex: '1 1 140px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Name</Text>
          <TextInput value={infName} onUpdate={setInfName} placeholder="my-openrouter" />
        </div>
        <div style={{ flex: '1 1 100px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Provider</Text>
          <TextInput value={infProvider} onUpdate={setInfProvider} placeholder="or|do|yc" />
        </div>
        <div style={{ flex: '1 1 160px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Model</Text>
          <TextInput value={infModel} onUpdate={setInfModel} placeholder="model id" />
        </div>
        <div style={{ flex: '2 1 200px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>API key</Text>
          <TextInput value={infKey} onUpdate={setInfKey} placeholder="sk-..." />
        </div>
        <div style={{ flex: '1 1 80px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Temperature</Text>
          <TextInput value={infTemp} onUpdate={setInfTemp} placeholder="0.0" />
        </div>
        <div style={{ flex: '1 1 80px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Top P</Text>
          <TextInput value={infTopP} onUpdate={setInfTopP} placeholder="1.0" />
        </div>
        <div style={{ flex: '1 1 80px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Seed</Text>
          <TextInput value={infSeed} onUpdate={setInfSeed} placeholder="42" />
        </div>
        <div style={{ flex: '1 1 100px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Effort</Text>
          <TextInput value={infEffort} onUpdate={setInfEffort} placeholder="normal|high" />
        </div>
        <div style={{ flex: '1 1 100px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Max tokens</Text>
          <TextInput value={infMaxTokens} onUpdate={setInfMaxTokens} placeholder="optional" />
        </div>
        <div style={{ flex: '1 1 140px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>YC folder</Text>
          <TextInput value={infYc} onUpdate={setInfYc} placeholder="optional" />
        </div>
        <div style={{ flex: '1 1 140px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Description</Text>
          <TextInput value={infDesc} onUpdate={setInfDesc} placeholder="optional" />
        </div>
        <div style={{ flex: '2 1 240px' }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>
            OpenRouter provider JSON
          </Text>
          <TextInput
            value={infOrProvider}
            onUpdate={setInfOrProvider}
            placeholder='{"only":["Groq"],"allow_fallbacks":true}'
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', paddingBottom: '4px' }}>
          <Checkbox checked={infDummy} onUpdate={setInfDummy}>Dummy (no real API)</Checkbox>
        </div>
        <Button view="action" onClick={handleAddInference} loading={addingInf}
          disabled={!infName.trim() || !infModel.trim() || !infKey.trim() || addingInf}>Add</Button>
      </div>

      {addInfError && <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>{addInfError}</Text>}
      {error && <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>{error}</Text>}

      {loading ? <Loader size="m" /> : <Table data={profiles} columns={infColumns} />}

      <Dialog open={deleteInfTarget !== null} onClose={() => setDeleteInfTarget(null)}>
        <Dialog.Header caption="Delete inference profile" />
        <Dialog.Body>
          <Text>Delete profile <Text variant="body-2" color="primary">"{deleteInfTarget?.name}"</Text>? This cannot be undone.</Text>
        </Dialog.Body>
        <Dialog.Footer onClickButtonApply={handleDeleteInference} onClickButtonCancel={() => setDeleteInfTarget(null)}
          textButtonApply="Delete" textButtonCancel="Cancel" loading={deleting} propsButtonApply={{ view: 'outlined-danger' }} />
      </Dialog>
    </div>
  );
}
