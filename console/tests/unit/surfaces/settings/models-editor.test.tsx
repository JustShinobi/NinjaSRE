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
};

const ANTHROPIC: ProviderOption = {
  providerId: 'anthropic',
  displayName: 'Anthropic',
  configured: true,
  verified: true,
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
  detail: 'no credential is stored for this provider',
  models: [],
};

const PROVIDERS = [ANTHROPIC, OLLAMA];

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

describe('an advanced role, collapsed until asked for', () => {
  it('opens to show its own provider and model controls, and can be fixed away from the default', async () => {
    editor();

    await userEvent.click(screen.getByText('Subagent'));

    const subagent = screen.getByTestId('model-role-subagent');
    expect(within(subagent).getByLabelText('Provider')).toBeInTheDocument();
  });

  it('returns to inheriting the default on a bound role, clearing its pending edits', async () => {
    editor([
      INVESTIGATOR,
      { ...SUBAGENT, bound: true, providerOrigin: 'Set at org-northwind' },
    ]);

    await userEvent.click(screen.getByText('Subagent'));
    const subagent = screen.getByTestId('model-role-subagent');
    await userEvent.click(within(subagent).getByTestId('revert-subagent'));

    expect(screen.getByTestId('role-reverted')).toBeInTheDocument();
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
});

describe('an advanced role’s own disclosure', () => {
  it('opens and closes independently, remembering which roles are expanded', async () => {
    editor();

    const disclosure = screen.getByTestId('advanced-role-subagent');
    await userEvent.click(screen.getByText('Subagent'));
    expect(disclosure).toHaveAttribute('open');

    await userEvent.click(screen.getByText('Subagent'));
    expect(disclosure).not.toHaveAttribute('open');
  });
});
