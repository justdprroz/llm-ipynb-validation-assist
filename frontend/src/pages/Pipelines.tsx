import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Dialog,
  Label,
  Loader,
  RadioGroup,
  Select,
  Table,
  Text,
  TextInput,
} from '@gravity-ui/uikit';
import type { Pipeline } from '@/types';
import { deletePipeline, installPipeline, listPipelines, uploadPipeline } from '@/api/pipelines';

const SOURCE_TYPES = [
  { value: 'local', content: 'Local path' },
  { value: 'whl', content: 'Wheel file (.whl)' },
  { value: 'git', content: 'Git repository' },
];

function statusLabel(status: Pipeline['status']) {
  const map: Record<Pipeline['status'], { theme: 'success' | 'danger' | 'warning'; text: string }> = {
    installed: { theme: 'success', text: 'Installed' },
    broken: { theme: 'danger', text: 'Broken' },
    pending: { theme: 'warning', text: 'Pending' },
  };
  const { theme, text } = map[status];
  return <Label theme={theme}>{text}</Label>;
}

export default function Pipelines() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [installMode, setInstallMode] = useState<'path' | 'upload'>('path');
  const [sourceType, setSourceType] = useState<string>('local');
  const [sourcePath, setSourcePath] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const [deleteTarget, setDeleteTarget] = useState<Pipeline | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listPipelines();
      setPipelines(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load pipelines');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleInstall() {
    setInstalling(true);
    setInstallError(null);
    try {
      if (installMode === 'upload') {
        if (!uploadFile) return;
        await uploadPipeline(uploadFile);
        setUploadFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        if (!sourcePath.trim()) return;
        await installPipeline({ source_type: sourceType, source_path: sourcePath.trim() });
        setSourcePath('');
      }
      await load();
    } catch (e) {
      setInstallError(e instanceof Error ? e.message : 'Install failed');
    } finally {
      setInstalling(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deletePipeline(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  const columns = [
    { id: 'name', name: 'Name', template: (row: Pipeline) => row.name },
    { id: 'version', name: 'Version', template: (row: Pipeline) => row.version },
    {
      id: 'source',
      name: 'Source',
      template: (row: Pipeline) => (
        <Text color="secondary" variant="body-1">{row.source}</Text>
      ),
    },
    {
      id: 'status',
      name: 'Status',
      template: (row: Pipeline) => statusLabel(row.status),
    },
    {
      id: 'installed_at',
      name: 'Installed',
      template: (row: Pipeline) => new Date(row.installed_at).toLocaleString(),
    },
    {
      id: 'actions',
      name: '',
      template: (row: Pipeline) => (
        <Button
          view="outlined-danger"
          size="s"
          onClick={() => setDeleteTarget(row)}
        >
          Delete
        </Button>
      ),
    },
  ];

  const installDisabled =
    installing ||
    (installMode === 'path' ? !sourcePath.trim() : !uploadFile);

  return (
    <div style={{ padding: '24px' }}>
      <Text variant="header-2" style={{ marginBottom: '24px', display: 'block' }}>
        Pipelines
      </Text>

      <div
        style={{
          marginBottom: '24px',
          padding: '16px',
          border: '1px solid var(--g-color-line-generic)',
          borderRadius: '8px',
        }}
      >
        <div style={{ marginBottom: '16px' }}>
          <RadioGroup
            value={installMode}
            onUpdate={(val) => {
              setInstallMode(val as 'path' | 'upload');
              setInstallError(null);
            }}
            options={[
              { value: 'path', content: 'Install from path' },
              { value: 'upload', content: 'Upload package' },
            ]}
          />
        </div>

        <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
          {installMode === 'path' ? (
            <>
              <div style={{ minWidth: '180px' }}>
                <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>
                  Source type
                </Text>
                <Select
                  value={[sourceType]}
                  onUpdate={(val) => setSourceType(val[0])}
                  options={SOURCE_TYPES}
                  width="max"
                />
              </div>
              <div style={{ flex: 1 }}>
                <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>
                  Source path
                </Text>
                <TextInput
                  value={sourcePath}
                  onUpdate={setSourcePath}
                  placeholder={
                    sourceType === 'git'
                      ? 'https://github.com/org/repo.git'
                      : sourceType === 'whl'
                        ? '/path/to/package.whl'
                        : '/path/to/package'
                  }
                />
              </div>
            </>
          ) : (
            <div style={{ flex: 1 }}>
              <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>
                Package file (.zip or .whl)
              </Text>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".zip,.whl"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const f = e.target.files?.[0] ?? null;
                    setUploadFile(f);
                  }}
                />
                <Button view="outlined" onClick={() => fileInputRef.current?.click()}>
                  Choose file
                </Button>
                <Text color={uploadFile ? 'primary' : 'secondary'} variant="body-1">
                  {uploadFile ? uploadFile.name : 'No file selected'}
                </Text>
              </div>
            </div>
          )}

          <Button
            view="action"
            onClick={handleInstall}
            loading={installing}
            disabled={installDisabled}
          >
            Install
          </Button>
        </div>
      </div>

      {installError && (
        <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>
          {installError}
        </Text>
      )}

      {error && (
        <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>
          {error}
        </Text>
      )}

      {loading ? (
        <Loader size="m" />
      ) : (
        <Table data={pipelines} columns={columns} />
      )}

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <Dialog.Header caption="Delete Pipeline" />
        <Dialog.Body>
          <Text>
            Delete pipeline{' '}
            <Text variant="body-2" color="primary">
              "{deleteTarget?.name}"
            </Text>
            ? This cannot be undone.
          </Text>
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonApply={handleDelete}
          onClickButtonCancel={() => setDeleteTarget(null)}
          textButtonApply="Delete"
          textButtonCancel="Cancel"
          loading={deleting}
          propsButtonApply={{ view: 'outlined-danger' }}
        />
      </Dialog>
    </div>
  );
}
