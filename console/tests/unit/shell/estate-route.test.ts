import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The estate courier: three questions, one handler, and no secret in any of them.
 *
 * It exists for the reason every courier here does — the session credential is
 * an HTTP-only, `SameSite=Strict` cookie the browser will not send to another
 * host — and what is worth asserting is which address each action reaches and
 * what it puts in the body. A handler that sent a preview to the confirm route
 * would sweep a cluster somebody was still deciding about, which is precisely
 * the mistake the preview exists to prevent.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';
const API = 'http://127.0.0.1:8424';

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

function bodyOf(request: Sent | undefined): unknown {
  return typeof request?.init.body === 'string' ? JSON.parse(request.init.body) : null;
}

function request(body: unknown, withSession = true): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/estate`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/estate/route');
  return POST(request(body, session));
}

beforeEach(() => {
  sent = [];
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', API);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it('asks the vendor what the token may do, and carries the session credential', async () => {
  vi.stubGlobal('fetch', answering(200, { integration: 'proxmox', report: { a: 1 } }));

  const answer = await post({ action: 'report', integration: 'proxmox' });

  expect(answer.status).toBe(200);
  expect(sent[0]?.url).toBe(`${API}/v1/integrations/proxmox/verify/report`);
  expect(sent[0]?.init.method).toBe('POST');
  expect(new Headers(sent[0]?.init.headers).get('authorization')).toBe(
    'Bearer tok_session',
  );
  await expect(answer.json()).resolves.toMatchObject({
    ok: true,
    result: { report: { a: 1 } },
  });
});

it('sends a preview to the preview route, with the declared networks', async () => {
  vi.stubGlobal('fetch', answering(200, { guests: 57 }));

  await post({
    action: 'preview',
    integration: 'proxmox',
    zones: { '10.20.20.0/24': 'infra', '10.20.30.0/24': 42 },
  });

  expect(sent[0]?.url).toBe(`${API}/v1/estate/discovery/preview`);
  expect(bodyOf(sent[0])).toEqual({
    integration: 'proxmox',
    // A zone name that is not a string is a shape somebody is probing with,
    // dropped rather than coerced.
    zones: { '10.20.20.0/24': 'infra' },
  });
});

it('sends a confirmation to the sources route, and never to the preview', async () => {
  vi.stubGlobal('fetch', answering(200, { job_id: 'estate.discovery:proxmox' }));

  await post({ action: 'confirm', integration: 'proxmox' });

  expect(sent[0]?.url).toBe(`${API}/v1/estate/discovery/sources`);
  expect(bodyOf(sent[0])).toEqual({ integration: 'proxmox' });
});

it('forwards the deployment’s own refusal rather than a sentence of its own', async () => {
  vi.stubGlobal(
    'fetch',
    answering(404, {
      error: { type: 'not_found', message: "No discovery source for 'proxmox'" },
    }),
  );

  const answer = await post({ action: 'preview', integration: 'proxmox' });

  expect(answer.status).toBe(404);
  await expect(answer.json()).resolves.toMatchObject({
    ok: false,
    reachable: true,
    reason: "No discovery source for 'proxmox'",
    result: {},
  });
});

it('says the deployment did not answer rather than that it refused', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.reject(new Error('connection refused'))),
  );

  const answer = await post({ action: 'report', integration: 'proxmox' });

  expect(answer.status).toBe(502);
  await expect(answer.json()).resolves.toEqual({ ok: false, reachable: false });
});

it('refuses without a session, and asks nothing of the deployment', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const answer = await post({ action: 'report', integration: 'proxmox' }, false);

  expect(answer.status).toBe(401);
  expect(sent).toEqual([]);
});

it('refuses an action it does not serve, and an integration nobody named', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  const unknown = await post({ action: 'destroy', integration: 'proxmox' });
  const nameless = await post({ action: 'preview', integration: '' });

  expect(unknown.status).toBe(400);
  expect(nameless.status).toBe(400);
  expect(sent).toEqual([]);
});
