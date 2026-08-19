import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { GuardrailTable } from '@/surfaces/settings/guardrail-table';
import { guardrailRows } from '@/surfaces/settings/guardrail-values';
import type { EditableField } from '@/surfaces/preview';
import type { EffectiveFieldRow } from '@/design/resolution-preview';

/**
 * The Guardrails tab's own table: read and write in the same row.
 *
 * Three properties this component owns and `EffectiveFieldsTable` does not:
 * a field the catalogue declares editable gets an Edit affordance beside its
 * value, never in place of it; a save sends only the one path that changed,
 * to the same scoped write route every other settings page already saves
 * through; and the blank-cell guarantee `EffectiveFieldsTable` throws on is
 * reproduced here rather than assumed to still hold.
 */

const refresh = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}));

let sent: { url: string; body: unknown }[] = [];

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function answerWith(body: unknown, status = 200): void {
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent.push({
      url: String(url),
      body: typeof init.body === 'string' ? (JSON.parse(init.body) as unknown) : null,
    });
    return Promise.resolve(respond(body, status));
  });
}

beforeEach(() => {
  sent = [];
  refresh.mockClear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  setting: 'Setting',
  value: 'Value',
  origin: 'Set at',
  edit: 'Edit',
  cancel: 'Cancel',
  save: 'Save',
  saving: 'Saving…',
  saved: 'Saved.',
  failed: 'The deployment refused this change.',
  unreachable: 'The deployment could not be reached.',
};

function field(over: Partial<EditableField> = {}): EditableField {
  return {
    path: 'policies.masking.enabled',
    label: 'Masking enabled',
    type: 'boolean',
    help: 'Hide identifying values before they are sent to a model.',
    section: 'policies.masking',
    sectionHelp: '',
    value: false,
    default: false,
    provenance: '',
    setHere: false,
    lockedBy: '',
    approvalGated: false,
    allowedValues: null,
    minimum: null,
    maximum: null,
    suggestedValue: '',
    suggestedBecause: '',
    itemFields: [],
    ...over,
  };
}

function row(over: Partial<EffectiveFieldRow> = {}): EffectiveFieldRow {
  return {
    path: 'policies.masking.enabled',
    label: 'Masking enabled',
    value: 'Off',
    origin: 'Deployment default',
    ...over,
  };
}

function table({
  rows = [row()],
  catalogue = [field()],
  writable = true,
  nodeId = 'org-northwind',
}: {
  rows?: readonly EffectiveFieldRow[];
  catalogue?: readonly EditableField[];
  writable?: boolean;
  nodeId?: string;
} = {}): void {
  render(
    <GuardrailTable
      rows={rows}
      catalogue={catalogue}
      writable={writable}
      nodeId={nodeId}
      labels={LABELS}
    />,
  );
}

describe('reading the table', () => {
  it('draws Setting, Value and Set at for every row, and the two say different things', () => {
    table({
      rows: [
        row({ value: 'On', origin: 'org-northwind' }),
        row({
          path: 'policies.guardrails.ruleset',
          label: 'Ruleset',
          value: 'Not set',
          origin: 'Deployment default',
        }),
      ],
      catalogue: [
        field(),
        field({ path: 'policies.guardrails.ruleset', type: 'string' }),
      ],
    });

    const rows = screen.getAllByTestId('effective-field');
    expect(rows).toHaveLength(2);
    const maskingRow = rows.find(
      (each) => each.getAttribute('data-path') === 'policies.masking.enabled',
    );
    if (maskingRow === undefined)
      throw new Error('no row for policies.masking.enabled');
    expect(maskingRow).toHaveTextContent('Masking enabled');
    expect(maskingRow).toHaveTextContent('On');

    const origin = within(maskingRow).getByTestId('effective-field-origin');
    expect(origin).toHaveTextContent('org-northwind');
    // Set at names where the value came from, in words the value cell itself
    // never uses — the two columns are never the same sentence.
    expect(origin.textContent).not.toBe('On');
  });

  it('refuses to render a row with no renderable value, the same guarantee EffectiveFieldsTable enforces', () => {
    expect(() => {
      table({ rows: [row({ value: '' })] });
    }).toThrow(/policies\.masking\.enabled/);
  });

  it('refuses to render a row with no renderable origin', () => {
    expect(() => {
      table({ rows: [row({ origin: '' })] });
    }).toThrow(/policies\.masking\.enabled/);
  });
});

describe('who gets an Edit affordance', () => {
  it('offers Edit next to an editable field, for a writer', () => {
    table();

    expect(screen.getByTestId('guardrail-edit')).toBeInTheDocument();
  });

  it('offers no Edit affordance and no form, for a reader — the value is still there to read', () => {
    table({ writable: false });

    expect(screen.queryByTestId('guardrail-edit')).not.toBeInTheDocument();
    expect(screen.queryByTestId('guardrail-field-editor')).not.toBeInTheDocument();
    expect(screen.getByTestId('effective-field')).toHaveTextContent('Off');
  });

  it('offers no Edit affordance for a row the catalogue does not describe', () => {
    table({ catalogue: [] });

    expect(screen.queryByTestId('guardrail-edit')).not.toBeInTheDocument();
  });
});

describe('editing a field in its own row', () => {
  it('opens on the field’s current value, sends only that one path to the write route, and refreshes so Set at can catch up', async () => {
    answerWith({ ok: true, reachable: true, reason: '', values: {} });
    table({
      rows: [row({ value: 'Off', origin: 'Deployment default' })],
      catalogue: [field({ value: false, default: false, provenance: '' })],
    });

    await userEvent.click(screen.getByTestId('guardrail-edit'));
    const editor = screen.getByTestId('guardrail-field-editor');
    expect(within(editor).getByRole('switch')).toHaveAttribute('aria-checked', 'false');

    await userEvent.click(within(editor).getByRole('switch'));
    await userEvent.click(screen.getByTestId('guardrail-save'));

    expect(await screen.findByTestId('guardrail-save-result')).toHaveTextContent(
      'Saved.',
    );
    expect(sent).toHaveLength(1);
    expect(sent[0]?.url).toBe('/api/config');
    // Exactly the one field that changed — every guardrail sibling this
    // node holds, and everything outside this group, is absent from the
    // patch rather than merely unchanged in value.
    expect(sent[0]?.body).toEqual({
      nodeId: 'org-northwind',
      patch: { policies: { masking: { enabled: true } } },
      remove: [],
    });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('guardrail-field-editor')).not.toBeInTheDocument();
  });

  it('cancels without writing anything', async () => {
    table();

    await userEvent.click(screen.getByTestId('guardrail-edit'));
    await userEvent.click(screen.getByTestId('guardrail-cancel'));

    expect(screen.queryByTestId('guardrail-field-editor')).not.toBeInTheDocument();
    expect(sent).toHaveLength(0);
    expect(refresh).not.toHaveBeenCalled();
  });

  it('reports the deployment’s refusal in its own words, and leaves the form open to try again', async () => {
    answerWith(
      { ok: false, reachable: true, reason: 'policies.masking.enabled is locked here' },
      409,
    );
    table();

    await userEvent.click(screen.getByTestId('guardrail-edit'));
    await userEvent.click(screen.getByTestId('guardrail-save'));

    expect(await screen.findByTestId('guardrail-save-failure')).toHaveTextContent(
      'locked here',
    );
    expect(screen.getByTestId('guardrail-field-editor')).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it('says the deployment could not be reached, a different sentence than a refusal', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));
    table();

    await userEvent.click(screen.getByTestId('guardrail-edit'));
    await userEvent.click(screen.getByTestId('guardrail-save'));

    expect(await screen.findByTestId('guardrail-save-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });

  it('draws a closed set as a Select, matching the schema type — never a control this console invented', async () => {
    table({
      rows: [
        row({
          path: 'policies.guardrails.mode',
          label: 'Guardrail mode',
          value: 'enforcing',
        }),
      ],
      catalogue: [
        field({
          path: 'policies.guardrails.mode',
          label: 'Guardrail mode',
          type: 'string',
          value: 'enforcing',
          allowedValues: ['enforcing', 'observing'],
        }),
      ],
    });

    await userEvent.click(screen.getByTestId('guardrail-edit'));

    expect(
      screen.getByRole('combobox', { name: 'Guardrail mode' }),
    ).toBeInTheDocument();
  });

  it('shows the described sentence while reading but saves the raw slug underneath it', async () => {
    answerWith({ ok: true, reachable: true, reason: '', values: {} });
    const modeField = field({
      path: 'policies.guardrails.mode',
      label: 'Guardrail mode',
      type: 'string',
      value: 'enforcing',
      default: 'enforcing',
      allowedValues: ['enforcing', 'observing'],
    });
    // The real resolver both appearances of this table call, not a
    // hand-typed row — proves the sentence `guardrailRows` now produces and
    // the value this table saves stay two different things end to end.
    const rows = guardrailRows([modeField], 'en').filter(
      (each) => each.path === 'policies.guardrails.mode',
    );
    table({ rows, catalogue: [modeField] });

    expect(screen.getByTestId('effective-field')).toHaveTextContent(
      'Enforcing — matches are blocked',
    );

    await userEvent.click(screen.getByTestId('guardrail-edit'));
    const editor = screen.getByTestId('guardrail-field-editor');
    // Opens on the field's own raw value, through the closed-set control the
    // schema's `allowedValues` draws — never the sentence above, which is
    // not itself a value the deployment would accept back.
    expect(within(editor).getByRole('combobox')).toHaveValue('enforcing');

    await userEvent.selectOptions(within(editor).getByRole('combobox'), 'observing');
    await userEvent.click(screen.getByTestId('guardrail-save'));

    expect(await screen.findByTestId('guardrail-save-result')).toHaveTextContent(
      'Saved.',
    );
    // The write carries the slug the deployment understands, never the
    // sentence the Value cell showed while reading.
    expect(sent[0]?.body).toEqual({
      nodeId: 'org-northwind',
      patch: { policies: { guardrails: { mode: 'observing' } } },
      remove: [],
    });
  });
});
