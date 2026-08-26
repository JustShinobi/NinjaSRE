import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import {
  OperatingContextEditor,
  type ContextSection,
} from '@/surfaces/operating-context';

/**
 * Writing what this environment is, and reading the prompt it becomes.
 *
 * The assertion the screen exists for is the last group: the save control does
 * not exist until a preview of the *current* text has come back, and what that
 * preview shows is the deployment's own assembled prompt rather than anything
 * this component joined together. Everywhere else in the console a preview is a
 * diff of values; here the effect of saving is text a model will read, and
 * showing it is the only way somebody can consent to it.
 *
 * Nothing here resolves anything. Which level supplied a section, what the text
 * costs in tokens, and what the assembled prompt says are three of the
 * deployment's answers, rendered.
 */

let sent: { operation: string; payload: unknown }[] = [];

const PROMPT =
  'You are an SRE investigator.\n\n## Operating context\n\n### network\n\nMTU is 1450.';

const PREVIEW = {
  prompt: PROMPT,
  context: '## Operating context\n\n### network\n\nMTU is 1450.',
  tokens_used: 240,
  token_budget: 1200,
  over_budget: false,
  accepted: true,
  errors: [],
};

const REFUSED = {
  prompt: '',
  context: '',
  tokens_used: 4200,
  token_budget: 1200,
  over_budget: true,
  accepted: false,
  errors: [
    {
      path: 'agents.operating_context',
      message: 'is 3000 tokens over the 1200-token operating-context budget',
    },
  ],
};

function answerWith(answer: unknown, status = 200): void {
  vi.stubGlobal('fetch', (_url: unknown, init: RequestInit) => {
    const body: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    sent.push({
      operation: String(Reflect.get(Object(body), 'operation')),
      payload: Reflect.get(Object(body), 'payload'),
    });
    return Promise.resolve(
      new Response(JSON.stringify({ ok: status < 400, reachable: true, answer }), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  sent = [];
  answerWith(PREVIEW);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const LABELS = {
  section: 'Section',
  body: 'What it says',
  provenance: 'Set at',
  budget: 'Prompt budget',
  budgetUsed: '{used} of {budget} tokens',
  budgetConsequence: 'What goes over budget is refused, not truncated.',
  overBudget: 'Over the budget.',
  addSection: 'Add a section',
  addSectionDisabledReason: 'Type a name before adding a section.',
  sectionName: 'Section name',
  remove: 'Clear this section',
  factNotInstruction: 'Write facts, not instructions.',
  runbooks: 'Runbooks live in Knowledge',
  policy: 'Procedures live in Autonomy',
  previewTitle: 'What the model will be sent',
  previewLead: 'The exact text the next investigation will carry.',
  submit: 'Show me the prompt',
  previewDisabledReason: 'Change a section before asking for the prompt.',
  previewing: 'Assembling…',
  previewFirst: 'See the prompt before saving it.',
  save: 'Save',
  saving: 'Saving…',
  saved: 'Saved.',
  failed: 'The deployment refused this context.',
  unreachable: 'The deployment could not be reached.',
  roles: 'Sent to',
  templateUse: 'Use the starting document',
  templateLead: 'Derived from your own estate; nothing is written until you save it.',
};

const SECTIONS: readonly ContextSection[] = [
  {
    name: 'signals',
    body: 'Container metrics come from the host.',
    provenance: 'acme',
  },
  { name: 'network', body: 'MTU is 1450.', provenance: 'team-payments' },
];

const TEMPLATE: readonly ContextSection[] = [
  { name: 'Who is called, and when', body: 'Who is called for what?', provenance: '' },
];

function editor(
  overrides: {
    readonly sections?: readonly ContextSection[];
    readonly template?: readonly ContextSection[];
    readonly writable?: boolean;
    readonly tokensUsed?: number;
    readonly tokenBudget?: number;
  } = {},
): void {
  render(
    <OperatingContextEditor
      nodeId="team-payments"
      sections={overrides.sections ?? SECTIONS}
      template={overrides.template ?? []}
      tokensUsed={overrides.tokensUsed ?? 240}
      tokenBudget={overrides.tokenBudget ?? 1200}
      roles={['investigator', 'subagent']}
      labels={LABELS}
      writable={overrides.writable ?? true}
    />,
  );
}

async function editSection(name: string, text: string): Promise<void> {
  const field = screen.getByLabelText(name);
  await userEvent.clear(field);
  await userEvent.type(field, text);
}

// --- What applies, and where it came from ------------------------------------

it('renders one editable section per name', () => {
  editor();

  expect(screen.getAllByTestId('context-section')).toHaveLength(2);
});

it('names the level that supplied each section', () => {
  editor();

  const provenance = screen
    .getAllByTestId('section-provenance')
    .map((node) => [node.getAttribute('data-section'), node.textContent]);

  expect(provenance).toEqual([
    ['signals', `${LABELS.provenance}acme`],
    ['network', `${LABELS.provenance}team-payments`],
  ]);
});

it('states that this field is for facts and points at where instructions go', () => {
  editor();

  expect(screen.getByTestId('fact-not-instruction')).toHaveTextContent(
    LABELS.factNotInstruction,
  );
  expect(screen.getByRole('link', { name: LABELS.runbooks })).toHaveAttribute(
    'href',
    '/knowledge',
  );
  expect(screen.getByRole('link', { name: LABELS.policy })).toHaveAttribute(
    'href',
    '/autonomy',
  );

  // Two link sentences in a row read as one broken sentence without a
  // separator between them: "Runbooks live in Knowledge Procedures live in
  // Autonomy" is what shipped once.
  expect(screen.getByTestId('fact-not-instruction').textContent).toContain(
    `${LABELS.runbooks} · ${LABELS.policy}`,
  );
});

it('says which roles this text is sent to, in words and not as statuses', () => {
  editor();

  const tags = screen.getAllByTestId('context-role');
  expect(tags.map((tag) => tag.getAttribute('data-role-name'))).toEqual([
    'investigator',
    'subagent',
  ]);
  expect(tags.map((tag) => tag.textContent)).toEqual(['Investigator', 'Subagent']);
  // Through the status badge an unrecognised word takes the hollow ring that
  // means "a status this console has never heard of", so a list of audiences
  // rendered as a row of unticked checkboxes. A role is not a state.
  for (const tag of tags) {
    expect(tag.querySelector('[data-shape]')).toBeNull();
  }
});

it('shows what the context costs against the budget the deployment declares', () => {
  editor();

  expect(screen.getByTestId('context-budget')).toHaveTextContent('240 of 1200 tokens');
});

it('explains the consequence of the budget before anybody is anywhere near it', () => {
  editor();

  expect(screen.getByTestId('context-budget-consequence')).toHaveTextContent(
    LABELS.budgetConsequence,
  );
});

it('keeps explaining the consequence once the budget is actually exceeded', async () => {
  answerWith(REFUSED);
  editor();

  await editSection('network', 'a very long section');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-budget-consequence')).toHaveTextContent(
    LABELS.budgetConsequence,
  );
});

it('leaves a reader the text and none of the controls', () => {
  editor({ writable: false });

  expect(screen.queryByTestId('ask-context-preview')).not.toBeInTheDocument();
  expect(screen.getByText('MTU is 1450.')).toBeInTheDocument();
});

// --- Preview before save -----------------------------------------------------

it('will not preview at all until something has been changed', () => {
  editor();

  expect(screen.getByTestId('ask-context-preview')).toBeDisabled();
});

it('explains why "Show me the prompt" is disabled before anything has changed', () => {
  editor();

  expect(screen.getByTestId('ask-context-preview')).toHaveAttribute(
    'title',
    LABELS.previewDisabledReason,
  );
});

it('carries no disabled explanation once there is something to preview', async () => {
  editor();
  await editSection('network', 'MTU is 1450 over a 1450 underlay.');

  expect(screen.getByTestId('ask-context-preview')).not.toBeDisabled();
  expect(screen.getByTestId('ask-context-preview')).not.toHaveAttribute('title');
});

it('shows the prompt the deployment assembled, not one it built itself', async () => {
  editor();

  await editSection('network', 'MTU is 1450 over a 1450 underlay.');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-prompt')).toHaveTextContent(
    'You are an SRE investigator.',
  );
  expect(screen.getByTestId('context-prompt')).toHaveTextContent('MTU is 1450.');
});

it('offers no save until the prompt has come back', async () => {
  editor();
  await editSection('network', 'MTU is 1450 over a 1450 underlay.');

  expect(screen.queryByTestId('save-context')).not.toBeInTheDocument();
  expect(screen.getByTestId('context-preview-first')).toBeInTheDocument();

  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('save-context')).toBeInTheDocument();
});

it('withdraws the save when the text changes after the preview', async () => {
  editor();
  await editSection('network', 'MTU is 1450 over a 1450 underlay.');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  await editSection('network', 'Something else entirely.');

  expect(screen.queryByTestId('save-context')).not.toBeInTheDocument();
});

it('saves the document the preview was taken of', async () => {
  editor();
  await editSection('network', 'MTU is 1450 over a 1450 underlay.');
  await userEvent.click(screen.getByTestId('ask-context-preview'));
  await userEvent.click(screen.getByTestId('save-context'));

  const save = sent.find((entry) => entry.operation === 'save');
  const patch: unknown = Reflect.get(Object(save?.payload), 'patch');
  const agents: unknown = Reflect.get(Object(patch), 'agents');
  const context: unknown = Reflect.get(Object(agents), 'operating_context');
  const sections: unknown = Reflect.get(Object(context), 'sections');

  expect(Reflect.get(Object(sections), 'network')).toBe(
    'MTU is 1450 over a 1450 underlay.',
  );
  expect(screen.getByTestId('context-saved')).toBeInTheDocument();
});

// --- What the deployment refuses ---------------------------------------------

it('names a refusal and offers no save for it', async () => {
  answerWith(REFUSED);
  editor();

  await editSection('network', 'a very long section');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-errors')).toHaveTextContent(
    'is 3000 tokens over the 1200-token operating-context budget',
  );
  expect(screen.queryByTestId('save-context')).not.toBeInTheDocument();
});

it('shows no prompt for a document the deployment would refuse', async () => {
  answerWith(REFUSED);
  editor();

  await editSection('network', 'a very long section');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.queryByTestId('context-prompt')).not.toBeInTheDocument();
});

it('reports the deployment being over budget with the deployment’s own count', async () => {
  answerWith(REFUSED);
  editor();

  await editSection('network', 'a very long section');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-over-budget')).toBeInTheDocument();
  expect(screen.getByTestId('context-budget')).toHaveTextContent('4200 of 1200 tokens');
});

it('says the deployment could not be reached rather than pretending it saved', async () => {
  vi.stubGlobal('fetch', () => Promise.reject(new TypeError('offline')));
  editor();

  await editSection('network', 'MTU is 1450 over a 1450 underlay.');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-failure')).toHaveTextContent(LABELS.unreachable);
});

// --- The starting document ---------------------------------------------------

it('offers the derived template only where the deployment sent one', () => {
  editor({ template: [] });

  expect(screen.queryByTestId('use-template')).not.toBeInTheDocument();
});

it('names what the starting-document button does, rather than "start from this"', () => {
  editor({ sections: [], template: TEMPLATE });

  const button = screen.getByTestId('use-template');
  expect(button).toHaveTextContent(LABELS.templateUse);
  expect(button.textContent).not.toBe('Start from this');
  expect(button).toHaveAttribute('title', LABELS.templateLead);
});

it('fills the sections from the template rather than saving it', async () => {
  editor({ sections: [], template: TEMPLATE });

  await userEvent.click(screen.getByTestId('use-template'));

  expect(screen.getByTestId('context-section')).toHaveAttribute(
    'data-section',
    'Who is called, and when',
  );
  expect(sent).toEqual([]);
});

it('carries the deployment’s own refusal reason rather than a generic one', async () => {
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      new Response(
        JSON.stringify({ ok: false, reason: 'that section names a secret' }),
        {
          status: 400,
          headers: { 'content-type': 'application/json' },
        },
      ),
    ),
  );
  editor();

  await editSection('network', 'a token');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-failure')).toHaveTextContent(
    'that section names a secret',
  );
});

it('falls back to its own wording when the deployment gives no reason', async () => {
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      new Response('{}', {
        status: 500,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  );
  editor();

  await editSection('network', 'anything');
  await userEvent.click(screen.getByTestId('ask-context-preview'));

  expect(screen.getByTestId('context-failure')).toHaveTextContent(LABELS.failed);
});

it('marks a section no level has supplied yet as unset', () => {
  editor({ sections: [{ name: 'change windows', body: '', provenance: '' }] });

  expect(screen.getByTestId('section-provenance')).toHaveTextContent('unset');
});

it('does not re-add a section the template shares with what is already written', async () => {
  editor({
    sections: [
      { name: 'Who is called, and when', body: 'Anna, then Bo.', provenance: 'acme' },
    ],
    template: TEMPLATE,
  });

  await userEvent.click(screen.getByTestId('use-template'));

  expect(screen.getAllByTestId('context-section')).toHaveLength(1);
});

it('adds a section by name', async () => {
  editor({ sections: [] });

  await userEvent.type(screen.getByLabelText(LABELS.sectionName), 'change windows');
  await userEvent.click(screen.getByTestId('add-section'));

  expect(screen.getByTestId('context-section')).toHaveAttribute(
    'data-section',
    'change windows',
  );
});

it('explains why "Add a section" is disabled before a name is typed', () => {
  editor({ sections: [] });

  expect(screen.getByTestId('add-section')).toHaveAttribute(
    'title',
    LABELS.addSectionDisabledReason,
  );
});

it('carries no disabled explanation once a name has been typed', async () => {
  editor({ sections: [] });

  await userEvent.type(screen.getByLabelText(LABELS.sectionName), 'change windows');

  expect(screen.getByTestId('add-section')).not.toBeDisabled();
  expect(screen.getByTestId('add-section')).not.toHaveAttribute('title');
});
