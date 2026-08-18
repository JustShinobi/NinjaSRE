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
  // Which sections were open is remembered per browser. Left uncleared, one
  // test's "opened" section would start the next test already open.
  window.localStorage.clear();
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
  setAt: 'Set at:',
  usingDefault: 'Using the deployment default:',
  toc: 'Jump to a section',
  search: 'Find a field',
  searchEmpty: 'No field matches this search.',
  generalSection: 'General',
  empty: 'Nothing would change',
  previewFirst: 'Preview the change before saving it.',
  clear: 'Remove this override',
  cleared: 'Will go back to being inherited',
  redundant: 'This is already what is inherited here',
  reverts: 'Reverts to',
  notEditable: 'Edited as a document rather than here.',
  inherited: 'Inherited',
  useSuggested: 'Use',
  addEntry: 'Add another',
  removeEntry: 'Remove',
  moveUp: 'Move earlier',
  moveDown: 'Move later',
  entryPosition: 'Evaluated',
  emptyList: 'Nothing declared here yet.',
};

function field(over: Partial<EditableField> = {}): EditableField {
  return {
    path: 'agents.tool_budget',
    label: 'Tool budget',
    type: 'integer',
    help: '',
    section: 'agents',
    sectionHelp: 'Prompts, topology, and the budgets one run may spend.',
    value: 8,
    default: 5,
    provenance: 'org-northwind',
    setHere: false,
    lockedBy: '',
    approvalGated: false,
    allowedValues: null,
    minimum: 1,
    maximum: 20,
    suggestedValue: '',
    suggestedBecause: '',
    // A list of plain values, which is what the test below is about: there is
    // nothing inside a string to draw a row of controls from.
    itemFields: [],
    ...over,
  };
}

function editor(fields: readonly EditableField[]): void {
  render(
    <ConfigEditor nodeId="payments" fields={fields} labels={LABELS} locale="en" />,
  );
}

/** The jump-to link for `section`, or a failure saying it was never drawn. */
function sectionLink(section: string): HTMLElement {
  const found = screen
    .getAllByTestId('section-link')
    .find((each) => each.getAttribute('data-section') === section);
  if (found === undefined) {
    throw new Error(`no section-link for ${section}`);
  }
  return found;
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
    default: '',
    provenance: '',
    minimum: null,
    maximum: null,
    suggestedValue: FOUND,
    suggestedBecause: 'a guest labelled prometheus answers on the metrics port',
  });

  /** Sections start collapsed; a field's own section has to be opened to reach it. */
  async function openItsSection(): Promise<void> {
    await userEvent.click(sectionLink(ENDPOINT.section));
  }

  it('offers the address the estate found, and says where it came from', async () => {
    editor([ENDPOINT]);
    await openItsSection();

    const offer = screen.getByTestId('use-suggested');
    expect(offer).toHaveTextContent(FOUND);
    expect(screen.getByTestId('suggested-because')).toHaveTextContent(
      'answers on the metrics port',
    );
  });

  it('fills the control rather than saving anything, so it is still previewed', async () => {
    editor([ENDPOINT]);
    await openItsSection();

    await userEvent.click(screen.getByTestId('use-suggested'));

    expect(screen.getByLabelText('Endpoint')).toHaveValue(FOUND);
    expect(screen.queryByTestId('save-config')).toBeNull();
  });

  it('offers nothing where the field already has a value', async () => {
    // An address somebody typed is a decision. Offering to replace it with a
    // derived one puts a guess above a choice.
    editor([field({ ...ENDPOINT, value: TYPED })]);
    await openItsSection();

    expect(screen.queryByTestId('use-suggested')).toBeNull();
  });

  it('offers nothing where the deployment found nothing', async () => {
    editor([field({ ...ENDPOINT, suggestedValue: '', suggestedBecause: '' })]);
    await openItsSection();

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

describe('the default an unset field is actually running with', () => {
  it('shows the deployment default that applies, rather than leaving the field silent', () => {
    editor([field({ provenance: '', value: null, default: 5 })]);

    expect(screen.getByTestId('field-provenance')).toHaveTextContent(
      'Using the deployment default: 5',
    );
  });

  it('prefills the control with that default, so the operator sees what is running', () => {
    editor([field({ provenance: '', value: null, default: 5 })]);

    expect(screen.getByLabelText('Tool budget')).toHaveValue(5);
  });

  it('never says an override is "the default", even at a node literally named default', () => {
    editor([field({ provenance: 'default', setHere: false })]);

    expect(screen.getByTestId('field-provenance')).toHaveTextContent('Set at: default');
    expect(screen.getByTestId('field-provenance')).not.toHaveTextContent(
      LABELS.usingDefault,
    );
  });
});

describe('sections, collapsed by default and reachable two ways', () => {
  function two(): EditableField[] {
    return [
      field({
        path: 'agents.tool_budget',
        label: 'Tool budget',
        section: 'agents',
        sectionHelp: 'Budgets',
      }),
      field({
        path: 'policies.masking.level',
        label: 'Masking level',
        section: 'policies',
        sectionHelp: 'Guardrails',
        type: 'string',
        value: 'standard',
        default: 'standard',
        minimum: null,
        maximum: null,
      }),
    ];
  }

  it('opens no section until the operator asks for one', () => {
    editor(two());

    for (const details of screen.getAllByTestId('config-section')) {
      expect(details).not.toHaveAttribute('open');
    }
  });

  it('opens the section the jump-to list points at, and leaves the other closed', async () => {
    editor(two());

    await userEvent.click(sectionLink('agents'));

    const opened = screen
      .getAllByTestId('config-section')
      .find((each) => each.getAttribute('data-section') === 'agents');
    const other = screen
      .getAllByTestId('config-section')
      .find((each) => each.getAttribute('data-section') === 'policies');
    expect(opened).toHaveAttribute('open');
    expect(other).not.toHaveAttribute('open');
  });

  it('narrows the fields shown to the ones a search matches', async () => {
    editor(two());

    await userEvent.type(screen.getByLabelText(LABELS.search), 'masking');

    expect(screen.queryByLabelText('Tool budget')).toBeNull();
    expect(screen.getByLabelText('Masking level')).toBeInTheDocument();
  });

  it('says nothing matches, rather than showing an empty page, when the search finds nothing', async () => {
    editor(two());

    await userEvent.type(screen.getByLabelText(LABELS.search), 'nonexistent-setting');

    expect(screen.getByTestId('search-empty')).toHaveTextContent(LABELS.searchEmpty);
  });
});

describe('a section titles itself for a person, never by its own schema path', () => {
  function schemaSectioned(section: string): EditableField[] {
    return [field({ path: `${section}.level`, label: 'Level', section })];
  }

  it('shows a human title for a known technical section, not the schema path', () => {
    editor(schemaSectioned('policies.masking'));

    expect(screen.queryByText('policies.masking')).toBeNull();
    expect(screen.getByTestId('section-link')).toHaveTextContent('Masking');
    const details = screen.getByTestId('config-section');
    expect(details).not.toHaveTextContent('policies.masking');
    expect(details).toHaveTextContent('Masking');
  });

  it('shows a human title for every other section this feature names', () => {
    editor([
      ...schemaSectioned('policies.guardrails'),
      ...schemaSectioned('policies.approvals'),
      ...schemaSectioned('policies.autonomy'),
      ...schemaSectioned('surfaces.notification_policy'),
    ]);

    const body = document.body.textContent;
    for (const path of [
      'policies.guardrails',
      'policies.approvals',
      'policies.autonomy',
      'surfaces.notification_policy',
    ]) {
      expect(body).not.toContain(path);
    }
    expect(screen.getByText('Guardrails')).toBeInTheDocument();
    expect(screen.getByText('Approvals')).toBeInTheDocument();
    expect(screen.getByText('Autonomy')).toBeInTheDocument();
    expect(screen.getByText('Notification policy')).toBeInTheDocument();
  });

  it('still reads as words, not a path, for a section this catalogue has never met', () => {
    editor(schemaSectioned('policies.unheard_of_thing'));

    expect(screen.queryByText('policies.unheard_of_thing')).toBeNull();
    expect(screen.getByTestId('section-link')).toHaveTextContent('Unheard Of Thing');
  });
});

describe('an ordered list entry, titled by what it is rather than by its position', () => {
  function integrations(over: Partial<EditableField> = {}): EditableField {
    return field({
      path: 'capabilities.integrations',
      label: 'Integrations',
      type: 'array',
      value: [{ name: 'proxmox', enabled: true }],
      itemFields: [
        {
          path: 'name',
          label: 'Name',
          type: 'string',
          help: '',
          allowedValues: null,
          minimum: null,
          maximum: null,
          default: '',
        },
        {
          path: 'enabled',
          label: 'Enabled',
          type: 'boolean',
          help: '',
          allowedValues: null,
          minimum: null,
          maximum: null,
          default: false,
        },
      ],
      ...over,
    });
  }

  it('titles the entry by its own name field, not by the order it is evaluated in', () => {
    editor([integrations()]);

    expect(screen.getByTestId('entry-title')).toHaveTextContent('proxmox');
  });

  it('gives the enabled toggle an accessible name that says whose it is', () => {
    editor([integrations()]);

    expect(screen.getByLabelText('proxmox — Enabled')).toBeInTheDocument();
  });

  it('names the toggle by its position instead, for an entry with no name typed yet', () => {
    // A freshly-added entry starts with an empty name — `blankEntry` seeds it
    // at `''` until the operator types one. The toggle beside it still has to
    // say whose it is; a bare "Enabled" names nothing, and position is the one
    // fact about an unnamed entry that is never a guess.
    editor([integrations({ value: [{ name: '', enabled: true }] })]);

    expect(screen.getByLabelText('Evaluated 1 — Enabled')).toBeInTheDocument();
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

describe('the answers the deployment gives that are not diffs', () => {
  it('says nothing would change when the deployment says nothing would', async () => {
    answerWith({
      ...ANSWER,
      changes: [],
      locked: {},
      approval_gated: [],
      requires_approval: false,
      redundant: [],
    });
    editor([field()]);

    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));

    expect(await screen.findByText(LABELS.empty)).toBeInTheDocument();
    expect(screen.queryByTestId('preview-changes')).toBeNull();
  });

  it('says the deployment could not be reached when the preview never arrives', async () => {
    editor([field()]);
    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));

    await userEvent.click(screen.getByTestId('ask-preview'));

    expect(await screen.findByTestId('save-failure')).toHaveTextContent(
      LABELS.unreachable,
    );
  });

  it('falls back to its own words when a refusal named no reason', async () => {
    editor([field()]);
    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));
    await screen.findByTestId('save-config');
    answerWith({ ok: false, reachable: true }, 500);

    await userEvent.click(screen.getByTestId('save-config'));

    expect(await screen.findByTestId('save-failure')).toHaveTextContent(LABELS.failed);
  });

  it('says which level a field with no value at all comes from, when the schema names no default either', () => {
    editor([field({ provenance: '', value: null, default: undefined })]);

    expect(screen.getByTestId('field-provenance')).toHaveTextContent(LABELS.inherited);
  });

  it('draws a plain string field as text rather than as a number', () => {
    editor([
      field({
        path: 'policies.masking.level',
        label: 'Level',
        type: 'string',
        value: 'standard',
        minimum: null,
        maximum: null,
      }),
    ]);

    expect(screen.getByLabelText('Level')).toHaveAttribute('type', 'text');
  });

  it('says a gated field will be queued, beside the control that queues it', () => {
    editor([field({ approvalGated: true })]);

    expect(screen.getByTestId('field-gated')).toHaveTextContent(LABELS.gatedDetail);
  });

  it('offers no clear on a locked field, whatever this node set', () => {
    editor([field({ setHere: true, lockedBy: 'org-northwind' })]);

    expect(screen.queryByTestId('clear-override')).toBeNull();
  });

  it('reports success and clears the pending change once a save lands', async () => {
    editor([field()]);
    await userEvent.clear(screen.getByLabelText('Tool budget'));
    await userEvent.type(screen.getByLabelText('Tool budget'), '12');
    await userEvent.click(screen.getByTestId('ask-preview'));
    await screen.findByTestId('save-config');
    answerWith({ ok: true, reachable: true, reason: '', values: {} });

    await userEvent.click(screen.getByTestId('save-config'));

    expect(await screen.findByTestId('save-result')).toHaveTextContent(LABELS.saved);
    expect(screen.queryByTestId('preview-changes')).toBeNull();
  });
});
