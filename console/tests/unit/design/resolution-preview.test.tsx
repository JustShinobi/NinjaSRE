import { render, screen } from '@testing-library/react';
import { act } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  EffectiveFieldsTable,
  patchOf,
  ResolutionPreview,
  useConfigWrite,
} from '@/design/resolution-preview';

/**
 * The shared patch → preview → apply machinery every settings page in this
 * group edits through, proved once here rather than three times.
 *
 * `patchOf` grows the nested document a closed schema demands from flat
 * dotted paths — the same reasoning `first-run/model.tsx`'s own `patchOf`
 * states: a flat key is a field the schema has never heard of. `useConfigWrite`
 * is the state machine every page's save button is gated by: no save exists
 * until a preview of exactly the pending change has come back, because a save
 * that could run without a preview would make the preview decoration.
 */

describe('patchOf', () => {
  it('nests a single dotted path', () => {
    expect(patchOf([['models.investigator.provider', 'anthropic']])).toEqual({
      models: { investigator: { provider: 'anthropic' } },
    });
  });

  it('merges several paths that share a prefix into one document', () => {
    expect(
      patchOf([
        ['models.investigator.provider', 'anthropic'],
        ['models.investigator.model', 'claude-sonnet-5'],
        ['models.subagent.provider', 'anthropic'],
      ]),
    ).toEqual({
      models: {
        investigator: { provider: 'anthropic', model: 'claude-sonnet-5' },
        subagent: { provider: 'anthropic' },
      },
    });
  });

  it('builds an empty document from no entries', () => {
    expect(patchOf([])).toEqual({});
  });
});

describe('ResolutionPreview', () => {
  it('renders nothing-changed when the preview carries no changes', () => {
    render(
      <ResolutionPreview
        changes={[]}
        labels={{
          before: 'Now',
          after: 'After saving',
          nothingChanges: 'Nothing would change.',
        }}
      />,
    );

    expect(screen.getByTestId('resolution-preview-empty')).toHaveTextContent(
      'Nothing would change.',
    );
  });

  it('lists every changed path with its before and after value', () => {
    render(
      <ResolutionPreview
        changes={[
          {
            path: 'models.investigator.model',
            before: 'gemini-2.5-flash',
            after: 'gemini-2.5-pro',
          },
        ]}
        labels={{
          before: 'Now',
          after: 'After saving',
          nothingChanges: 'Nothing would change.',
        }}
      />,
    );

    const row = screen.getByTestId('resolution-change');
    expect(row).toHaveAttribute('data-path', 'models.investigator.model');
    expect(row).toHaveTextContent('gemini-2.5-flash');
    expect(row).toHaveTextContent('gemini-2.5-pro');
  });
});

const LABELS = {
  unreachable: 'The deployment could not be reached.',
  failed: 'Refused.',
};

function Harness({
  nodeId,
  patch,
}: {
  readonly nodeId: string;
  readonly patch: Record<string, unknown>;
}) {
  const write = useConfigWrite(nodeId, patch, [], LABELS);
  return (
    <div>
      <span data-testid="write-status">{write.status}</span>
      <span data-testid="write-current">{String(write.current)}</span>
      <span data-testid="write-saved">{String(write.saved)}</span>
      <span data-testid="write-failure">{write.failure}</span>
      <span data-testid="write-changes">
        {write.resolved?.changes.map((change) => change.path).join(',') ?? ''}
      </span>
      <span data-testid="write-accepted">{String(write.resolved?.accepted ?? '')}</span>
      <span data-testid="write-errors">{write.resolved?.errors.join(',') ?? ''}</span>
      <span data-testid="write-requires-approval">
        {String(write.resolved?.requiresApproval ?? '')}
      </span>
      <button
        onClick={() => {
          void write.preview();
        }}
      >
        preview
      </button>
      <button
        onClick={() => {
          void write.save();
        }}
      >
        save
      </button>
    </div>
  );
}

describe('useConfigWrite', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    vi.stubGlobal('fetch', (input: unknown) => {
      const url = String(input);
      if (url.endsWith('/api/preview')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              changes: [{ path: 'a.b', before: '1', after: '2' }],
              values: { a: { b: 2 } },
              provenance: { 'a.b': 'org-northwind' },
              accepted: true,
              errors: [],
              requires_approval: false,
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      if (url.endsWith('/api/config')) {
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true, values: {} }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        );
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`));
    });
  });

  it('is not "current" until a preview of exactly this patch has come back', async () => {
    render(<Harness nodeId="org-northwind" patch={{ a: { b: 2 } }} />);

    expect(screen.getByTestId('write-current')).toHaveTextContent('false');

    await act(async () => {
      screen.getByText('preview').click();
      await Promise.resolve();
    });

    expect(screen.getByTestId('write-current')).toHaveTextContent('true');
    expect(screen.getByTestId('write-changes')).toHaveTextContent('a.b');
  });

  it('reports what the deployment resolved, then clears the pending preview on save', async () => {
    render(<Harness nodeId="org-northwind" patch={{ a: { b: 2 } }} />);

    await act(async () => {
      screen.getByText('preview').click();
      await Promise.resolve();
    });
    await act(async () => {
      screen.getByText('save').click();
      await Promise.resolve();
    });

    expect(screen.getByTestId('write-saved')).toHaveTextContent('true');
    expect(screen.getByTestId('write-current')).toHaveTextContent('false');
  });

  it('reports the deployment as unreachable rather than as having refused', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('no route to host')));
    render(<Harness nodeId="org-northwind" patch={{ a: { b: 2 } }} />);

    await act(async () => {
      screen.getByText('preview').click();
      await Promise.resolve();
    });

    expect(screen.getByTestId('write-failure')).toHaveTextContent(
      'The deployment could not be reached.',
    );
  });

  it('reports the deployment’s own reason for a refusal, in the deployment’s own words', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          JSON.stringify({ reason: 'models.investigator.model is required' }),
          {
            status: 400,
            headers: { 'content-type': 'application/json' },
          },
        ),
      ),
    );
    render(<Harness nodeId="org-northwind" patch={{ a: { b: 2 } }} />);

    await act(async () => {
      screen.getByText('preview').click();
      await Promise.resolve();
    });

    expect(screen.getByTestId('write-failure')).toHaveTextContent(
      'models.investigator.model is required',
    );
  });

  it('falls back to the stated failure sentence when the refusal carries no reason', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(JSON.stringify({}), {
          status: 400,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
    render(<Harness nodeId="org-northwind" patch={{ a: { b: 2 } }} />);

    await act(async () => {
      screen.getByText('save').click();
      await Promise.resolve();
    });

    expect(screen.getByTestId('write-failure')).toHaveTextContent('Refused.');
    expect(screen.getByTestId('write-saved')).toHaveTextContent('false');
  });

  it('carries whether the patch was accepted, its errors, and whether it needs approval', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            changes: [],
            values: {},
            provenance: {},
            accepted: false,
            errors: [{ path: 'a.b', message: 'must be a known configuration field' }],
            requires_approval: true,
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );
    render(<Harness nodeId="org-northwind" patch={{ a: { b: 2 } }} />);

    await act(async () => {
      screen.getByText('preview').click();
      await Promise.resolve();
    });

    expect(screen.getByTestId('write-accepted')).toHaveTextContent('false');
    expect(screen.getByTestId('write-errors')).toHaveTextContent(
      'must be a known configuration field',
    );
    expect(screen.getByTestId('write-requires-approval')).toHaveTextContent('true');
  });
});

describe('EffectiveFieldsTable', () => {
  const LABELS = { setting: 'Setting', value: 'Value', origin: 'Set at' };

  it('draws a legible value and its origin for every row it is given', () => {
    render(
      <EffectiveFieldsTable
        rows={[
          {
            path: 'policies.masking.enabled',
            label: 'Masking',
            value: 'On',
            origin: 'Deployment default',
          },
          {
            path: 'policies.approvals.expiry_hours',
            label: 'Approval expiry',
            value: '2 hours',
            origin: 'org-northwind',
          },
        ]}
        labels={LABELS}
      />,
    );

    const rows = screen.getAllByTestId('effective-field');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('On');
    expect(rows[1]).toHaveTextContent('2 hours');
  });

  it('refuses to render a row with no renderable value, rather than drawing a blank cell', () => {
    expect(() =>
      render(
        <EffectiveFieldsTable
          rows={[
            {
              path: 'policies.masking.enabled',
              label: 'Masking',
              value: '',
              origin: 'Deployment default',
            },
          ]}
          labels={LABELS}
        />,
      ),
    ).toThrow(/policies\.masking\.enabled/);
  });

  it('refuses to render a row with no renderable origin, rather than drawing a blank cell', () => {
    expect(() =>
      render(
        <EffectiveFieldsTable
          rows={[
            {
              path: 'policies.masking.enabled',
              label: 'Masking',
              value: 'On',
              origin: '',
            },
          ]}
          labels={LABELS}
        />,
      ),
    ).toThrow(/policies\.masking\.enabled/);
  });
});
