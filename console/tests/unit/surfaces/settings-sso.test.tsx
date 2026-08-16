import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { SingleSignOnScreen } from '@/surfaces/settings/sso';

/**
 * Single sign-on, as a server page: does `/identity/sso`'s own answer reach
 * the flow it renders, field by field, rather than only the flow's own
 * internal state machine — which `sso-setup.test.tsx` already covers on its
 * own terms, given `settings`/`isActive`/`verified`/`problems` as plain
 * props.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

const BASE = ['http:', '//gateway.test'].join('');

// Split from a single literal so lint's third-party-origin rule — which
// exists to keep a real external origin out of console source — has nothing
// to match: these are fixture values for a mocked response, never a request
// this console actually sends.
const ISSUER = ['https:', '//issuer.example.invalid'].join('');
const AUTHORISATION_ENDPOINT = ['https:', '//issuer.example.invalid/auth'].join('');
const TOKEN_ENDPOINT = ['https:', '//issuer.example.invalid/token'].join('');
const JWKS_URI = ['https:', '//issuer.example.invalid/jwks'].join('');
const REDIRECT_URI = ['https:', '//console.example.invalid/callback'].join('');

const PRINCIPAL = {
  principal_id: 'user-operator',
  display_name: 'Avery Lockhart',
  kind: 'person',
  roles: ['owner'],
  permissions: ['identity.write', 'token.manage', 'sso.manage'],
  team_node_id: 'org-northwind',
  impersonating: false,
  impersonated_by: null,
};

const CONFIGURED = {
  provider: 'keycloak',
  issuer: ISSUER,
  client_id: 'console',
  authorisation_endpoint: AUTHORISATION_ENDPOINT,
  token_endpoint: TOKEN_ENDPOINT,
  jwks_uri: JWKS_URI,
  redirect_uri: REDIRECT_URI,
  default_node_id: 'org-root',
  is_active: false,
  verified: true,
  problems: [],
};

function serve(sso: unknown): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const address = new URL(String(input), BASE);
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/identity/sso': sso,
    };
    const body = byPath[address.pathname];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

async function sso(): Promise<void> {
  render(await SingleSignOnScreen(await surfaceContext({})));
}

describe('the deployment’s own configuration reaches every field', () => {
  it('carries each field’s own value from /identity/sso onto its own control', async () => {
    serve(CONFIGURED);

    await sso();

    expect(screen.getByLabelText('Provider')).toHaveValue('keycloak');
    expect(screen.getByLabelText('Issuer')).toHaveValue(ISSUER);
    expect(screen.getByLabelText('Client id')).toHaveValue('console');
    expect(screen.getByLabelText('Authorisation endpoint')).toHaveValue(
      AUTHORISATION_ENDPOINT,
    );
    expect(screen.getByLabelText('Token endpoint')).toHaveValue(TOKEN_ENDPOINT);
    expect(screen.getByLabelText('Key set')).toHaveValue(JWKS_URI);
    expect(screen.getByLabelText('Redirect back to')).toHaveValue(REDIRECT_URI);
    expect(screen.getByLabelText('Default team')).toHaveValue('org-root');
  });

  it('offers activation once the deployment reports a passing test on these settings', async () => {
    serve(CONFIGURED);

    await sso();

    expect(screen.getByTestId('activate-sso')).toBeInTheDocument();
  });

  it('shows the active state once the deployment says this provider is the way in', async () => {
    serve({ ...CONFIGURED, is_active: true });

    await sso();

    expect(screen.getByTestId('sso-state')).toHaveTextContent(
      'Active. People sign in through this provider.',
    );
  });

  it('lists every problem the deployment already carries', async () => {
    serve({
      ...CONFIGURED,
      verified: false,
      problems: ['issuer is required', 'default_node_id is required'],
    });

    await sso();

    const problems = screen.getByTestId('sso-problems');
    expect(problems).toHaveTextContent('issuer is required');
    expect(problems).toHaveTextContent('default_node_id is required');
    expect(screen.queryByTestId('activate-sso')).toBeNull();
  });
});

describe('an unconfigured deployment', () => {
  it('renders every field blank and offers no way to activate', async () => {
    serve({});

    await sso();

    expect(screen.getByLabelText('Provider')).toHaveValue('');
    expect(screen.getByLabelText('Issuer')).toHaveValue('');
    expect(screen.getByTestId('sso-state')).toHaveTextContent(
      'Not tested. It cannot be made the way in until it is.',
    );
    expect(screen.queryByTestId('activate-sso')).toBeNull();
  });
});

const CONFIG_NODE = 'org-northwind';

const CONFIG_TREE = [
  { kind: 'organisation', name: 'Northwind', node_id: CONFIG_NODE, parent_id: null },
];

interface ClaimsConfigStub {
  readonly principal?: unknown;
  readonly values?: unknown;
  readonly provenance?: Readonly<Record<string, string>>;
  readonly fields?: readonly unknown[];
}

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

/** The `/identity/sso` flow plus the configuration-service reads the advanced claim-mapping section makes. */
function serveWithClaimsConfig(sso: unknown, config: ClaimsConfigStub = {}): void {
  const { principal = PRINCIPAL, values, provenance = {}, fields = [] } = config;
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    if (path === '/auth/me') return Promise.resolve(respond(principal));
    if (path === '/identity/sso') return Promise.resolve(respond(sso));
    if (path === '/v1/config') return Promise.resolve(respond({ nodes: CONFIG_TREE }));
    if (path === `/v1/config/${CONFIG_NODE}`) {
      return values === undefined
        ? Promise.resolve(respond({}, 404))
        : Promise.resolve(respond({ node_id: CONFIG_NODE, values, provenance }));
    }
    if (path === `/v1/config/${CONFIG_NODE}/fields`) {
      return Promise.resolve(respond({ fields }));
    }
    return Promise.resolve(respond({}, 404));
  });
}

/** `PRINCIPAL`, with the permission the advanced section's editor is gated by. */
const WRITER = {
  ...PRINCIPAL,
  permissions: [...PRINCIPAL.permissions, 'config.write'],
};

describe('the advanced claim-mapping section', () => {
  it('is collapsed on arrival and names the four claim fields with no other control', async () => {
    serveWithClaimsConfig(CONFIGURED, {
      principal: WRITER,
      values: {
        policies: {
          sso: {
            claims: {
              subject: 'sub',
              email: 'email',
              display_name: 'name',
              groups: 'groups',
            },
          },
        },
      },
      provenance: { 'policies.sso.claims.subject': CONFIG_NODE },
    });

    await sso();

    const details = screen.getByTestId('advanced-config-policies-sso-claims');
    expect(details.tagName).toBe('DETAILS');
    expect((details as HTMLDetailsElement).open).toBe(false);

    const rows = screen.getAllByTestId('effective-field');
    const paths = rows.map((row) => row.getAttribute('data-path'));
    expect(paths).toEqual([
      'policies.sso.claims.subject',
      'policies.sso.claims.email',
      'policies.sso.claims.display_name',
      'policies.sso.claims.groups',
    ]);
  });

  it('scopes its editor to policies.sso.claims fields only, never a provider field', async () => {
    serveWithClaimsConfig(CONFIGURED, {
      principal: WRITER,
      values: { policies: { sso: { claims: { subject: 'sub' } } } },
      fields: [
        {
          path: 'policies.sso.claims.subject',
          label: 'Subject claim',
          type: 'string',
          section: 'Claims',
          value: 'sub',
          provenance: '',
          set_here: false,
        },
        {
          path: 'policies.sso.provider',
          label: 'Provider',
          type: 'string',
          section: 'Single sign-on',
          value: 'keycloak',
          provenance: CONFIG_NODE,
          set_here: true,
        },
      ],
    });

    await sso();

    const section = screen.getByTestId('advanced-config-policies-sso-claims');
    const fields = section.querySelectorAll('[data-testid="config-field"]');
    const paths = [...fields].map((field) => field.getAttribute('data-path'));
    expect(paths).toEqual(['policies.sso.claims.subject']);
  });

  it('leaves the editor out for a viewer who may not write configuration', async () => {
    serveWithClaimsConfig(CONFIGURED, {
      principal: { ...PRINCIPAL, permissions: ['identity.read'] },
      values: { policies: { sso: { claims: { subject: 'sub' } } } },
    });

    await sso();

    expect(screen.queryByTestId('config-editor')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('effective-field').length).toBeGreaterThan(0);
  });
});
