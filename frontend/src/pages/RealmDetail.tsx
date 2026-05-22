import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Button, Loader, Text } from '@gravity-ui/uikit';
import type { FileContent, FileEntry, Homework, Realm } from '@/types';
import { getHomework, getHomeworkFile, getRealm, uploadGoldFile } from '@/api/realms';
import NotebookViewer from '@/components/NotebookViewer';

interface HomeworkDetail extends Homework {
  student_files: FileEntry[];
  gold_files: FileEntry[];
}

function HomeworkCard({
  realmId,
  hw,
  onOpenFile,
  onRefreshRealm,
}: {
  realmId: string;
  hw: Homework;
  onOpenFile: (realmId: string, hwId: string, filePath: string) => void;
  onRefreshRealm: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [detail, setDetail] = useState<HomeworkDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function toggleExpand() {
    if (expanded) {
      setExpanded(false);
      return;
    }
    setExpanded(true);
    if (detail) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getHomework(realmId, hw.id);
      setDetail(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load homework');
    } finally {
      setLoading(false);
    }
  }

  async function handleGoldFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';
    setUploading(true);
    setUploadError(null);
    try {
      await uploadGoldFile(realmId, hw.id, file);
      setDetail(null);
      const data = await getHomework(realmId, hw.id);
      setDetail(data);
      onRefreshRealm();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  return (
    <div
      style={{
        padding: '16px',
        border: '1px solid var(--g-color-line-generic)',
        borderRadius: 8,
        background: 'var(--g-color-base-background)',
      }}
    >
      <div
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={toggleExpand}
      >
        <Text variant="subheader-2">{hw.name} {expanded ? '▾' : '▸'}</Text>
        <div style={{ display: 'flex', gap: '24px' }}>
          <Text color="secondary">
            Students: <Text variant="body-2">{hw.student_count}</Text>
          </Text>
          <Text color="secondary">
            Gold: <Text variant="body-2">{hw.gold_count}</Text>
          </Text>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: '16px' }}>
          {loading && <Loader size="s" />}
          {error && <Text color="danger">{error}</Text>}
          {detail && (
            <div style={{ display: 'flex', gap: '32px' }}>
              <div style={{ flex: 1 }}>
                <Text variant="body-2" color="secondary" style={{ marginBottom: '8px', display: 'block' }}>
                  Student files ({detail.student_files.length})
                </Text>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {detail.student_files.map((file) => (
                    <Button
                      key={file.path}
                      view="flat"
                      size="s"
                      onClick={() => onOpenFile(realmId, hw.id, file.path)}
                    >
                      {file.name}
                    </Button>
                  ))}
                  {detail.student_files.length === 0 && (
                    <Text color="secondary">None</Text>
                  )}
                </div>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: '8px' }}>
                  <Text variant="body-2" color="secondary">
                    Gold files ({detail.gold_files.length})
                  </Text>
                  <Button
                    view="outlined"
                    size="xs"
                    disabled={uploading}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    {uploading ? 'Uploading...' : 'Upload gold...'}
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".ipynb"
                    style={{ display: 'none' }}
                    onChange={handleGoldFileSelected}
                  />
                </div>
                {uploadError && (
                  <Text color="danger" style={{ display: 'block', marginBottom: 4, fontSize: 12 }}>
                    {uploadError}
                  </Text>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {detail.gold_files.map((file) => (
                    <Button
                      key={file.path}
                      view="flat"
                      size="s"
                      onClick={() => onOpenFile(realmId, hw.id, file.path)}
                    >
                      {file.name}
                    </Button>
                  ))}
                  {detail.gold_files.length === 0 && (
                    <Text color="secondary">None</Text>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function RealmDetail() {
  const { id } = useParams<{ id: string }>();
  const [realm, setRealm] = useState<Realm | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<FileContent | null>(null);
  const [fileLoading, setFileLoading] = useState(false);

  function fetchRealm() {
    if (!id) return;
    getRealm(id)
      .then(setRealm)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load realm'));
  }

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setError(null);
    getRealm(id)
      .then(setRealm)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load realm'))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleOpenFile(realmId: string, hwId: string, filePath: string) {
    setFileLoading(true);
    try {
      const content = await getHomeworkFile(realmId, hwId, filePath);
      setViewingFile(content);
    } finally {
      setFileLoading(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: '24px' }}>
        <Loader size="m" />
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '24px' }}>
        <Text color="danger">{error}</Text>
      </div>
    );
  }

  if (!realm) return null;

  return (
    <div style={{ padding: '24px' }}>
      <Text variant="header-2" style={{ marginBottom: '8px', display: 'block' }}>
        {realm.name}
      </Text>
      <Text color="secondary" style={{ marginBottom: '24px', display: 'block' }}>
        Created {new Date(realm.created_at).toLocaleString()}
      </Text>

      <Text variant="subheader-3" style={{ marginBottom: '16px', display: 'block' }}>
        Homeworks ({realm.homeworks.length})
      </Text>

      {fileLoading && (
        <div style={{ marginBottom: '12px' }}>
          <Loader size="s" />
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {realm.homeworks.length === 0 && (
          <Text color="secondary">No homeworks in this realm.</Text>
        )}
        {realm.homeworks.map((hw) => (
          <HomeworkCard key={hw.id} realmId={realm.id} hw={hw} onOpenFile={handleOpenFile} onRefreshRealm={fetchRealm} />
        ))}
      </div>

      <NotebookViewer
        content={viewingFile}
        open={viewingFile !== null}
        onClose={() => setViewingFile(null)}
      />
    </div>
  );
}
