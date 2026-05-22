import { Modal, Text, Flex } from '@gravity-ui/uikit';
import type { FileContent } from '@/types';

interface NotebookViewerProps {
  content: FileContent | null;
  open: boolean;
  onClose: () => void;
}

export default function NotebookViewer({ content, open, onClose }: NotebookViewerProps) {
  if (!content) return null;

  return (
    <Modal open={open} onClose={onClose}>
      <div style={{ padding: 24, maxWidth: 900, width: '90vw', maxHeight: '85vh', overflow: 'auto' }}>
        <Flex direction="column" gap={4}>
          <Text variant="header-2">{content.filename}</Text>

          {content.content_type === 'notebook' && content.notebook ? (
            <Flex direction="column" gap={3}>
              {content.notebook.cells.map((cell, i) => (
                <div key={i}>
                  <span style={{
                    display: 'inline-block',
                    marginBottom: 4,
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 12,
                    fontWeight: 500,
                    background: cell.cell_type === 'code'
                      ? 'var(--g-color-base-info-light)'
                      : cell.cell_type === 'markdown'
                        ? 'var(--g-color-base-positive-light)'
                        : 'var(--g-color-base-misc-light)',
                    color: 'var(--g-color-text-primary)',
                  }}>
                    {cell.cell_type}
                  </span>
                  <pre
                    style={{
                      background: cell.cell_type === 'code'
                        ? 'var(--g-color-base-float)'
                        : 'transparent',
                      padding: 12,
                      borderRadius: 6,
                      overflow: 'auto',
                      fontFamily: cell.cell_type === 'code' ? 'monospace' : 'inherit',
                      fontSize: 13,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                      border: '1px solid var(--g-color-line-generic)',
                      margin: 0,
                    }}
                  >
                    {cell.source}
                  </pre>
                </div>
              ))}
            </Flex>
          ) : (
            <pre
              style={{
                background: 'var(--g-color-base-float)',
                padding: 16,
                borderRadius: 6,
                overflow: 'auto',
                fontFamily: 'monospace',
                fontSize: 13,
                whiteSpace: 'pre-wrap',
              }}
            >
              {content.text}
            </pre>
          )}
        </Flex>
      </div>
    </Modal>
  );
}
