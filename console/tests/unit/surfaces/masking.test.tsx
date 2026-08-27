import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { surfaceContext } from '@/surfaces/context';
import { RunDetailScreen } from '@/surfaces/screens/run-detail';

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
 *
 * Read off the report panel of the run's own detail page, not the runs list's
 * subject column: that column is a run's *name* now, resolved through
 * `run-subject.ts`, and a name is never the raw document — exactly the
 * property this suite is elsewhere held to. The report panel is the one
 * surface that still shows the deployment's text verbatim, which is what
 * this file needs to see the masking decision travel untouched.
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
const RUN = 'run-0001';

/** A base for parsing a path-only address. Never contacted. */
const BASE = ['http:', '//fixtures.invalid'].join('');

/** Serve one run whose report carries `identifier`, however the server spelled it. */
function serveSummary(identifier: string, permissions: readonly string[]): void {
  const sentence = `The datastore on ${identifier} is nearly full.`;
  vi.stubGlobal('fetch', (input: unknown) => {
    const path = new URL(String(input), BASE).pathname;
    const body =
      path === '/auth/me'
        ? principalHolding(permissions)
        : path === `/v1/runs/${RUN}`
          ? {
              run_id: RUN,
              status: 'succeeded',
              trigger: 'alert',
              // Mirrored onto both fields, the way the deployment's own
              // summary_of() does — this file is about what travels through
              // either of them untouched, not about which one a run carries.
              summary: sentence,
              report: sentence,
              started_at: '2026-08-07T11:00:00+00:00',
              finished_at: '2026-08-07T11:05:00+00:00',
            }
          : path === `/v1/runs/${RUN}/replay`
            ? {
                run_id: RUN,
                is_interrupted: false,
                total_cost: 0,
                total_tokens: 0,
                turns: [],
              }
            : path === '/v1/incidents'
              ? { incidents: [] }
              : path === `/v1/investigations/${RUN}/interactions`
                ? { interactions: [] }
                : {};
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

async function renderRunDetail(): Promise<void> {
  render(await RunDetailScreen(await surfaceContext({}), RUN));
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
    await renderRunDetail();

    // Scoped to the rendered report itself, not the whole page: the same
    // text also sits, verbatim, inside the closed disclosure right below it
    // — a second, legitimate copy this assertion is not about.
    const report = within(screen.getByTestId('report'));
    expect(report.getByText(new RegExp(MASKED))).toBeInTheDocument();
    expect(report.queryByText(new RegExp(RESTORED))).toBeNull();
  });

  it('is restored for a viewer the server restored it for', async () => {
    serveSummary(RESTORED, ['investigation.read', 'credential.read']);
    await renderRunDetail();

    const report = within(screen.getByTestId('report'));
    expect(report.getByText(new RegExp(RESTORED))).toBeInTheDocument();
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
