import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { CLOCK_ENV, surfaceContext } from '@/surfaces/context';
import { MembersScreen } from '@/surfaces/settings/members';

/**
 * Members & roles: people and service accounts, their grants, and their
 * active sessions — the desmembramento's simplest page, because it is the
 * one part of the old Administration screen that already worked. What
 * changes here is what is *not* on the page any more: no machine tokens, no
 * SSO form crowding the bottom of it.
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

const PEOPLE = {
  users: [
    {
      user_id: 'user-operator',
      email: 'avery@x.test',
      display_name: 'Avery Lockhart',
      kind: 'user',
      is_active: true,
    },
    {
      user_id: 'svc-scheduler',
      email: '',
      display_name: 'Scheduler',
      kind: 'service_account',
      is_active: true,
    },
  ],
};

const GRANTS = {
  grants: [
    {
      grant_id: 'grant-1',
      principal_id: 'user-operator',
      role: 'owner',
      node_id: null,
    },
  ],
};

const ROLES = {
  roles: [
    { name: 'viewer', permissions: ['investigation.read'] },
    { name: 'owner', permissions: ['org.delete', 'owner.assign'] },
  ],
};

const TOKENS = {
  tokens: [
    {
      token_id: 'tok-session',
      user_id: 'user-operator',
      name: 'Console sign-in',
      description: null,
      team_node_id: 'org-northwind',
      scopes: [],
      created_at: '2026-08-01T00:00:00Z',
      expires_at: '2026-08-14T00:00:00Z',
      last_used_at: '2026-08-13T00:00:00Z',
      revoked: false,
    },
    {
      token_id: 'tok-machine',
      user_id: 'svc-scheduler',
      name: 'bootstrap',
      description: 'x',
      team_node_id: null,
      scopes: ['token.manage'],
      created_at: '2026-08-01T00:00:00Z',
      expires_at: '2026-08-02T00:00:00Z',
      last_used_at: null,
      revoked: false,
    },
  ],
};

function serve(): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const address = new URL(String(input), BASE);
    const byPath: Record<string, unknown> = {
      '/auth/me': PRINCIPAL,
      '/identity/principals': PEOPLE,
      '/identity/grants': GRANTS,
      '/identity/roles': ROLES,
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
  serve();
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

async function members(): Promise<void> {
  render(await MembersScreen(await surfaceContext({})));
}

describe('who exists and what they hold', () => {
  it('lists people and service accounts with a kind chip each', async () => {
    await members();

    const principals = screen.getAllByTestId('principal');
    expect(principals).toHaveLength(2);
    const [first, second] = principals;
    if (first === undefined || second === undefined) {
      throw new Error('expected two principal rows');
    }
    expect(within(first).getByText('Avery Lockhart')).toBeInTheDocument();
    expect(within(first).getByText('avery@x.test')).toBeInTheDocument();
    expect(within(second).getByText('Scheduler')).toBeInTheDocument();
    // A service account is created with no email by design; naming that is
    // the honest second line, not the generic "not recorded" a blank field
    // elsewhere would read as something this deployment forgot.
    expect(
      within(second).getByText('A service account created at deploy, with no email.'),
    ).toBeInTheDocument();
  });

  it('shows the grant panel with legible role permissions, not raw ids alone', async () => {
    await members();

    const panel = screen.getByTestId('grant-panel');
    expect(panel).toBeInTheDocument();
    // The selected role's own permissions, read live from /identity/roles
    // rather than a copy this page keeps — `viewer` is first in the
    // catalogue and therefore the role select's own default.
    expect(within(panel).getByText(/investigation\.read/)).toBeInTheDocument();
  });

  it('shows active sessions', async () => {
    await members();

    expect(screen.getByTestId('session-panel')).toBeInTheDocument();
  });

  it('falls back to the raw id for a blank-email principal that is not a service account', async () => {
    vi.stubGlobal('fetch', (input: unknown) => {
      const address = new URL(String(input), BASE);
      const byPath: Record<string, unknown> = {
        '/auth/me': PRINCIPAL,
        '/identity/principals': {
          users: [
            {
              user_id: 'user-mystery',
              email: '',
              display_name: 'Mystery',
              kind: 'user',
              is_active: true,
            },
          ],
        },
        '/identity/grants': { grants: [] },
        '/identity/roles': ROLES,
        '/identity/tokens': { tokens: [] },
      };
      const body = byPath[address.pathname];
      return Promise.resolve(
        new Response(JSON.stringify(body ?? {}), {
          status: body === undefined ? 404 : 200,
          headers: { 'content-type': 'application/json' },
        }),
      );
    });

    await members();

    expect(screen.getByText('user-mystery')).toBeInTheDocument();
  });
});

describe('what this page no longer shows', () => {
  it('carries no machine-token issuance form', async () => {
    await members();

    expect(screen.queryByTestId('token-panel')).toBeNull();
    expect(screen.queryByTestId('issue-token')).toBeNull();
  });

  it('carries no SSO configuration form', async () => {
    await members();

    expect(screen.queryByTestId('sso-form')).toBeNull();
    expect(screen.queryByTestId('sso-setup-flow')).toBeNull();
  });
});
