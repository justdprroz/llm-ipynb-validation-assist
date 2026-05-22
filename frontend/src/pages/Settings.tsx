import { useEffect, useState } from 'react';
import {
  Button,
  Dialog,
  Loader,
  Table,
  Text,
  TextInput,
} from '@gravity-ui/uikit';
import type { GitCredential } from '@/types';
import { listCredentials, createCredential, deleteCredential } from '@/api/credentials';

export default function Settings() {
  const [credentials, setCredentials] = useState<GitCredential[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [host, setHost] = useState('');
  const [token, setToken] = useState('');
  const [description, setDescription] = useState('');
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<GitCredential | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setCredentials(await listCredentials());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleAdd() {
    if (!host.trim() || !token.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      await createCredential({
        host: host.trim(),
        token: token.trim(),
        description: description.trim() || undefined,
      });
      setHost('');
      setToken('');
      setDescription('');
      await load();
    } catch (e) {
      setAddError(e instanceof Error ? e.message : 'Failed to add credential');
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteCredential(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  const gitColumns = [
    { id: 'host', name: 'Host', template: (row: GitCredential) => row.host },
    {
      id: 'token_preview',
      name: 'Token',
      template: (row: GitCredential) => (
        <Text color="secondary" variant="body-1">{row.token_preview}</Text>
      ),
    },
    { id: 'description', name: 'Description', template: (row: GitCredential) => row.description ?? '—' },
    { id: 'created_at', name: 'Created', template: (row: GitCredential) => new Date(row.created_at).toLocaleString() },
    {
      id: 'actions',
      name: '',
      template: (row: GitCredential) => (
        <Button view="outlined-danger" size="s" onClick={() => setDeleteTarget(row)}>
          Delete
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <Text variant="header-1" style={{ marginBottom: '24px', display: 'block' }}>
        Settings
      </Text>

      <Text variant="header-2" style={{ marginBottom: '16px', display: 'block' }}>
        Git Credentials
      </Text>

      <div
        style={{
          display: 'flex',
          gap: '12px',
          alignItems: 'flex-end',
          marginBottom: '24px',
          padding: '16px',
          border: '1px solid var(--g-color-line-generic)',
          borderRadius: '8px',
        }}
      >
        <div style={{ flex: 1 }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Host</Text>
          <TextInput value={host} onUpdate={setHost} placeholder="github.com" />
        </div>
        <div style={{ flex: 2 }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Token</Text>
          <TextInput value={token} onUpdate={setToken} placeholder="ghp_..." />
        </div>
        <div style={{ flex: 1 }}>
          <Text variant="body-2" style={{ marginBottom: '6px', display: 'block' }}>Description</Text>
          <TextInput value={description} onUpdate={setDescription} placeholder="optional" />
        </div>
        <Button view="action" onClick={handleAdd} loading={adding} disabled={!host.trim() || !token.trim() || adding}>
          Add
        </Button>
      </div>

      {addError && (
        <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>{addError}</Text>
      )}
      {error && (
        <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>{error}</Text>
      )}

      {loading ? <Loader size="m" /> : <Table data={credentials} columns={gitColumns} />}

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <Dialog.Header caption="Delete Credential" />
        <Dialog.Body>
          <Text>
            Delete credential for{' '}
            <Text variant="body-2" color="primary">"{deleteTarget?.host}"</Text>? This cannot be undone.
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
