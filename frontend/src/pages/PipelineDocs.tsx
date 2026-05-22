import React from 'react';
import { Button, Card, Text } from '@gravity-ui/uikit';

const codeStyle: React.CSSProperties = {
  display: 'block',
  background: 'var(--g-color-base-misc-light)',
  border: '1px solid var(--g-color-line-generic)',
  borderRadius: 6,
  padding: '12px 16px',
  fontFamily: 'monospace',
  fontSize: 13,
  lineHeight: 1.6,
  overflowX: 'auto',
  whiteSpace: 'pre',
  margin: '8px 0 0 0',
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: 13,
};

const thStyle: React.CSSProperties = {
  textAlign: 'left',
  padding: '8px 12px',
  background: 'var(--g-color-base-misc-light)',
  borderBottom: '1px solid var(--g-color-line-generic)',
  fontWeight: 600,
};

const tdStyle: React.CSSProperties = {
  padding: '8px 12px',
  borderBottom: '1px solid var(--g-color-line-generic)',
  verticalAlign: 'top',
};

const monoStyle: React.CSSProperties = {
  fontFamily: 'monospace',
  fontSize: 12,
  background: 'var(--g-color-base-misc-light)',
  padding: '1px 5px',
  borderRadius: 3,
};

export default function PipelineDocs() {
  return (
    <div style={{ maxWidth: 860, padding: '24px' }}>
      <Text variant="header-2" style={{ display: 'block', marginBottom: 24 }}>
        Pipeline Development Guide
      </Text>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>Overview</Text>
          <Text variant="body-1" color="secondary">
            Pipelines are standard Python packages installed into isolated virtual environments.
            GradeLab executes them as subprocesses and communicates via JSON over stdin/stdout
            using the <span style={monoStyle}>gradelab_runner</span> shim. Each pipeline must expose
            a single entry function that receives a run context and returns structured results.
          </Text>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 12 }}>Quick Start</Text>
          <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2 }}>
            <li>
              <Text variant="body-1">Download the template package below and unzip it.</Text>
            </li>
            <li>
              <Text variant="body-1">
                Implement your grading logic in <span style={monoStyle}>my_pipeline/main.py</span> inside the{' '}
                <span style={monoStyle}>run(context)</span> function.
              </Text>
            </li>
            <li>
              <Text variant="body-1">
                Install the pipeline via the Pipelines page using its local path, or package it as a{' '}
                <span style={monoStyle}>.whl</span> and upload.
              </Text>
            </li>
          </ol>
          <div style={{ marginTop: 16 }}>
            <Button
              view="action"
              size="m"
              href="/api/v1/pipelines/template"
              target="_blank"
              rel="noopener noreferrer"
            >
              Download Template
            </Button>
          </div>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>Project Structure</Text>
          <Text variant="body-1" color="secondary" style={{ display: 'block', marginBottom: 8 }}>
            A minimal GradeLab-compatible package looks like this:
          </Text>
          <pre style={codeStyle}>{`my_pipeline/
├── pyproject.toml          # PEP 517 build config
├── gradelab_manifest.json  # GradeLab metadata
└── my_pipeline/
    ├── __init__.py
    └── main.py             # Entry point`}</pre>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 12 }}>Manifest — gradelab_manifest.json</Text>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Field</th>
                <th style={thStyle}>Type</th>
                <th style={thStyle}>Required</th>
                <th style={thStyle}>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>name</code></td>
                <td style={tdStyle}>string</td>
                <td style={tdStyle}>yes</td>
                <td style={tdStyle}>Pipeline identifier. Used as venv directory name.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>version</code></td>
                <td style={tdStyle}>string</td>
                <td style={tdStyle}>yes</td>
                <td style={tdStyle}>Semver version string, e.g. <code style={monoStyle}>"0.1.0"</code>.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>entry_module</code></td>
                <td style={tdStyle}>string</td>
                <td style={tdStyle}>yes</td>
                <td style={tdStyle}>Dotted module path, e.g. <code style={monoStyle}>"my_pipeline.main"</code>.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>entry_function</code></td>
                <td style={tdStyle}>string</td>
                <td style={tdStyle}>yes</td>
                <td style={tdStyle}>Function name within the module, e.g. <code style={monoStyle}>"run"</code>.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>description</code></td>
                <td style={tdStyle}>string</td>
                <td style={tdStyle}>no</td>
                <td style={tdStyle}>Human-readable description shown in the UI.</td>
              </tr>
            </tbody>
          </table>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>RunContext — input to run()</Text>
          <Text variant="body-1" color="secondary" style={{ display: 'block', marginBottom: 8 }}>
            The <span style={monoStyle}>context</span> dict passed to your entry function contains:
          </Text>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Key</th>
                <th style={thStyle}>Type</th>
                <th style={thStyle}>Description</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>run_id</code></td>
                <td style={tdStyle}>str</td>
                <td style={tdStyle}>Unique identifier for this run.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>homework_dir</code></td>
                <td style={tdStyle}>str</td>
                <td style={tdStyle}>Path to the root of the extracted homework realm.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>students_dir</code></td>
                <td style={tdStyle}>str</td>
                <td style={tdStyle}>Path to the <code style={monoStyle}>students/</code> subdirectory within the realm.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>gold_dir</code></td>
                <td style={tdStyle}>str</td>
                <td style={tdStyle}>Path to the <code style={monoStyle}>gold/</code> subdirectory (reference solutions).</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>student_files</code></td>
                <td style={tdStyle}>list[str]</td>
                <td style={tdStyle}>Absolute paths to all student <code style={monoStyle}>.ipynb</code> files.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>scratch_dir</code></td>
                <td style={tdStyle}>str</td>
                <td style={tdStyle}>Writable directory for intermediate files. Unique per run.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>config</code></td>
                <td style={tdStyle}>dict</td>
                <td style={tdStyle}>Optional pipeline tuning (e.g. <code style={monoStyle}>effort</code>, <code style={monoStyle}>reasoning</code>, <code style={monoStyle}>retry</code>, <code style={monoStyle}>debug</code>) — reserved for future use.</td>
              </tr>
              <tr>
                <td style={tdStyle}><code style={monoStyle}>credentials</code></td>
                <td style={tdStyle}>object or null</td>
                <td style={tdStyle}>
                  Present when the run was launched with an inference profile: <code style={monoStyle}>provider</code>,{' '}
                  <code style={monoStyle}>model</code>, <code style={monoStyle}>api_key</code>, optional{' '}
                  <code style={monoStyle}>yc_folder</code>, <code style={monoStyle}>profile_id</code>,{' '}
                  <code style={monoStyle}>profile_name</code>, <code style={monoStyle}>is_dummy</code> (stub runs, no real API).
                </td>
              </tr>
            </tbody>
          </table>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>Creating a run (API)</Text>
          <Text variant="body-1" color="secondary" style={{ display: 'block', marginBottom: 8 }}>
            <code style={monoStyle}>POST /api/v1/runs</code> accepts <code style={monoStyle}>pipeline_id</code>,{' '}
            <code style={monoStyle}>homework_id</code>, and optionally <code style={monoStyle}>inference_profile_id</code>.
            When set, the resolved profile is passed as <code style={monoStyle}>credentials</code> in the context.
          </Text>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 8 }}>PipelineOutput — return value</Text>
          <Text variant="body-1" color="secondary" style={{ display: 'block', marginBottom: 8 }}>
            Your function must return a dict with the following shape:
          </Text>
          <pre style={codeStyle}>{`{
    "results": [
        {
            "student_id": str,       # filename stem, e.g. "ivanov_ivan"
            "tasks": [
                {
                    "task_id": str,      # e.g. "task_1"
                    "score": float,      # 0.0 to 1.0 normalized
                    "max_score": float,  # display value, e.g. 10.0
                    "status": str,       # "pass"|"fail"|"partial"|"error"|"skipped"
                    "comment": str|None  # optional feedback
                }
            ],
            "total_score": float,    # 0.0 to 1.0 normalized
            "report": str|None,      # optional free-text report
            "metadata": dict|None    # optional extras
        }
    ],
    "metadata": dict|None    # optional pipeline-level metadata
}`}</pre>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 12 }}>Scoring Rules</Text>
          <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 2 }}>
            <li>
              <Text variant="body-1">
                All <span style={monoStyle}>score</span> and <span style={monoStyle}>total_score</span> values
                must be in the range <span style={monoStyle}>0.0</span>–<span style={monoStyle}>1.0</span>.
              </Text>
            </li>
            <li>
              <Text variant="body-1">
                <span style={monoStyle}>max_score</span> is a cosmetic display value only (e.g. <span style={monoStyle}>10.0</span>).
                GradeLab does not use it for normalization.
              </Text>
            </li>
            <li>
              <Text variant="body-1">
                <span style={monoStyle}>student_id</span> must equal the filename stem of the notebook,
                e.g. file <span style={monoStyle}>ivanov_ivan.ipynb</span> → id{' '}
                <span style={monoStyle}>ivanov_ivan</span>. This is the join key across all tables.
              </Text>
            </li>
            <li>
              <Text variant="body-1">
                <span style={monoStyle}>task_id</span> values are pipeline-defined but must be consistent
                across all students within a single run to enable per-task comparisons.
              </Text>
            </li>
          </ul>
        </Card>

        <Card style={{ padding: '20px 24px' }}>
          <Text variant="subheader-2" style={{ display: 'block', marginBottom: 12 }}>Download Template</Text>
          <Text variant="body-1" color="secondary" style={{ display: 'block', marginBottom: 16 }}>
            Download a ready-to-use skeleton package with all required files and a documented stub
            for the <span style={monoStyle}>run()</span> function.
          </Text>
          <Button
            view="action"
            size="l"
            href="/api/v1/pipelines/template"
            target="_blank"
            rel="noopener noreferrer"
          >
            Download gradelab_pipeline_template.zip
          </Button>
        </Card>

      </div>
    </div>
  );
}
