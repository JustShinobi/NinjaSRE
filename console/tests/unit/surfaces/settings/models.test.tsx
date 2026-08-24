import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { surfaceContext } from '@/surfaces/context';
import { ModelsSettingsScreen } from '@/surfaces/settings/models';

/**
 * Models & providers: choosing what drives an investigation without opening
 * the raw editor.
 *
 * Every fixture below mirrors the gateway's own `ProviderView` /
 * `ProviderDetailView` shape exactly — `configured`, `verified`, `detail`,
 * `model_capabilities` — never a spelling this suite invented, so a drift
 * between what the route actually serves and what this test pretends it
 * serves fails here rather than only in a browser.
 */

const BASE = ['http:', '//fixtures.invalid'].join('');

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === 'ninjasre_session' ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

const NODE = 'org-northwind';

const SINGLE_NODE = {
  kind: 'organisation',
  name: 'Northwind',
  node_id: NODE,
  parent_id: null,
};

const WRITER = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  email: 'avery.lockhart@example.invalid',
  kind: 'person',
  roles: ['owner'],
  permissions: ['config.read', 'config.write'],
  team_node_id: NODE,
  impersonated_by: null,
  impersonating: false,
};

const READER = { ...WRITER, principal_id: 'user-viewer', permissions: ['config.read'] };

const PROVIDER_IDS = [
  'anthropic',
  'openai',
  'azure_openai',
  'aws_bedrock',
  'google_gemini',
  'google_vertex_ai',
  'openrouter',
  'nvidia_nim',
  'ollama',
] as const;

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

interface ProviderFixture {
  readonly configured?: boolean;
  readonly verified?: boolean;
  /** Overrides the derived readiness — the only way this fixture can represent `failing`. */
  readonly readiness?: string;
  readonly detail?: string;
  readonly models?: readonly {
    readonly model_id: string;
    readonly supports_tools: boolean | null;
  }[];
}

/** The checklist's own four-word readiness, mirrored from the two booleans a fixture sets. */
function readinessOf(over: ProviderFixture): string {
  if (over.readiness !== undefined) return over.readiness;
  if (over.verified === true) return 'verified';
  if (over.configured === true) return 'configured';
  return 'absent';
}

function providerDetail(id: string, over: ProviderFixture = {}): unknown {
  return {
    provider_id: id,
    display_name: id,
    local: id === 'ollama',
    configured: over.configured ?? false,
    verified: over.verified ?? false,
    readiness: readinessOf(over),
    default_model: 'default-model',
    detail:
      over.detail ??
      (over.configured ? 'no verification has been run' : 'no credential is stored'),
    fields: [],
    guidance: '',
    where_to_get_it: '',
    models: (over.models ?? []).map((m) => m.model_id),
    model_capabilities: over.models ?? [],
    install_hint: '',
  };
}

interface Stub {
  readonly principal?: unknown;
  readonly values?: unknown;
  readonly provenance?: Readonly<Record<string, string>>;
  readonly providers?: Readonly<Record<string, ProviderFixture>>;
  readonly setupComplete?: boolean;
}

function serveModels({
  principal = WRITER,
  values = {},
  provenance = {},
  providers = {},
  setupComplete = true,
}: Stub): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/auth/me') return Promise.resolve(respond(principal));
    if (path === '/v1/config')
      return Promise.resolve(respond({ nodes: [SINGLE_NODE] }));
    if (path === `/v1/config/${NODE}`) {
      return Promise.resolve(respond({ node_id: NODE, values, provenance }));
    }
    if (path === '/v1/providers') {
      return Promise.resolve(
        respond({
          providers: PROVIDER_IDS.map((id) => {
            const over = providers[id] ?? {};
            return {
              provider_id: id,
              display_name: id,
              local: id === 'ollama',
              configured: over.configured ?? false,
              verified: over.verified ?? false,
              readiness: readinessOf(over),
              default_model: 'default-model',
              detail:
                over.detail ??
                (over.configured
                  ? 'no verification has been run'
                  : 'no credential is stored'),
            };
          }),
        }),
      );
    }
    const detailMatch = PROVIDER_IDS.find((id) => path === `/v1/providers/${id}`);
    if (detailMatch !== undefined) {
      return Promise.resolve(
        respond(providerDetail(detailMatch, providers[detailMatch])),
      );
    }
    if (path === '/v1/setup/checklist') {
      return Promise.resolve(
        respond({
          complete: setupComplete,
          provider: setupComplete ? 'verified' : 'absent',
          integrations: [],
          steps: [{ name: 'model-provider', state: setupComplete ? 'done' : 'ready' }],
        }),
      );
    }
    return Promise.resolve(respond({}, 404));
  });
}

async function renderModels(
  query: Readonly<Record<string, string>> = {},
): Promise<void> {
  render(await ModelsSettingsScreen(await surfaceContext(query)));
}

describe('the investigator role, the one every operator opens this page for', () => {
  it('shows the active provider, its credential chip, and the chosen model', async () => {
    serveModels({
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-sonnet-5' } },
      },
      provenance: {
        'models.investigator.provider': NODE,
        'models.investigator.model': NODE,
      },
      providers: {
        anthropic: {
          configured: true,
          verified: true,
          models: [
            { model_id: 'claude-sonnet-5', supports_tools: true },
            { model_id: 'claude-haiku-4-5', supports_tools: true },
          ],
        },
      },
    });

    await renderModels();

    // The credential chip moved to the state card that opens the role — the
    // three-line paragraph this feature retires never had a chip at all.
    expect(screen.getByTestId('provider-state-chip')).toHaveTextContent(/verified/i);
    const investigator = screen.getByTestId('model-role-investigator');
    const modelSelect = within(investigator).getByRole('combobox', { name: /model/i });
    expect(modelSelect).toHaveValue('claude-sonnet-5');
    expect(modelSelect).toHaveTextContent(/supports tool calling/i);
  });

  it('names a live check that failed — the check, its consequence, and an exit', async () => {
    serveModels({
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-sonnet-5' } },
      },
      provenance: {},
      providers: {
        anthropic: {
          configured: true,
          verified: true,
          models: [{ model_id: 'claude-sonnet-5', supports_tools: true }],
        },
      },
    });
    // Verifying is gesture-triggered and costs tokens, so nothing about a
    // failed check is known until "Check again" actually asks — the served
    // provider list and detail never carry per-check results, only the
    // rounded-up `verified` boolean the state chip already reads.
    const scenario = global.fetch;
    vi.stubGlobal('fetch', (input: unknown, init?: RequestInit) => {
      const path = new URL(String(input), BASE).pathname;
      if (path === '/api/verify') {
        return Promise.resolve(
          respond({
            verified: false,
            reason: 'the last check answered without calling the tool',
            checks: [
              {
                name: 'tool calling',
                status: 'failed',
                detail: 'no tool call was made',
                duration_ms: 40,
              },
            ],
          }),
        );
      }
      return (scenario as (i: unknown, init?: RequestInit) => Promise<Response>)(
        input,
        init,
      );
    });

    await renderModels();
    await userEvent.click(screen.getByTestId('check-again'));

    const chip = await screen.findByTestId('verification-error-chip');
    expect(chip).toHaveTextContent(/tool calling/i);
    expect(screen.getByTestId('verification-error-detail')).toHaveTextContent(
      'no tool call was made',
    );
    expect(screen.getByTestId('verification-error-consequence')).toHaveTextContent(
      /sequences of tool calls/i,
    );
    expect(screen.getByTestId('verification-error-exit')).toHaveTextContent(
      'Choose a model from the verified list',
    );
  });

  it('says a model the registry actively marks unsupported does not support tool calling', async () => {
    serveModels({
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-haiku-4-5' } },
      },
      provenance: {},
      providers: {
        anthropic: {
          configured: true,
          verified: true,
          models: [{ model_id: 'claude-haiku-4-5', supports_tools: false }],
        },
      },
    });

    await renderModels();

    const investigator = screen.getByTestId('model-role-investigator');
    expect(
      within(investigator).getByRole('combobox', { name: /model/i }),
    ).toHaveTextContent(/does not support tool calling/i);
  });

  it('does not let one provider’s own failed read blank the whole panel', async () => {
    // The comment this behaviour lives under: nine independent reads, and one
    // provider's own hiccup must not take the rest down with it.
    serveModels({
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-sonnet-5' } },
      },
      provenance: {},
      providers: {
        anthropic: {
          configured: true,
          verified: true,
          models: [{ model_id: 'claude-sonnet-5', supports_tools: true }],
        },
      },
    });
    const scenario = global.fetch;
    vi.stubGlobal('fetch', (input: unknown) => {
      const path = new URL(String(input), BASE).pathname;
      if (path === '/v1/providers/openai') {
        return Promise.resolve(respond({ error: 'unavailable' }, 503));
      }
      return (scenario as (i: unknown) => Promise<Response>)(input);
    });

    await renderModels();

    // The failing provider's own row still opens under the collapsed
    // disclosure, empty of what it could not read, rather than the whole
    // page reporting a dependency error.
    const investigator = screen.getByTestId('model-role-investigator');
    expect(within(investigator).getByLabelText('Provider')).toHaveValue('anthropic');
  });

  it('says a model the registry has no row for is not known to support tool calling, never that it does not', async () => {
    serveModels({
      values: {
        models: { investigator: { provider: 'ollama', model: 'a-local-model' } },
      },
      provenance: {},
      providers: {
        ollama: {
          configured: true,
          verified: true,
          models: [{ model_id: 'a-local-model', supports_tools: null }],
        },
      },
    });

    await renderModels();

    const investigator = screen.getByTestId('model-role-investigator');
    expect(
      within(investigator).queryByText(/does not support/i),
    ).not.toBeInTheDocument();
    expect(
      within(investigator).getByText(/not confirmed|not known/i),
    ).toBeInTheDocument();
  });

  it('blocks the model choice with an explanation and a way to connect the credential, for a provider with none stored', async () => {
    serveModels({
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-sonnet-5' } },
      },
      provenance: {},
      providers: { anthropic: { configured: false } },
    });

    await renderModels();

    const investigator = screen.getByTestId('model-role-investigator');
    expect(
      within(investigator).getByText(/no credential is stored/i),
    ).toBeInTheDocument();
    const modelControl = within(investigator).getByLabelText(/model/i);
    expect(modelControl).toBeDisabled();
    const connect = within(investigator).getByTestId('connect-credential');
    expect(connect).toHaveAttribute(
      'href',
      expect.stringContaining('/integrations/anthropic'),
    );
  });
});

describe('the seven advanced roles', () => {
  it('are collapsed, and say they inherit the default until expanded', async () => {
    serveModels({
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-sonnet-5' } },
      },
      provenance: {},
      providers: { anthropic: { configured: true, verified: true } },
    });

    await renderModels();

    const advanced = screen.getByTestId('advanced-roles');
    expect(advanced).toHaveTextContent(/subagent/i);
    expect(advanced).toHaveTextContent(/inherit/i);
    // Collapsed: the per-role provider control is not reachable without opening it.
    expect(
      screen.queryByTestId('model-role-subagent-provider'),
    ).not.toBeInTheDocument();
  });

  it('shows the origin of a role explicitly bound away from the default', async () => {
    serveModels({
      values: {
        models: {
          investigator: { provider: 'anthropic', model: 'claude-sonnet-5' },
          subagent: { provider: 'anthropic', model: 'claude-haiku-4-5' },
        },
      },
      provenance: { 'models.subagent.provider': NODE, 'models.subagent.model': NODE },
      providers: { anthropic: { configured: true, verified: true } },
    });

    await renderModels();

    // Collapsed until asked for: the origin only reaches the DOM once the
    // shared disclosure is open, same as every other advanced-role control.
    await userEvent.click(screen.getByTestId('advanced-roles-toggle'));

    expect(screen.getByTestId('advanced-roles')).toHaveTextContent(NODE);
  });
});

describe('a viewer who may not write configuration', () => {
  it('renders every role read-only, with no save control', async () => {
    serveModels({
      principal: READER,
      values: {
        models: { investigator: { provider: 'anthropic', model: 'claude-sonnet-5' } },
      },
      provenance: {},
      providers: { anthropic: { configured: true, verified: true } },
    });

    await renderModels();

    expect(screen.queryByTestId('save-and-verify')).not.toBeInTheDocument();
    expect(screen.queryByTestId('test-without-saving')).not.toBeInTheDocument();
  });
});

describe('the setup wizard handover', () => {
  it('offers the way back while setup is not finished', async () => {
    serveModels({
      values: {},
      provenance: {},
      providers: { anthropic: { configured: true, verified: true } },
      setupComplete: false,
    });

    await renderModels({ return: 'setup' });

    expect(screen.getByTestId('setup-return-banner')).toBeInTheDocument();
  });
});
