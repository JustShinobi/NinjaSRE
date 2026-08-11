import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The proposal courier: four operations, one handler, and no path it invents.
 *
 * What is worth asserting is which address each operation reaches — three of
 * them are the *deployment's own* preview mechanisms rather than anything this
 * console computes — that the deployment's refusal crosses back verbatim, and
 * that an operation the table does not name cannot be reached at all. That last
 * one is the property that keeps one handler for four calls from being a way to
 * address an arbitrary path on the deployment.
 */

const CONSOLE_ORIGIN = ['http:', '//localhost:8423'].join('');
const API = ['http:', '//127.0.0.1:8424'].join('');

interface Sent {
  readonly url: string;
  readonly init: RequestInit;
}

let sent: Sent[] = [];

function answering(status: number, body: unknown) {
  return vi.fn((url: unknown, init?: RequestInit) => {
    sent.push({ url: String(url), init: init ?? {} });
    return Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
}

function request(body: unknown, { session = true } = {}): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/proposal`, {
    method: 'POST',
    ...(body === null ? {} : { body: JSON.stringify(body) }),
    headers: { 'content-type': 'application/json' },
  });
  if (session) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/proposal/route');
  return POST(request(body, { session }));
}

beforeEach(() => {
  sent = [];
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', API);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

it('sends each named operation to the mechanism that already answers it', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  await post({
    operation: 'decide',
    target: 'prop-1',
    payload: { verdict: 'approve' },
  });
  expect(sent[0]?.url).toBe(`${API}/v1/proposals/prop-1/decision`);

  sent = [];
  await post({ operation: 'preview', target: 'team-a', payload: { patch: {} } });
  expect(sent[0]?.url).toBe(`${API}/v1/config/team-a/preview`);

  sent = [];
  await post({
    operation: 'context-preview',
    target: 'team-a',
    payload: { sections: {} },
  });
  expect(sent[0]?.url).toBe(`${API}/v1/config/team-a/operating-context/preview`);

  sent = [];
  await post({ operation: 'dry-run', target: 'corpus-fill' });
  expect(sent[0]?.url).toBe(`${API}/v1/detectors/corpus-fill/dry-run`);
});

it('refuses an operation the table does not name', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const answer = await post({ operation: 'delete', target: 'prop-1' });

  expect(answer.status).toBe(400);
  expect(sent).toHaveLength(0);
});

it('refuses a call that names nothing to act on', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ operation: 'decide', target: '' })).status).toBe(400);
  expect((await post(null)).status).toBe(400);
  expect(sent).toHaveLength(0);
});

it('refuses without a session, before it reaches the deployment', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const answer = await post({ operation: 'decide', target: 'prop-1' }, false);

  expect(answer.status).toBe(401);
  expect(sent).toHaveLength(0);
});

it('carries the deployment’s refusal back in its own words', async () => {
  vi.stubGlobal('fetch', answering(400, { detail: 'a rejection carries a reason' }));

  const answer = await post({
    operation: 'decide',
    target: 'prop-1',
    payload: { verdict: 'reject', reason: '' },
  });

  expect(answer.status).toBe(400);
  expect(await answer.json()).toMatchObject({ detail: 'a rejection carries a reason' });
});

it('says the deployment could not be reached rather than inventing an answer', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
  );

  const answer = await post({ operation: 'dry-run', target: 'corpus-fill' });

  expect(answer.status).toBe(502);
  expect(await answer.json()).toMatchObject({ reachable: false });
});
