import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The approval courier: one operation, and everything it refuses to do.
 *
 * It forwards a decision and returns what the deployment said, verbatim and
 * with its own status. The claims worth holding are the refusals — a request
 * with no session, a body naming an operation this courier does not carry,
 * and a target it cannot address all have to stop here rather than reach the
 * gateway, because a courier that forwards anything is a courier that has
 * stopped being one.
 *
 * The credential lives in an HTTP-only cookie the browser cannot read, so the
 * one thing asserted about every forwarded request is that it carries the
 * session's own bearer and that the secret never appears in what comes back.
 */

const CONSOLE_ORIGIN = ['http:', '//localhost:8423'].join('');
const API = ['http:', '//127.0.0.1:8424'].join('');
const SESSION = 'tok_session';

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
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/approval`, {
    method: 'POST',
    ...(body === null ? {} : { body: JSON.stringify(body) }),
    headers: { 'content-type': 'application/json' },
  });
  if (session) made.cookies.set(SESSION_COOKIE, SESSION);
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/approval/route');
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

it('forwards a decision to the approval it names, carrying the session', async () => {
  vi.stubGlobal('fetch', answering(200, { state: 'approved' }));

  const answer = await post({
    operation: 'decide',
    target: 'apr-1',
    payload: { verdict: 'approve', reason: '' },
  });

  expect(answer.status).toBe(200);
  expect(sent[0]?.url).toBe(`${API}/v1/approvals/apr-1/decision`);
  expect(sent[0]?.init.method).toBe('POST');
  const headers = new Headers(sent[0]?.init.headers);
  expect(headers.get('authorization')).toBe(`Bearer ${SESSION}`);
  const body = sent[0]?.init.body;
  expect(JSON.parse(typeof body === 'string' ? body : '{}')).toEqual({
    verdict: 'approve',
    reason: '',
  });
});

it('escapes the identifier rather than pasting it into the address', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  await post({ operation: 'decide', target: 'apr/../../secrets', payload: {} });

  expect(sent[0]?.url).toBe(`${API}/v1/approvals/apr%2F..%2F..%2Fsecrets/decision`);
});

it('returns the deployment refusal in its own words and status', async () => {
  vi.stubGlobal(
    'fetch',
    answering(400, { error: { message: 'no rollback plan is recorded' } }),
  );

  const answer = await post({
    operation: 'decide',
    target: 'apr-1',
    payload: { verdict: 'approve' },
  });

  expect(answer.status).toBe(400);
  expect(await answer.json()).toEqual({
    error: { message: 'no rollback plan is recorded' },
  });
});

it('refuses a request with no session before reaching the deployment', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const answer = await post(
    { operation: 'decide', target: 'apr-1', payload: {} },
    false,
  );

  expect(answer.status).toBe(401);
  expect(sent).toEqual([]);
});

it('refuses an operation it does not carry, and a decision with no target', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const unknown = await post({ operation: 'execute', target: 'apr-1', payload: {} });
  expect(unknown.status).toBe(400);

  const targetless = await post({ operation: 'decide', target: '', payload: {} });
  expect(targetless.status).toBe(400);

  // Neither reached the gateway: this courier refuses rather than relays.
  expect(sent).toEqual([]);
});

it('refuses a body that is not readable at all', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const answer = await post(null);

  expect(answer.status).toBe(400);
  expect(sent).toEqual([]);
});

it('says the deployment is unreachable rather than inventing an answer', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
  );

  const answer = await post({ operation: 'decide', target: 'apr-1', payload: {} });

  expect(answer.status).toBe(502);
  expect(await answer.json()).toEqual({ reachable: false });
});

it('survives an answer whose body is not JSON', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response('<html>gateway</html>', { status: 502 }))),
  );

  const answer = await post({ operation: 'decide', target: 'apr-1', payload: {} });

  expect(answer.status).toBe(502);
  expect(await answer.json()).toEqual({});
});
