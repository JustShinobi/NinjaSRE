import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { NotBuiltSettingsPage } from '@/surfaces/screens/settings-not-built';

/**
 * The honest stand-in for a Settings page nothing has built yet — and, since
 * the setup wizard hands its last step over to Alert intake (one of the five
 * still unbuilt), the one place that handover has to offer a way back while
 * there is still a wizard to come back to.
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
  permissions: ['config.read'],
  team_node_id: 'org-northwind',
  impersonating: false,
  impersonated_by: null,
};

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function serve(complete: boolean): void {
  const bodies: Record<string, unknown> = {
    '/auth/me': PRINCIPAL,
    '/v1/setup/checklist': {
      complete,
      provider: complete ? 'verified' : 'absent',
      integrations: [],
      steps: [{ name: 'model-provider', state: complete ? 'done' : 'ready' }],
    },
  };
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body = bodies[path];
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

async function page(id: string, query: Record<string, string> = {}): Promise<void> {
  render(await NotBuiltSettingsPage(id, await surfaceContext(query)));
}

describe('a Settings page nothing has built yet', () => {
  it('names the page and offers a way back to Settings', async () => {
    serve(false);
    await page('settings-alert-intake');

    expect(screen.getByTestId('page-header')).toHaveAttribute(
      'data-area',
      'settings-alert-intake',
    );
    expect(screen.getByTestId('way-back')).toHaveAttribute('href', '/settings');
  });

  it('offers the way back to the wizard when it sent the operator here and setup is not finished', async () => {
    serve(false);
    await page('settings-alert-intake', { return: 'setup' });

    expect(screen.getByTestId('setup-return-link')).toHaveAttribute(
      'href',
      '/first-run?step=provider',
    );
  });

  it('says nothing about the wizard on an ordinary visit', async () => {
    serve(false);
    await page('settings-alert-intake');

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });

  it('says nothing once setup is already finished, even though the address asked', async () => {
    serve(true);
    await page('settings-alert-intake', { return: 'setup' });

    expect(screen.queryByTestId('setup-return-banner')).toBeNull();
  });
});
