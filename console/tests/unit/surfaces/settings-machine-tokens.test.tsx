import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { CLOCK_ENV, surfaceContext } from '@/surfaces/context';
import { MachineTokensScreen } from '@/surfaces/settings/machine-tokens';

/**
 * Machine tokens, as a server page: does `/identity/tokens`'s own answer
 * reach `MachineTokenGroups` correctly mapped (`machineToken()`), with the
 * console's own browser session filtered out (`isConsoleSession`) and the
 * panel itself absent for a viewer without `token.manage` — properties that
 * belong to this wrapper, not to `machine-token-groups.test.tsx`, which
 * already covers the panel's own behaviour given plain props.
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

function principal(permissions: readonly string[]): unknown {
  return {
    principal_id: 'user-operator',
    display_name: 'Avery Lockhart',
    kind: 'person',
    roles: ['owner'],
    permissions,
    team_node_id: 'org-northwind',
    impersonating: false,
    impersonated_by: null,
  };
}

const TOKENS = {
  tokens: [
    {
      token_id: 'tok-session',
      user_id: 'user-operator',
      name: 'Console sign-in',
      description: null,
      team_node_id: 'org-northwind',
      scopes: [],
      created_at: '2026-08-10T00:00:00Z',
      expires_at: '2026-08-20T00:00:00Z',
      last_used_at: '2026-08-13T00:00:00Z',
      revoked: false,
    },
    {
      token_id: 'tok-mail',
      user_id: 'svc-mail',
      name: 'mail-relay',
      description: 'SMTP relay credential',
      team_node_id: null,
      scopes: ['token.manage'],
      created_at: '2026-08-01T00:00:00Z',
      expires_at: '2026-09-01T00:00:00Z',
      last_used_at: '2026-08-12T00:00:00Z',
      revoked: false,
    },
  ],
};

function serve(permissions: readonly string[]): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const address = new URL(String(input), BASE);
    const byPath: Record<string, unknown> = {
      '/auth/me': principal(permissions),
      '/identity/tokens': TOKENS,
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
  vi.stubEnv(CLOCK_ENV, '2026-08-13T12:00:00Z');
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

async function tokens(permissions: readonly string[]): Promise<void> {
  serve(permissions);
  render(await MachineTokensScreen(await surfaceContext({})));
}

describe('a viewer who may manage tokens', () => {
  it('groups the machine token by its own purpose, not the console’s own browser session', async () => {
    await tokens(['token.manage']);

    const groups = screen.getAllByTestId('token-group');
    expect(groups).toHaveLength(1);
    const [group] = groups;
    if (group === undefined) {
      throw new Error('expected one token group');
    }
    expect(within(group).getByText('mail-relay')).toBeInTheDocument();
    expect(screen.queryByText('Console sign-in')).toBeNull();
    // Only the one, real machine token — the console session never reaches
    // even the collapsed detail list underneath the group.
    expect(screen.getAllByTestId('token')).toHaveLength(1);
  });

  it('carries the token’s own description and scopes onto its group', async () => {
    await tokens(['token.manage']);

    const [group] = screen.getAllByTestId('token-group');
    if (group === undefined) {
      throw new Error('expected one token group');
    }
    expect(within(group).getByText('SMTP relay credential')).toBeInTheDocument();
    expect(within(group).getByText('Token Manage')).toBeInTheDocument();
  });

  it('offers the issue form', async () => {
    await tokens(['token.manage']);

    expect(screen.getByTestId('issue-token')).toBeInTheDocument();
  });
});

describe('a viewer who may not manage tokens', () => {
  it('renders no token panel at all — absent, not disabled', async () => {
    await tokens(['identity.read']);

    expect(screen.queryByTestId('machine-token-groups')).toBeNull();
    expect(screen.queryByTestId('token')).toBeNull();
    expect(screen.queryByTestId('issue-token')).toBeNull();
  });
});

describe('a viewer who arrives already scoped, by address', () => {
  const DELIVERY_SCOPE = ['webhook', 'deliver'].join('.');
  const SCOPED_TOKENS = {
    tokens: [
      {
        token_id: 'tok-alert',
        user_id: 'svc-alertmanager',
        name: 'Alert delivery',
        description: '',
        team_node_id: null,
        scopes: [DELIVERY_SCOPE],
        created_at: '2026-08-01T00:00:00Z',
        expires_at: null,
        last_used_at: '2026-08-13T00:00:00Z',
        revoked: false,
      },
      {
        token_id: 'tok-mail',
        user_id: 'svc-mail',
        name: 'mail-relay',
        description: 'SMTP relay credential',
        team_node_id: null,
        scopes: ['token.manage'],
        created_at: '2026-08-01T00:00:00Z',
        expires_at: null,
        last_used_at: '2026-08-12T00:00:00Z',
        revoked: false,
      },
    ],
  };

  function serveScoped(): void {
    vi.stubGlobal('fetch', (input: unknown) => {
      const address = new URL(String(input), BASE);
      const byPath: Record<string, unknown> = {
        '/auth/me': principal(['token.manage']),
        '/identity/tokens': SCOPED_TOKENS,
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

  it('shows only the tokens carrying the scope named in the address — the destination Alert intake’s own "Rotate" promises', async () => {
    serveScoped();
    render(await MachineTokensScreen(await surfaceContext({ scope: DELIVERY_SCOPE })));

    const groups = screen.getAllByTestId('token-group');
    expect(groups).toHaveLength(1);
    const [group] = groups;
    if (group === undefined) {
      throw new Error('expected one token group');
    }
    // `within` this one group, not the page: the issue form below also
    // offers "Alert delivery" as a purpose template button, and this
    // assertion is about the token list, not about that suggestion.
    expect(within(group).getByText('Alert delivery')).toBeInTheDocument();
    expect(screen.queryByText('mail-relay')).toBeNull();
  });

  it('names the scope it filtered to, and offers a way back to the full list', async () => {
    serveScoped();
    render(await MachineTokensScreen(await surfaceContext({ scope: DELIVERY_SCOPE })));

    expect(screen.getByTestId('machine-tokens-filter')).toHaveTextContent(
      'Webhook Deliver',
    );
    expect(screen.getByTestId('machine-tokens-filter-clear')).toHaveAttribute(
      'href',
      '/settings/machine-tokens',
    );
  });

  it('shows every token, unfiltered, and names no filter, when the address names none', async () => {
    serveScoped();
    render(await MachineTokensScreen(await surfaceContext({})));

    expect(screen.getAllByTestId('token-group')).toHaveLength(2);
    expect(screen.queryByTestId('machine-tokens-filter')).toBeNull();
  });
});
