import { useEffect, useRef, useState } from 'react';
import {
  Button,
  Dialog,
  Loader,
  Table,
  Text,
  TextInput,
} from '@gravity-ui/uikit';
import type { Realm } from '@/types';
import { deleteRealm, listRealms, uploadRealm } from '@/api/realms';
import { useNavigate } from 'react-router-dom';

export default function Realms() {
  const [realms, setRealms] = useState<Realm[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadName, setUploadName] = useState('');
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [deleteTarget, setDeleteTarget] = useState<Realm | null>(null);
  const [deleting, setDeleting] = useState(false);

  const navigate = useNavigate();

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listRealms();
      setRealms(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load realms');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleUpload() {
    if (!uploadFile || !uploadName.trim()) return;
    setUploading(true);
    setUploadError(null);
    try {
      await uploadRealm(uploadFile, uploadName.trim());
      setUploadOpen(false);
      setUploadName('');
      setUploadFile(null);
      await load();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteRealm(deleteTarget.id);
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
    {
      id: 'name',
      name: 'Name',
      template: (row: Realm) => (
        <Button
          view="flat"
          onClick={() => navigate(`/realms/${row.id}`)}
        >
          {row.name}
        </Button>
      ),
    },
    {
      id: 'homework_count',
      name: 'Homeworks',
      template: (row: Realm) => String(row.homeworks.length),
    },
    {
      id: 'created_at',
      name: 'Created',
      template: (row: Realm) => new Date(row.created_at).toLocaleString(),
    },
    {
      id: 'actions',
      name: '',
      template: (row: Realm) => (
        <Button
          view="outlined-danger"
          size="s"
          onClick={(e) => {
            e.stopPropagation();
            setDeleteTarget(row);
          }}
        >
          Delete
        </Button>
      ),
    },
  ];

  return (
    <div style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px' }}>
        <Text variant="header-2">Realms</Text>
        <Button view="action" onClick={() => setUploadOpen(true)}>
          Upload Realm
        </Button>
      </div>

      {error && (
        <Text color="danger" style={{ marginBottom: '16px', display: 'block' }}>
          {error}
        </Text>
      )}

      {loading ? (
        <Loader size="m" />
      ) : (
        <Table data={realms} columns={columns} />
      )}

      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)}>
        <Dialog.Header caption="Upload Realm" />
        <Dialog.Body>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minWidth: '360px' }}>
            <TextInput
              label="Realm name"
              value={uploadName}
              onUpdate={setUploadName}
              placeholder="e.g. homework-2024"
            />
            <div>
              <Button
                view="outlined"
                onClick={() => fileInputRef.current?.click()}
              >
                {uploadFile ? uploadFile.name : 'Choose file (.zip / .tar.gz)'}
              </Button>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip,.tar,.tar.gz,.tgz"
                style={{ display: 'none' }}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) setUploadFile(f);
                }}
              />
            </div>
            {uploadError && (
              <Text color="danger">{uploadError}</Text>
            )}
          </div>
        </Dialog.Body>
        <Dialog.Footer
          onClickButtonApply={handleUpload}
          onClickButtonCancel={() => setUploadOpen(false)}
          textButtonApply="Upload"
          textButtonCancel="Cancel"
          loading={uploading}
          propsButtonApply={{ disabled: !uploadFile || !uploadName.trim() || uploading }}
        />
      </Dialog>

      <Dialog open={deleteTarget !== null} onClose={() => setDeleteTarget(null)}>
        <Dialog.Header caption="Delete Realm" />
        <Dialog.Body>
          <Text>
            Delete realm <Text variant="body-2" color="primary">"{deleteTarget?.name}"</Text>?
            This cannot be undone.
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
