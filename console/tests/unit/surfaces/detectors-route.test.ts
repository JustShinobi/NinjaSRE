import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The detector courier: three operations, one handler, and no secret in any
 * of them.
 *
 * What is worth asserting is which address each operation reaches, that a
 * dry run fires nothing, that the deployment's own refusal crosses back
 * verbatim, and that an operation the table does not name cannot be reached
 * through it at all — the property that keeps one handler for three writes
 * from being a way to address an arbitrary path on the deployment.
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

function request(body: unknown, { session = true } = {}): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/detectors`, {
    method: 'POST',
    ...(body === null ? {} : { body: JSON.stringify(body) }),
    headers: { 'content-type': 'application/json' },
  });
  if (session) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/detectors/route');
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

it('sends each named operation to its own address', async () => {
  vi.stubGlobal('fetch', answering(200, { detector_id: 'd1', would_fire: false }));

  await post({ detectorId: 'd1', operation: 'dry-run' });
  expect(sent[0]?.url).toBe(`${API}/v1/detectors/d1/dry-run`);
  expect(sent[0]?.init.method).toBe('POST');

  sent = [];
  await post({ detectorId: 'd1', operation: 'enable' });
  expect(sent[0]?.url).toBe(`${API}/v1/detectors/d1/enable`);

  sent = [];
  await post({ detectorId: 'd1', operation: 'disable' });
  expect(sent[0]?.url).toBe(`${API}/v1/detectors/d1/disable`);
});

it('carries the deployment’s answer verbatim under its own key', async () => {
  vi.stubGlobal(
    'fetch',
    answering(200, {
      detector_id: 'd1',
      would_fire: true,
      fired: false,
      observations: [],
    }),
  );

  const answer = await post({ detectorId: 'd1', operation: 'dry-run' });

  expect(await answer.json()).toMatchObject({
    ok: true,
    answer: { would_fire: true, fired: false },
  });
});

it('carries the deployment’s refusal, nested the way the gateway shapes it', async () => {
  vi.stubGlobal(
    'fetch',
    answering(404, {
      error: { type: 'not_found', message: "no detector 'd1' is declared" },
    }),
  );

  const answer = await post({ detectorId: 'd1', operation: 'enable' });

  expect(answer.status).toBe(404);
  expect(await answer.json()).toMatchObject({
    ok: false,
    reason: "no detector 'd1' is declared",
  });
});

it('will not forward an operation the table does not name', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ detectorId: 'd1', operation: 'delete' })).status).toBe(400);
  expect(sent).toHaveLength(0);
});

it('will not forward an operation with no detector to apply it to', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ operation: 'enable' })).status).toBe(400);
  expect(sent).toHaveLength(0);
});

it('refuses without a session, and asks the deployment nothing', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ detectorId: 'd1', operation: 'enable' }, false)).status).toBe(
    401,
  );
  expect(sent).toHaveLength(0);
});

it('says the deployment could not be reached, not that it refused', async () => {
  vi.stubGlobal('fetch', unreachable());

  const answer = await post({ detectorId: 'd1', operation: 'enable' });

  expect(answer.status).toBe(502);
  expect(await answer.json()).toEqual({ ok: false, reachable: false });
});
