import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

import { bodyFor } from '../../../scripts/fixture-server.mjs';

/**
 * What the frame reads on every full-page render, and what it does not.
 *
 * The shell layout runs on every screen, so a read here is a read the
 * deployment pays for on every render of every page. The investigate drawer's
 * briefing — the incident listing, the estate summary and the organisation
 * tree, three reads to derive a team name and two suggestions — used to be
 * one of them, for a drawer most page views never open. It is fetched by the
 * drawer, when it opens, and this holds the layout to that.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

let asked: string[] = [];

beforeEach(() => {
  asked = [];
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', 'http://127.0.0.1:8424');
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input)).pathname;
    asked.push(path);
    const body: unknown = bodyFor('populated', path);
    return Promise.resolve(
      new Response(JSON.stringify(body ?? {}), {
        status: body === null || body === undefined ? 404 : 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it('reads the viewer and the frame, and nothing the drawer reads for itself', async () => {
  const { default: ShellLayout } = await import('@/app/(shell)/layout');

  await ShellLayout({ children: null });

  expect(asked).toContain('/auth/me');
  expect(asked).toContain('/v1/setup/checklist');
  expect(asked).not.toContain('/v1/incidents');
  expect(asked).not.toContain('/v1/estate/summary');
  expect(asked).not.toContain('/v1/config');
});
