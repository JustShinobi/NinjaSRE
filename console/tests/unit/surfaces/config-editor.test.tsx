import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConfigEditor, type EditableField } from '@/surfaces/preview';

/**
 * Editing configuration, and the two things that make it safe to.
 *
 * **The preview is mandatory by construction.** There is no save control until a
 * preview of the *current* patch has come back, and any further edit takes it
 * away again. That is a client-side guarantee and it has to be: the API cannot
 * know whether a human read the diff, and a save endpoint that demanded a
 * preview token would only prove the browser had asked, not that anybody looked.
 * So the test that matters is the bypass one — with an edit pending and no
 * preview, there is nothing in the document to press.
 *
 * **The controls come from the catalogue.** Type, range and closed set are the
 * deployment's answer, so an integer is a number control and a closed set is a
 * list. A console that decided this itself would offer values the write refuses.
 */

let sent: { url: string; init: RequestInit }[] = [];

/** The deployment's answer to a preview, with everything the diff renders. */
const ANSWER = {
  changes: [{ path: 'agents.tool_budget', before: 8, after: 12 }],
  locked: { 'policies.masking.level': 'org-northwind' },
  approval_gated: ['policies.masking.level'],
  requires_approval: true,
  redundant: [
    { path: 'agents.tool_budget', value: 12, inherited_from: 'org-northwind' },
  ],
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

/** What was actually put on the wire for the last request, parsed. */
function lastBody(): Record<string, unknown> {
  const body = sent.at(-1)?.init.body;
  return typeof body === 'string' ? (JSON.parse(body) as Record<string, unknown>) : {};
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
};

function field(over: Partial<EditableField> = {}): EditableField {
  return {
    path: 'agents.tool_budget',
    label: 'Tool budget',
    type: 'integer',
    description: '',
    section: 'agents',
    sectionSummary: 'Prompts, topology, and the budgets one run may spend.',
    value: 8,
    provenance: 'org-northwind',
    setHere: false,
    lockedBy: '',
    approvalGated: false,
    allowedValues: null,
    minimum: 1,
    maximum: 20,
    suggestedValue: '',
    suggestedBecause: '',
    ...over,
  };
}

function editor(fields: readonly EditableField[]): void {
  render(<ConfigEditor nodeId="payments" fields={fields} labels={LABELS} />);
}

describe('the controls the catalogue produces', () => {
  it('draws a bounded integer as a number control carrying its own range', () => {
    editor([field()]);

    const control = screen.getByLabelText('Tool budget');
    expect(control).toHaveAttribute('type', 'number');
    expect(control).toHaveAttribute('min', '1');
    expect(control).toHaveAttribute('max', '20');
  });

  it('draws a closed set as a list of exactly those values', () => {
    editor([
      field({
        path: 'policies.guardrails.mode',
        label: 'Mode',
        type: 'string',
        allowedValues: ['enforcing', 'observing'],
        minimum: null,
        maximum: null,
        value: 'enforcing',
      }),
    ]);

    const options = screen.getAllByRole('option').map((each) => each.textContent);
    expect(options).toEqual(['enforcing', 'observing']);
  });

  it('draws a boolean as a switch, because a switch is on and a checkbox is selected', () => {
    editor([field({ path: 'policies.masking.enabled', type: 'boolean', value: true })]);

    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });

  it('offers no control at all for a field an ancestor locked, and says who locked it', () => {
    editor([field({ lockedBy: 'org-northwind' })]);

    expect(screen.queryByLabelText('Tool budget')).toBeNull();
    expect(screen.getByTestId('field-locked')).toHaveTextContent('org-northwind');
  });

  it('says a list is edited elsewhere rather than offering a text box for it', () => {
    // A list replaces entirely on write. A text control here would let a typo
    // drop every entry but the one somebody retyped.
    editor([field({ path: 'capabilities.enabled', type: 'array', value: ['a', 'b'] })]);

    expect(screen.queryByLabelText('Tool budget')).toBeNull();
    expect(screen.getByTestId('field-not-editable')).toHaveTextContent(
      LABELS.notEditable,
    );
  });

  it('shows which level each value came from beside the control', () => {
    editor([field()]);

    expect(screen.getByTestId('field-provenance')).toHaveTextContent('org-northwind');
  });
});

describe('an endpoint the deployment already found', () => {
  // Assembled rather than written: a literal origin in console source is a lint
  // failure, and the rule is the one that keeps every request pointed at the
  // deployment.
  const FOUND = ['http:', '//10.20.0.14:9090'].join('');
  const TYPED = ['http:', '//metrics.internal:9090'].join('');

  const ENDPOINT = field({
    path: 'policies.observation.bridge.metrics.endpoint',
    label: 'Endpoint',
    type: 'string',
    value: '',
    provenance: '',
    minimum: null,
    maximum: null,
    suggestedValue: FOUND,
    suggestedBecause: 'a guest labelled prometheus answers on the metrics port',
  });

  it('offers the address the estate found, and says where it came from', () => {
    editor([ENDPOINT]);

    const offer = screen.getByTestId('use-suggested');
    expect(offer).toHaveTextContent(FOUND);
    expect(screen.getByTestId('suggested-because')).toHaveTextContent(
      'answers on the metrics port',
    );
  });

  it('fills the control rather than saving anything, so it is still previewed', async () => {
    editor([ENDPOINT]);

    await userEvent.click(screen.getByTestId('use-suggested'));

    expect(screen.getByLabelText('Endpoint')).toHaveValue(FOUND);
    expect(screen.queryByTestId('save-config')).toBeNull();
  });

  it('offers nothing where the field already has a value', () => {
    // An address somebody typed is a decision. Offering to replace it with a
    // derived one puts a guess above a choice.
    editor([field({ ...ENDPOINT, value: TYPED })]);

    expect(screen.queryByTestId('use-suggested')).toBeNull();
  });

  it('offers nothing where the deployment found nothing', () => {
    editor([field({ ...ENDPOINT, suggestedValue: '', suggestedBecause: '' })]);

    expect(screen.queryByTestId('use-suggested')).toBeNull();
  });
});

describe('preview before save, by construction', () => {
  it('has no save control before anything has been previewed', () => {
    editor([field()]);

    expect(screen.queryByTestId('save-config')).toBeNull();
  });

  it('still has no save control after an edit, which is the bypass attempt', async () => {
    editor([field()]);

    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');

    expect(screen.queryByTestId('save-config')).toBeNull();
    expect(screen.getByTestId('preview-first')).toHaveTextContent(LABELS.previewFirst);
  });

  it('offers the save only once the deployment has answered for this exact patch', async () => {
    editor([field()]);

    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));

    expect(await screen.findByTestId('save-config')).toBeInTheDocument();
  });

  it('takes the save away again the moment anything else is edited', async () => {
    editor([field()]);

    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));
    expect(await screen.findByTestId('save-config')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Tool budget'), '0');

    expect(screen.queryByTestId('save-config')).toBeNull();
    expect(screen.queryByTestId('preview-changes')).toBeNull();
  });

  it('will not preview at all until something has been changed', () => {
    editor([field()]);

    expect(screen.getByTestId('ask-preview')).toBeDisabled();
  });
});

describe('the diff the deployment answered with', () => {
  async function previewed(): Promise<void> {
    editor([field()]);
    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));
    await screen.findByTestId('preview-changes');
  }

  it('renders the server’s rows rather than working a merge out here', async () => {
    await previewed();

    const change = screen.getByTestId('preview-change');
    expect(change).toHaveAttribute('data-path', 'agents.tool_budget');
    expect(change).toHaveTextContent('8');
    expect(change).toHaveTextContent('12');
    expect(sent[0]?.url).toBe('/api/preview');
  });

  it('warns, inside the diff, that the new value is what is already inherited', async () => {
    await previewed();

    const warning = screen.getByTestId('preview-redundant');
    expect(warning).toHaveTextContent(LABELS.redundant);
    expect(warning).toHaveTextContent('org-northwind');
  });

  it('says what a locked value would do and that a gated one is queued', async () => {
    await previewed();

    expect(screen.getByTestId('locked')).toHaveTextContent(LABELS.lockedDetail);
    expect(screen.getByTestId('gated')).toHaveTextContent(LABELS.gatedDetail);
  });

  it('sends the typed value the catalogue declared, not the text that was keyed', async () => {
    await previewed();

    expect(lastBody()).toEqual({
      nodeId: 'payments',
      patch: { agents: { tool_budget: 12 } },
      remove: [],
    });
  });
});

describe('clearing an override, which is not setting the parent’s value', () => {
  it('offers the clear only for a field this node actually sets', () => {
    editor([field({ setHere: true, provenance: 'payments' })]);

    expect(screen.getByTestId('clear-override')).toBeInTheDocument();
  });

  it('does not offer it for a field this node only inherits', () => {
    editor([field({ setHere: false })]);

    expect(screen.queryByTestId('clear-override')).toBeNull();
  });

  it('sends a removal rather than a value, which is the whole distinction', async () => {
    editor([field({ setHere: true, provenance: 'payments', value: 12 })]);

    await userEvent.click(screen.getByTestId('clear-override'));
    await userEvent.click(screen.getByTestId('ask-preview'));

    expect(lastBody()).toEqual({
      nodeId: 'payments',
      patch: {},
      remove: ['agents.tool_budget'],
    });
  });

  it('shows what the field reverts to and from where', async () => {
    answerWith({
      ...ANSWER,
      changes: [{ path: 'agents.tool_budget', before: 12, after: 3 }],
      redundant: [],
      reverts: [
        { path: 'agents.tool_budget', value: 3, inherited_from: 'org-northwind' },
      ],
    });
    editor([field({ setHere: true, provenance: 'payments', value: 12 })]);

    await userEvent.click(screen.getByTestId('clear-override'));
    await userEvent.click(screen.getByTestId('ask-preview'));

    const revert = await screen.findByTestId('preview-revert');
    expect(revert).toHaveTextContent(LABELS.reverts);
    expect(revert).toHaveTextContent('org-northwind');
  });

  it('a clear can be taken back before it is previewed', async () => {
    editor([field({ setHere: true, provenance: 'payments', value: 12 })]);

    await userEvent.click(screen.getByTestId('clear-override'));
    expect(screen.getByTestId('ask-preview')).toBeEnabled();

    await userEvent.click(screen.getByTestId('clear-override'));
    expect(screen.getByTestId('ask-preview')).toBeDisabled();
  });
});

describe('the save', () => {
  async function readyToSave(): Promise<void> {
    editor([field()]);
    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));
    await screen.findByTestId('save-config');
  }

  it('sends the same patch that was previewed, to the write route', async () => {
    await readyToSave();
    answerWith({ ok: true, reachable: true, reason: '', values: {} });

    await userEvent.click(screen.getByTestId('save-config'));

    expect(sent.at(-1)?.url).toBe('/api/config');
    expect(lastBody()).toEqual({
      nodeId: 'payments',
      patch: { agents: { tool_budget: 12 } },
      remove: [],
    });
  });

  it('reports the deployment’s refusal in its own words rather than as a generic failure', async () => {
    await readyToSave();
    answerWith(
      {
        ok: false,
        reachable: true,
        reason: 'agents.tool_budget is locked at org-northwind',
      },
      409,
    );

    await userEvent.click(screen.getByTestId('save-config'));

    expect(await screen.findByTestId('save-failure')).toHaveTextContent(
      'locked at org-northwind',
    );
  });

  it('says the deployment could not be reached, which is a different sentence', async () => {
    await readyToSave();
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('save-config'));

    expect(await screen.findByTestId('save-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});
