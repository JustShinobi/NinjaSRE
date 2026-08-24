import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  ModelsEditor,
  type ProviderOption,
  type RoleValue,
} from '@/surfaces/settings/models-editor';

/**
 * The client half of Models & providers, exercised directly — the same
 * reasoning `autonomy-editor.test.tsx` follows for `AutonomyEditor`: a
 * component with this much of its own state deserves interaction tests that
 * do not also have to stand up a whole page's worth of server reads.
 */

const LABELS = {
  provider: 'Provider',
  knownModel: 'Model',
  freeModel: 'Model',
  toolCallingSupported: ' — supports tool calling',
  toolCallingUnsupported: ' — does not support tool calling',
  toolCallingUnknown: ' — tool calling not confirmed',
  verificationNote: 'Last verification:',
  notConnected: 'No credential is stored for this provider.',
  connectCredential: 'Connect a credential',
  advancedTitle: 'Advanced roles',
  advancedLead: 'Advanced roles inherit the default unless fixed here.',
  inherits: 'Inherits the default',
  revert: 'Return to inheriting the default',
  reverted: 'Will inherit the default once saved',
  saveAndVerify: 'Save and verify',
  saving: 'Saving…',
  testWithoutSaving: 'Test without saving',
  verifying: 'Verifying…',
  verified: 'A check reached this provider and it answered.',
  verificationFailed: 'The check did not pass.',
  saved: 'Saved.',
  failed: 'The deployment refused this change.',
  unreachable: 'The deployment could not be reached.',
  before: 'Now',
  after: 'After saving',
  nothingChanges: 'Nothing would change.',
  origin: 'Set at',
  checkAgain: 'Check again',
  checking: 'Checking…',
  chooseVerifiedModel: 'Choose a model from the verified list',
  reloadModels: 'Reload models',
  reloadingModels: 'Reloading…',
  staticModelsLabel: 'Static list — the endpoint could not be asked.',
  advancedSummaryAll: '{total} roles, all inherit the default',
  advancedSummaryPartial: '{total} roles, {inheriting} inherit the default',
  checkLabels: {
    credentials: 'Credentials',
    authentication: 'Authentication',
    'tool calling': 'Tool calling',
    'structured output': 'Structured output',
    streaming: 'Streaming',
  },
  checkConsequences: {
    credentials: 'No credential resolved, so nothing was called.',
    authentication: 'The endpoint rejected the credential.',
    'tool calling': 'Investigations are sequences of tool calls.',
    'structured output': 'The pipeline reads typed documents, not prose.',
    streaming: 'Streamed output would not reach the console.',
  },
};

const ANTHROPIC: ProviderOption = {
  providerId: 'anthropic',
  displayName: 'Anthropic',
  configured: true,
  verified: true,
  readiness: 'verified',
  detail: 'a check reached this provider and it answered',
  models: [
    { modelId: 'claude-sonnet-5', supportsTools: true },
    { modelId: 'claude-haiku-4-5', supportsTools: false },
  ],
};

const OLLAMA: ProviderOption = {
  providerId: 'ollama',
  displayName: 'Ollama',
  configured: false,
  verified: false,
  readiness: 'absent',
  detail: 'no credential is stored for this provider',
  models: [],
};

const OPENAI: ProviderOption = {
  providerId: 'openai',
  displayName: 'OpenAI',
  configured: true,
  verified: false,
  readiness: 'configured',
  detail: 'no verification has been run against this deployment',
  models: [{ modelId: 'gpt-5', supportsTools: true }],
};

const MISTRAL: ProviderOption = {
  providerId: 'mistral',
  displayName: 'Mistral',
  configured: true,
  verified: false,
  readiness: 'failing',
  detail: 'the last check of this provider did not pass: it did not answer',
  models: [{ modelId: 'mistral-large', supportsTools: true }],
};

const PROVIDERS = [ANTHROPIC, OLLAMA, OPENAI, MISTRAL];

const INVESTIGATOR: RoleValue = {
  role: 'investigator',
  label: 'Investigator',
  provider: 'anthropic',
  model: 'claude-sonnet-5',
  bound: true,
  providerOrigin: 'Set at org-northwind',
  modelOrigin: 'Set at org-northwind',
};

const SUBAGENT: RoleValue = {
  role: 'subagent',
  label: 'Subagent',
  provider: 'anthropic',
  model: 'claude-sonnet-5',
  bound: false,
  providerOrigin: 'Deployment default',
  modelOrigin: 'Deployment default',
};

function editor(roles: readonly RoleValue[] = [INVESTIGATOR, SUBAGENT]): void {
  render(
    <ModelsEditor
      nodeId="org-northwind"
      locale="en"
      writable
      providers={PROVIDERS}
      roles={roles}
      labels={LABELS}
    />,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a model that fails the registry’s own tool-calling check', () => {
  it('is annotated as not supporting it, in the option text', async () => {
    editor();
    const investigator = screen.getByTestId('model-role-investigator');
    const select = within(investigator).getByLabelText('Model');

    await userEvent.selectOptions(select, 'claude-haiku-4-5');

    expect(select).toHaveTextContent(/does not support tool calling/i);
  });
});

describe('the seven advanced roles, collapsed into one line until asked for', () => {
  it('declares how many there are and that they inherit, before anything is expanded', () => {
    editor();

    expect(screen.getByTestId('advanced-roles-summary')).toHaveTextContent('1 roles');
    // Not rendered until the disclosure is opened — the whole point of
    // collapsing them into one line rather than seven accordions.
    expect(screen.queryByTestId('model-role-subagent')).not.toBeInTheDocument();
  });

  it('opens every advanced role together, showing its own provider and model controls', async () => {
    editor();

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));

    const subagent = screen.getByTestId('model-role-subagent');
    expect(within(subagent).getByLabelText('Provider')).toBeInTheDocument();
  });

  it('returns to inheriting the default on a bound role, clearing its pending edits', async () => {
    editor([
      INVESTIGATOR,
      { ...SUBAGENT, bound: true, providerOrigin: 'Set at org-northwind' },
    ]);

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));
    const subagent = screen.getByTestId('model-role-subagent');
    await userEvent.click(within(subagent).getByTestId('revert-subagent'));

    expect(within(subagent).getByTestId('role-reverted')).toBeInTheDocument();
  });
});

describe('a provider with no credential stored', () => {
  it('blocks the model choice and offers the way to connect one', () => {
    editor([{ ...INVESTIGATOR, provider: 'ollama', model: '' }]);

    const investigator = screen.getByTestId('model-role-investigator');
    expect(within(investigator).getByLabelText('Model')).toBeDisabled();
    expect(within(investigator).getByTestId('connect-credential')).toHaveAttribute(
      'href',
      '/integrations/ollama',
    );
  });

  it('draws an advanced role bound to a provider this catalogue no longer lists', async () => {
    // A role's own configuration can outlive the catalogue — a provider this
    // build retired, or one a viewer without config.write cannot see. The
    // console's own state, "nothing here to say is verified", not a fifth
    // guess dressed as one of the four real ones.
    editor([
      INVESTIGATOR,
      { ...SUBAGENT, provider: 'retired-vendor', model: 'whatever-it-ran' },
    ]);

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));

    const subagent = screen.getByTestId('model-role-subagent');
    const chip = subagent.querySelector('[data-credential-status]');
    expect(chip).not.toBeNull();
    // "no-provider-selected" is deliberately not one of the five canonical
    // words — it is this console's own state, not a fact the deployment
    // reported — so it reads as the honest "unknown" fallback rather than
    // a guessed status the deployment never sent.
    expect(chip).toHaveAttribute('data-credential-status', 'unknown');
  });

  it('draws an advanced role on a stored credential nobody has checked yet, distinctly from a verified one', async () => {
    editor([INVESTIGATOR, { ...SUBAGENT, provider: 'openai', model: 'gpt-5' }]);

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));

    const subagent = screen.getByTestId('model-role-subagent');
    const chip = subagent.querySelector('[data-credential-status]');
    expect(chip).toHaveAttribute('data-credential-status', 'stored');
  });

  it('draws an advanced role whose last check failed as failing, never as stored', async () => {
    editor([INVESTIGATOR, { ...SUBAGENT, provider: 'mistral', model: 'mistral-large' }]);

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));

    const subagent = screen.getByTestId('model-role-subagent');
    const chip = subagent.querySelector('[data-credential-status]');
    expect(chip).toHaveAttribute('data-credential-status', 'failing');
  });
});

describe("the investigator's own headline chip", () => {
  it('reads failing, not stored, when the provider bound to it last failed its check', () => {
    editor([{ ...INVESTIGATOR, provider: 'mistral', model: 'mistral-large' }, SUBAGENT]);

    const chip = screen.getByTestId('provider-state-chip');
    expect(chip).toHaveAttribute('data-credential-status', 'failing');
  });

  it('reads verified when the bound provider last passed its check', () => {
    editor();

    const chip = screen.getByTestId('provider-state-chip');
    expect(chip).toHaveAttribute('data-credential-status', 'verified');
  });
});

describe('verifying without saving', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(JSON.stringify({ ok: true, reachable: true, verified: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      ),
    );
  });

  it('reports the deployment’s verdict for the currently saved provider', async () => {
    editor();

    await userEvent.click(screen.getByTestId('test-without-saving'));

    expect(await screen.findByTestId('verify-result')).toHaveTextContent(
      LABELS.verified,
    );
  });

  it('reports the deployment as unreachable rather than as having refused', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('fetch failed')));
    editor();

    await userEvent.click(screen.getByTestId('test-without-saving'));

    expect(await screen.findByTestId('verify-result')).toHaveTextContent(
      LABELS.unreachable,
    );
  });
});

describe('saving and verifying together', () => {
  it('verifies the investigator’s provider directly when nothing is pending', async () => {
    vi.stubGlobal('fetch', (input: unknown) => {
      expect(String(input)).toBe('/api/verify');
      return Promise.resolve(
        new Response(JSON.stringify({ ok: true, reachable: true, verified: true }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });
    editor();

    await userEvent.click(screen.getByTestId('save-and-verify'));

    expect(await screen.findByTestId('verify-result')).toHaveTextContent(
      LABELS.verified,
    );
  });

  it('stops before saving when the preview reports the change would be refused', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', (input: unknown) => {
      const url = String(input);
      calls.push(url);
      if (url === '/api/preview') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              changes: [],
              values: {},
              provenance: {},
              accepted: false,
              errors: [],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });
    editor();

    const investigator = screen.getByTestId('model-role-investigator');
    await userEvent.selectOptions(
      within(investigator).getByLabelText('Model'),
      'claude-haiku-4-5',
    );
    await userEvent.click(screen.getByTestId('save-and-verify'));

    await screen.findByTestId('models-failure').catch(() => null);
    expect(calls).toContain('/api/preview');
    expect(calls).not.toContain('/api/config');
  });

  it('saves a changed provider once its preview is accepted, then reports what saving resolved to', async () => {
    vi.stubGlobal('fetch', (input: unknown) => {
      const url = String(input);
      if (url === '/api/preview') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              changes: [
                {
                  path: 'models.investigator.provider',
                  before: 'anthropic',
                  after: 'ollama',
                },
              ],
              values: {},
              provenance: {},
              accepted: true,
              errors: [],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      if (url === '/api/config') {
        return Promise.resolve(
          new Response(JSON.stringify({ ok: true, values: {} }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ok: true,
            reachable: true,
            verified: false,
            reason: 'no tool call was made',
          }),
          {
            status: 200,
            headers: { 'content-type': 'application/json' },
          },
        ),
      );
    });
    editor();

    const investigator = screen.getByTestId('model-role-investigator');
    await userEvent.selectOptions(
      within(investigator).getByLabelText('Provider'),
      'ollama',
    );
    await userEvent.click(screen.getByTestId('save-and-verify'));

    expect(await screen.findByTestId('models-saved')).toBeInTheDocument();
    expect(await screen.findByTestId('verify-result')).toHaveTextContent(
      'no tool call was made',
    );
  });

  it('reports a genuine save failure — not a stalled preview — and never verifies a change that did not land', async () => {
    vi.stubGlobal('fetch', (input: unknown) => {
      const url = String(input);
      if (url === '/api/preview') {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              changes: [
                {
                  path: 'models.investigator.provider',
                  before: 'anthropic',
                  after: 'ollama',
                },
              ],
              values: {},
              provenance: {},
              accepted: true,
              errors: [],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          ),
        );
      }
      if (url === '/api/config') {
        return Promise.resolve(
          new Response(
            JSON.stringify({ ok: false, reason: 'the node changed underneath it' }),
            {
              status: 409,
              headers: { 'content-type': 'application/json' },
            },
          ),
        );
      }
      throw new Error(`unexpected call to ${url} once the save itself already failed`);
    });
    editor();

    const investigator = screen.getByTestId('model-role-investigator');
    await userEvent.selectOptions(
      within(investigator).getByLabelText('Provider'),
      'ollama',
    );
    await userEvent.click(screen.getByTestId('save-and-verify'));

    expect(await screen.findByTestId('models-failure')).toBeInTheDocument();
    expect(screen.queryByTestId('models-saved')).not.toBeInTheDocument();
    // A verify call that follows a failed save would grade a change that
    // never landed — the assertion above (no further fetch reached) is what
    // `saveAndVerify`'s own early return on a failed save exists to keep true.
  });
});

describe('the advanced roles’ shared disclosure', () => {
  it('opens and closes all of them together', async () => {
    editor();

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));
    expect(screen.getByTestId('model-role-subagent')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));
    expect(screen.queryByTestId('model-role-subagent')).not.toBeInTheDocument();
  });
});

describe('the investigator’s own model listing', () => {
  it('replaces the static registry once the endpoint answers, with names it never had', async () => {
    vi.stubGlobal('fetch', (input: unknown) => {
      expect(String(input)).toContain('/api/models?provider=anthropic');
      return Promise.resolve(
        new Response(
          JSON.stringify({
            models: [{ model_id: 'claude-opus-5', display_name: 'Claude Opus 5' }],
            source: 'endpoint',
            reason: '',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      );
    });
    editor();

    const investigator = screen.getByTestId('model-role-investigator');
    expect(await within(investigator).findByText('Claude Opus 5')).toBeInTheDocument();
    expect(screen.queryByTestId('model-list-static-label')).not.toBeInTheDocument();
  });

  it('labels the fallback honestly when the endpoint could not be asked', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            models: [],
            source: 'static',
            reason: "anthropic's listing could not be used",
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );
    editor();

    expect(await screen.findByTestId('model-list-static-label')).toHaveTextContent(
      LABELS.staticModelsLabel,
    );
  });

  it('reloads on request, ignoring whatever this deployment already cached', async () => {
    let calls = 0;
    vi.stubGlobal('fetch', (input: unknown) => {
      calls += 1;
      expect(String(input)).toContain(
        calls > 1 ? 'refresh=true' : 'provider=anthropic',
      );
      return Promise.resolve(
        new Response(JSON.stringify({ models: [], source: 'endpoint', reason: '' }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });
    editor();
    await screen.findByTestId('reload-models');

    await userEvent.click(screen.getByTestId('reload-models'));

    expect(calls).toBeGreaterThanOrEqual(2);
  });
});
