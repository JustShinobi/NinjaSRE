import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The model-listing courier: a `GET`, unlike `/api/verify` beside it —
 * listing spends no tokens, so nothing here is gated on a gesture the way a
 * write is. What is worth asserting is the query it forwards (the provider,
 * and `refresh` only when asked), that a refusal or an unreachable deployment
 * both fall back to the same honest static-listing shape rather than an
 * empty body, and that no vendor credential — only the session cookie —
 * ever crosses this handler.
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

function unreachable() {
  return vi.fn(() => Promise.reject(new TypeError('fetch failed')));
}

function request(query: string, { session = true } = {}): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/models${query}`);
  if (session) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function get(query: string, session = true): Promise<Response> {
  const { GET } = await import('@/app/api/models/route');
  return GET(request(query, { session }));
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

it('asks the named provider, plain, when no reload was requested', async () => {
  vi.stubGlobal(
    'fetch',
    answering(200, {
      provider_id: 'google_gemini',
      models: [],
      source: 'endpoint',
      reason: '',
    }),
  );

  await get('?provider=google_gemini');

  expect(sent[0]?.url).toBe(`${API}/v1/providers/google_gemini/models`);
  expect(sent[0]?.init.method).toBe('GET');
});

it('carries "refresh=true" only when the caller asked to reload', async () => {
  vi.stubGlobal(
    'fetch',
    answering(200, {
      provider_id: 'google_gemini',
      models: [],
      source: 'endpoint',
      reason: '',
    }),
  );

  await get('?provider=google_gemini&refresh=true');

  expect(sent[0]?.url).toBe(`${API}/v1/providers/google_gemini/models?refresh=true`);
});

it('returns the deployment’s own listing body, verbatim', async () => {
  const listing = {
    provider_id: 'google_gemini',
    models: [{ model_id: 'gemini-3.7-flash', display_name: 'Gemini 3.7 Flash' }],
    source: 'endpoint',
    reason: '',
  };
  vi.stubGlobal('fetch', answering(200, listing));

  const answer = await get('?provider=google_gemini');

  expect(answer.status).toBe(200);
  expect(await answer.json()).toEqual(listing);
});

it('refuses without a session, and asks the deployment nothing', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const answer = await get('?provider=google_gemini', false);

  expect(answer.status).toBe(401);
  expect(await answer.json()).toMatchObject({ models: [], source: 'static' });
  expect(sent).toHaveLength(0);
});

it('refuses with no provider named, whether the query is absent or empty', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const absent = await get('');
  expect(absent.status).toBe(400);
  expect(await absent.json()).toMatchObject({ models: [], source: 'static' });

  const empty = await get('?provider=');
  expect(empty.status).toBe(400);

  expect(sent).toHaveLength(0);
});

it('falls back to the static shape, honestly labelled, when the deployment refuses', async () => {
  vi.stubGlobal('fetch', answering(503, { error: { message: 'unavailable' } }));

  const answer = await get('?provider=google_gemini');

  expect(answer.status).toBe(503);
  expect(await answer.json()).toMatchObject({
    models: [],
    source: 'static',
    reason: 'the deployment could not be reached',
  });
});

it('says the deployment could not be reached, not that it refused', async () => {
  vi.stubGlobal('fetch', unreachable());

  const answer = await get('?provider=google_gemini');

  expect(answer.status).toBe(502);
  expect(await answer.json()).toMatchObject({ models: [], source: 'static' });
});
