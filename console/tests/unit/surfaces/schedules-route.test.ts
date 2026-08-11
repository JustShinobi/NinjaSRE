import { NextRequest } from 'next/server';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The schedule courier: five operations, one handler, and no secret in any
 * of them.
 *
 * `create` needs no identifier — the job id is in the body — and every other
 * operation is refused without one to act on. What is worth asserting beyond
 * the address each operation reaches is that a cron expression the
 * deployment refuses crosses back exactly as it worded the refusal.
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

function bodyOf(request: Sent | undefined): unknown {
  return typeof request?.init.body === 'string' ? JSON.parse(request.init.body) : null;
}

function request(body: unknown, { session = true } = {}): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/schedules`, {
    method: 'POST',
    ...(body === null ? {} : { body: JSON.stringify(body) }),
    headers: { 'content-type': 'application/json' },
  });
  if (session) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/schedules/route');
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

it('sends each named operation to its own address and method', async () => {
  vi.stubGlobal('fetch', answering(201, { job_id: 'j1' }));

  await post({ operation: 'create', payload: { job_id: 'j1' } });
  expect(sent[0]?.url).toBe(`${API}/v1/schedules`);
  expect(sent[0]?.init.method).toBe('POST');
  expect(bodyOf(sent[0])).toEqual({ job_id: 'j1' });

  sent = [];
  await post({ jobId: 'j1', operation: 'update', payload: { cron: '0 9 * * *' } });
  expect(sent[0]?.url).toBe(`${API}/v1/schedules/j1`);
  expect(sent[0]?.init.method).toBe('PUT');

  sent = [];
  await post({ jobId: 'j1', operation: 'delete' });
  expect(sent[0]?.url).toBe(`${API}/v1/schedules/j1`);
  expect(sent[0]?.init.method).toBe('DELETE');

  sent = [];
  await post({ jobId: 'j1', operation: 'enable' });
  expect(sent[0]?.url).toBe(`${API}/v1/schedules/j1/enable`);
  expect(sent[0]?.init.method).toBe('POST');

  sent = [];
  await post({ jobId: 'j1', operation: 'disable' });
  expect(sent[0]?.url).toBe(`${API}/v1/schedules/j1/disable`);
});

it('encodes the job id into the path', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  await post({ jobId: 'has a space', operation: 'enable' });

  expect(sent[0]?.url).toBe(`${API}/v1/schedules/has%20a%20space/enable`);
});

it('carries the deployment’s answer verbatim under its own key', async () => {
  vi.stubGlobal('fetch', answering(201, { job_id: 'j1', name: 'A schedule' }));

  const answer = await post({ operation: 'create', payload: { job_id: 'j1' } });

  expect(await answer.json()).toMatchObject({
    ok: true,
    answer: { job_id: 'j1', name: 'A schedule' },
  });
});

it('carries a refused cron expression back exactly as the deployment worded it', async () => {
  const refusal = "'99 7 * * 1' is outside 0–59 in the minute field of '99 7 * * 1'.";
  vi.stubGlobal(
    'fetch',
    answering(400, { error: { type: 'bad_request', message: refusal } }),
  );

  const answer = await post({
    jobId: 'j1',
    operation: 'update',
    payload: { cron: '99 7 * * 1' },
  });

  expect(answer.status).toBe(400);
  expect(await answer.json()).toMatchObject({ ok: false, reason: refusal });
});

it('will not forward an operation the table does not name', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ jobId: 'j1', operation: 'destroy' })).status).toBe(400);
  expect(sent).toHaveLength(0);
});

it('will not forward an operation that acts on a schedule with no id given', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ operation: 'update', payload: {} })).status).toBe(400);
  expect(sent).toHaveLength(0);
});

it('needs no id to create, since the job id is in the body', async () => {
  vi.stubGlobal('fetch', answering(201, { job_id: 'j1' }));

  const answer = await post({ operation: 'create', payload: { job_id: 'j1' } });

  expect(answer.status).toBe(201);
  expect(sent).toHaveLength(1);
});

it('refuses without a session, and asks the deployment nothing', async () => {
  vi.stubGlobal('fetch', answering(200, {}));

  expect((await post({ jobId: 'j1', operation: 'enable' }, false)).status).toBe(401);
  expect(sent).toHaveLength(0);
});

it('says the deployment could not be reached, not that it refused', async () => {
  vi.stubGlobal('fetch', unreachable());

  const answer = await post({ jobId: 'j1', operation: 'enable' });

  expect(answer.status).toBe(502);
  expect(await answer.json()).toEqual({ ok: false, reachable: false });
});
