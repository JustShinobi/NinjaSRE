import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

import { AREA_SCREENS } from '../support/screens';
import { principalHolding } from '../support/dataset';

/**
 * A masked identifier, and where the decision to restore it is made.
 *
 * It is made on the server, and this file's job is to show that the console has
 * no opinion at all: the same screen, the same code, two principals, and the
 * only difference is what the deployment sent. There is no branch here that
 * could restore something, which is the strongest form of the claim — a console
 * that decided masking would be a second implementation of a security control,
 * and the second implementation is the one that is wrong.
 */

vi.mock('next/headers', () => ({
  cookies: () =>
    Promise.resolve({
      get: (name: string) =>
        name === SESSION_COOKIE ? { value: 'a-token' } : undefined,
    }),
  headers: () => Promise.resolve({ get: () => null }),
}));

const MASKED = '‹redacted:host›';
const RESTORED = 'pve02.lan.internal';

/** A base for parsing a path-only address. Never contacted. */
const BASE = ['http:', '//fixtures.invalid'].join('');

/** Serve one run whose summary carries `identifier`, however the server spelled it. */
function serveSummary(identifier: string, permissions: readonly string[]): void {
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body =
      path === '/auth/me'
        ? principalHolding(permissions)
        : path === '/v1/runs'
          ? {
              runs: [
                {
                  run_id: 'run-0001',
                  status: 'succeeded',
                  trigger: 'alert',
                  summary: `The datastore on ${identifier} is nearly full.`,
                  started_at: '2026-08-07T11:00:00+00:00',
                  finished_at: '2026-08-07T11:05:00+00:00',
                },
              ],
            }
          : {};
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

async function renderRuns(): Promise<void> {
  const runs = AREA_SCREENS.find((screen_) => screen_.id === 'runs');
  if (runs === undefined) throw new Error('there is no run list');
  render(await runs.render({ searchParams: Promise.resolve({}) }));
}

beforeEach(() => {
  vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('a masked identifier', () => {
  it('stays masked for a viewer the server masked it for', async () => {
    serveSummary(MASKED, ['investigation.read']);
    await renderRuns();

    expect(screen.getByText(new RegExp(MASKED))).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(RESTORED))).toBeNull();
  });

  it('is restored for a viewer the server restored it for', async () => {
    serveSummary(RESTORED, ['investigation.read', 'credential.read']);
    await renderRuns();

    expect(screen.getByText(new RegExp(RESTORED))).toBeInTheDocument();
  });

  it('is rendered as the server spelled it, with no branch in between', () => {
    function sources(root: string): readonly string[] {
      const found: string[] = [];
      for (const entry of readdirSync(root)) {
        const path = join(root, entry);
        if (statSync(path).isDirectory()) {
          found.push(...sources(path));
        } else if (path.endsWith('.ts') || path.endsWith('.tsx')) {
          found.push(path);
        }
      }
      return found;
    }

    // The structural half. A console that could restore a masked value would
    // have to have a word for doing it; it has none, and that is deliberate.
    // The generated client is excluded: it is the API document's own prose about
    // what the *server* does not reveal, which is the opposite of a code path.
    const guilty = sources(join(process.cwd(), 'src'))
      .filter((path) => !path.endsWith(join('api', 'schema.ts')))
      .filter((path) =>
        /unmask|reveal|deredact|restoreMask/i.test(readFileSync(path, 'utf8')),
      );
    expect(guilty).toEqual([]);
  });
});
