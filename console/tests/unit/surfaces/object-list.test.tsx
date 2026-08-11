import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConfigEditor, type EditableField, type ItemField } from '@/surfaces/preview';

import { only } from '../support/dom';

/**
 * Editing an ordered list of objects — routing rules, and the specialists a
 * team declares.
 *
 * Until now the editor drew a control for four scalar types and called
 * everything else "edited as a document rather than here", which meant the two
 * settings whose *order* is their meaning could not be edited at all. Routing
 * rules are evaluated first-match-wins with an explicit last word; a list of
 * specialists is dispatched down. Neither is a set.
 *
 * Three properties, and each is a way a list editor lies about what it will save.
 *
 * **Order is the value.** Moving an entry has to change what gets written, not
 * just what is drawn. A control that rendered a position and posted the
 * original order would be the worst possible version of this.
 *
 * **The whole list travels.** A list replaces entirely — that is what the merge
 * does — so the patch carries every entry, including the ones nobody touched.
 * Sending only the edited entry would silently delete the rest.
 *
 * **The preview guarantee is not weakened by having a bigger control.** Adding,
 * removing and reordering are edits like any other: each one takes the save
 * control away until the deployment has been asked again.
 */

let sent: { url: string; init: RequestInit }[] = [];

const ANSWER = {
  changes: [{ path: 'transit.rules', before: '[…]', after: '[…]' }],
  locked: {},
  approval_gated: [],
  requires_approval: false,
  redundant: [],
  reverts: [],
};

function answerWith(body: unknown, status = 200): void {
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent.push({ url: String(url), init });
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith(ANSWER);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastBody(): Record<string, unknown> {
  const body = sent.at(-1)?.init.body;
  return typeof body === 'string' ? (JSON.parse(body) as Record<string, unknown>) : {};
}

/** The rules the patch would write, as the deployment would receive them. */
function patchedRules(): readonly Record<string, unknown>[] {
  const patch = lastBody().patch as Record<string, unknown>;
  const transit = patch.transit as Record<string, unknown> | undefined;
  return (transit?.rules ?? []) as readonly Record<string, unknown>[];
}

/** The entry at `index`, or a failure saying how many there actually are. */
function entry(index: number): Element {
  const entries = screen.getAllByTestId('list-entry');
  const found = entries[index];
  if (found === undefined) {
    throw new Error(`no list entry at ${String(index)}; the editor drew ${String(entries.length)}`);
  }
  return found;
}

/** The `index`th control with `testId`, or a failure naming what was found. */
function control(testId: string, index: number): Element {
  const found = screen.getAllByTestId(testId)[index];
  if (found === undefined) {
    throw new Error(`no ${testId} at ${String(index)}`);
  }
  return found;
}

const LABELS = {
  setting: 'Setting',
  value: 'Value',
  submit: 'Preview',
  save: 'Save',
  saving: 'Saving…',
  saved: 'Saved.',
  failed: 'The deployment refused this change.',
  unreachable: 'The deployment could not be reached.',
  before: 'Now',
  after: 'After saving',
  locked: 'Locked here',
  lockedDetail: 'A change made here would be refused.',
  gated: 'Approval-gated',
  gatedDetail: 'Saving this queues a change rather than applying it.',
  provenance: 'Set at',
  empty: 'Nothing would change',
  previewFirst: 'Preview the change before saving it.',
  clear: 'Remove this override',
  cleared: 'Will go back to being inherited',
  redundant: 'This is already what is inherited here',
  reverts: 'Reverts to',
  notEditable: 'Edited as a document rather than here.',
  inherited: 'Inherited',
  useSuggested: 'Use',
  addEntry: 'Add',
  removeEntry: 'Remove',
  moveUp: 'Move up',
  moveDown: 'Move down',
  entryPosition: 'Evaluated',
  emptyList: 'Nothing declared here yet.',
};

function item(over: Partial<ItemField> = {}): ItemField {
  return {
    path: 'team',
    label: 'Team',
    type: 'string',
    description: '',
    allowedValues: null,
    minimum: null,
    maximum: null,
    default: '',
    ...over,
  };
}

const RULE_ITEMS: readonly ItemField[] = [
  item({ path: 'rule_id', label: 'Rule' }),
  item({ path: 'team', label: 'Team' }),
  item({
    path: 'action',
    label: 'Action',
    allowedValues: ['investigate', 'record', 'discard'],
    default: 'investigate',
  }),
];

function rules(over: Partial<EditableField> = {}): EditableField {
  return {
    path: 'transit.rules',
    label: 'Routing rules',
    type: 'array',
    description: 'Evaluated in order; the last one decides what matched nothing.',
    section: 'transit',
    sectionSummary: 'What comes in, where it goes.',
    value: [
      { rule_id: 'payments', team: 'payments', action: 'investigate' },
      { rule_id: 'rest', team: 'platform', action: 'record' },
    ],
    provenance: 'org-northwind',
    setHere: true,
    lockedBy: '',
    approvalGated: false,
    allowedValues: null,
    minimum: null,
    maximum: null,
    suggestedValue: '',
    suggestedBecause: '',
    itemFields: RULE_ITEMS,
    ...over,
  };
}

function editor(fields: readonly EditableField[]): void {
  render(<ConfigEditor nodeId="payments" fields={fields} labels={LABELS} />);
}

/** Ask for a preview, which is what puts the current patch on the wire. */
async function preview(): Promise<void> {
  await userEvent.click(screen.getByTestId('ask-preview'));
}

describe('an ordered list of objects', () => {
  it('draws one row per entry, in the order the deployment stores them', () => {
    editor([rules()]);

    const entries = screen.getAllByTestId('list-entry');
    expect(entries.map((each) => each.getAttribute('data-index'))).toEqual(['0', '1']);
  });

  it('draws a control per declared item field, from the catalogue and not its own table', () => {
    editor([rules()]);

    const first = entry(0);
    expect(only(first, '[data-item-path="rule_id"]')).toBeInTheDocument();
    expect(only(first, '[data-item-path="team"]')).toBeInTheDocument();
    expect(only(first, '[data-item-path="action"]')).toBeInTheDocument();
  });

  it('draws an item field with a closed set as a list of exactly those values', () => {
    editor([rules()]);

    const options = screen.getAllByRole('option').map((each) => each.textContent);
    expect(options).toContain('investigate');
    expect(options).toContain('discard');
  });

  it('says where in the order each entry sits, because the order is the meaning', () => {
    editor([rules()]);

    const positions = screen
      .getAllByTestId('entry-position')
      .map((each) => each.textContent.trim());
    expect(positions).toEqual(['Evaluated 1', 'Evaluated 2']);
  });

  it('writes the new order when an entry moves, not the order it was drawn in', async () => {
    editor([rules()]);

    await userEvent.click(control('move-entry-down', 0));
    await preview();

    expect(patchedRules().map((each) => each.rule_id)).toEqual(['rest', 'payments']);
  });

  it('carries every entry, including the ones nobody touched', async () => {
    editor([rules()]);

    await userEvent.type(only(entry(0), 'input'), '!');
    await preview();

    expect(patchedRules()).toHaveLength(2);
    expect(patchedRules()[1]?.rule_id).toBe('rest');
  });

  it('appends an entry built from what the catalogue says an entry defaults to', async () => {
    editor([rules()]);

    await userEvent.click(screen.getByTestId('add-entry'));
    await preview();

    expect(patchedRules()).toHaveLength(3);
    expect(patchedRules()[2]).toEqual({ rule_id: '', team: '', action: 'investigate' });
  });

  it('drops the entry that was removed and keeps the rest in order', async () => {
    editor([rules()]);

    await userEvent.click(control('remove-entry', 0));
    await preview();

    expect(patchedRules().map((each) => each.rule_id)).toEqual(['rest']);
  });

  it('edits one entry without touching its neighbour', async () => {
    editor([rules()]);

    const teamControl = only(entry(1), '[data-item-path="team"] input');
    await userEvent.clear(teamControl);
    await userEvent.type(teamControl, 'search');
    await preview();

    expect(patchedRules()[0]?.team).toBe('payments');
    expect(patchedRules()[1]?.team).toBe('search');
  });

  it('says so plainly when the list is empty rather than drawing nothing', () => {
    editor([rules({ value: [] })]);

    expect(screen.getByText('Nothing declared here yet.')).toBeInTheDocument();
  });

  it('leaves a list of plain strings alone, because there is nothing inside one to draw', () => {
    editor([
      rules({
        path: 'capabilities.enabled',
        label: 'Enabled capabilities',
        value: ['logs_query'],
        itemFields: [],
      }),
    ]);

    expect(screen.getByTestId('field-not-editable')).toBeInTheDocument();
  });
});

describe('the preview guarantee, with a bigger control', () => {
  it('offers no save until the reordering has been previewed', async () => {
    editor([rules()]);

    await userEvent.click(control('move-entry-down', 0));

    expect(screen.queryByTestId('save-config')).toBeNull();
    expect(screen.getByTestId('preview-first')).toBeInTheDocument();
  });

  it('takes the save away again when an entry is added after the preview', async () => {
    editor([rules()]);

    await userEvent.click(control('move-entry-down', 0));
    await preview();
    expect(await screen.findByTestId('save-config')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('add-entry'));

    expect(screen.queryByTestId('save-config')).toBeNull();
  });
});
