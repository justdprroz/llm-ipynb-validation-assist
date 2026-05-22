import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Button, Loader, Text, TextInput } from '@gravity-ui/uikit';
import {
  getSyncedCourse,
  importCourseAsRealm,
  syncCourse,
  type AnytaskCourseData,
  type AnytaskSyncResult,
  type RealmImportResult,
} from '@/api/anytask';

type ArtifactKey = 'course' | 'queue' | 'gradebook';

const ARTIFACT_LABELS: Record<ArtifactKey, string> = {
  course: 'Course',
  queue: 'Queue',
  gradebook: 'Gradebook',
};

function ArtifactSection({
  label,
  data,
  defaultOpen,
}: {
  label: string;
  data: object | null;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div
      style={{
        border: '1px solid var(--g-color-line-generic)',
        borderRadius: 8,
        marginBottom: 12,
        overflow: 'hidden',
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 16px',
          border: 'none',
          background: 'var(--g-color-base-float)',
          cursor: 'pointer',
          textAlign: 'left',
        }}
      >
        <Text variant="subheader-2">{label}</Text>
        <Text color="secondary">{open ? '▾' : '▸'}</Text>
      </button>
      {open && (
        <pre
          style={{
            margin: 0,
            padding: 16,
            fontSize: 12,
            lineHeight: 1.5,
            overflow: 'auto',
            maxHeight: 400,
            background: 'var(--g-color-base-background)',
          }}
        >
          {data === null ? 'Not synced' : JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}

export default function AnytaskSync() {
  const [courseId, setCourseId] = useState('');
  const [realmName, setRealmName] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<AnytaskSyncResult | null>(null);
  const [importResult, setImportResult] = useState<RealmImportResult | null>(null);
  const [data, setData] = useState<AnytaskCourseData | null>(null);

  const idTrimmed = courseId.trim();
  const realmNameTrimmed = realmName.trim();

  async function handleLoad() {
    if (!idTrimmed) return;
    setLoading(true);
    setError(null);
    try {
      setData(await getSyncedCourse(idTrimmed));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load synced data');
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSync() {
    if (!idTrimmed) return;
    setSyncing(true);
    setError(null);
    setImportResult(null);
    try {
      const result = await syncCourse(idTrimmed);
      setLastSync(result);
      setData(await getSyncedCourse(idTrimmed));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  }

  async function handleImportRealm() {
    if (!idTrimmed) return;
    setImporting(true);
    setError(null);
    setImportResult(null);
    try {
      const result = await importCourseAsRealm(
        idTrimmed,
        realmNameTrimmed || undefined,
      );
      setImportResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import as realm failed');
    } finally {
      setImporting(false);
    }
  }

  return (
    <div style={{ padding: '24px', maxWidth: 960 }}>
      <Text variant="header-2" style={{ marginBottom: 8, display: 'block' }}>
        Anytask Sync
      </Text>
      <Text color="secondary" style={{ marginBottom: 24, display: 'block' }}>
        Import course metadata, review queue, and gradebook from anytask.org via the scraper
        service. Data is stored in Storage Manager (MinIO).
      </Text>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'flex-end',
          marginBottom: 24,
        }}
      >
        <div style={{ flex: '1 1 200px', minWidth: 160 }}>
          <Text variant="body-2" style={{ marginBottom: 6, display: 'block' }}>
            Course ID
          </Text>
          <TextInput
            value={courseId}
            onUpdate={setCourseId}
            placeholder="e.g. 12345"
          />
        </div>
        <Button
          view="action"
          onClick={handleSync}
          loading={syncing}
          disabled={!idTrimmed || syncing || importing}
        >
          Sync
        </Button>
        <Button
          view="outlined"
          onClick={handleLoad}
          loading={loading}
          disabled={!idTrimmed || loading || syncing || importing}
        >
          Load
        </Button>
      </div>

      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 12,
          alignItems: 'flex-end',
          marginBottom: 24,
        }}
      >
        <div style={{ flex: '1 1 200px', minWidth: 160 }}>
          <Text variant="body-2" style={{ marginBottom: 6, display: 'block' }}>
            Realm name
          </Text>
          <TextInput
            value={realmName}
            onUpdate={setRealmName}
            placeholder="defaults to course title"
          />
        </div>
        <Button
          view="action"
          onClick={handleImportRealm}
          loading={importing}
          disabled={!idTrimmed || importing || syncing}
        >
          Import as Realm
        </Button>
      </div>

      {error && (
        <Text color="danger" style={{ marginBottom: 16, display: 'block' }}>
          {error}
        </Text>
      )}

      {importResult && (
        <Text
          color="positive"
          style={{
            marginBottom: 16,
            display: 'block',
            padding: '12px 16px',
            borderRadius: 8,
            background: 'var(--g-color-base-positive-light)',
          }}
        >
          Realm &apos;{importResult.realm_name}&apos; created — {importResult.homework_count}{' '}
          homeworks, {importResult.student_count} students.{' '}
          <Link to={`/storage-manager/${importResult.realm_id}`}>Open in Storage Manager</Link>
        </Text>
      )}

      {lastSync && (
        <Text color="secondary" style={{ marginBottom: 16, display: 'block' }}>
          Last sync: {new Date(lastSync.synced_at).toLocaleString()} — artifacts:{' '}
          {lastSync.artifacts.join(', ')}
        </Text>
      )}

      {(syncing || loading || importing) && !data && <Loader size="m" />}

      {data && (
        <div style={{ marginTop: 8 }}>
          {(Object.keys(ARTIFACT_LABELS) as ArtifactKey[]).map((key, i) => (
            <ArtifactSection
              key={key}
              label={ARTIFACT_LABELS[key]}
              data={data.artifacts[key]}
              defaultOpen={i === 0}
            />
          ))}
        </div>
      )}
    </div>
  );
}
