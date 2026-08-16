import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Issuing and revoking a machine token, forwarded once.
 *
 * The interesting half is what the issuing courier now carries across that it
 * did not before: `superseded`, the ids of any live token this issuance
 * replaced. Dropping it silently would be exactly the "acúmulo silencioso"
 * the substitution behaviour exists to end — the gateway can supersede a
 * token correctly and the console can still show nobody that it happened.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';
const API = 'http://127.0.0.1:8424';

interface Sent {
  readonly url: string;
  readonly init: RequestInit;
}

function bodyOf(request: Sent | undefined): string {
  return typeof request?.init.body === 'string' ? request.init.body : '';
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

beforeEach(() => {
  sent = [];
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', API);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function postRequest(body: unknown, withSession = true): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/token`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

function deleteRequest(tokenId: string | null, withSession = true): NextRequest {
  const query = tokenId === null ? '' : `?token_id=${encodeURIComponent(tokenId)}`;
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/token${query}`, {
    method: 'DELETE',
  });
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/token/route');
  return POST(postRequest(body, session));
}

async function del(tokenId: string | null, session = true): Promise<Response> {
  const { DELETE } = await import('@/app/api/token/route');
  return DELETE(deleteRequest(tokenId, session));
}

describe('issuing a machine token', () => {
  it('forwards the name and permissions, and returns the secret exactly once', async () => {
    vi.stubGlobal(
      'fetch',
      answering(201, {
        token: { token_id: 'tok-1' },
        secret: 'nsre-sentinel',
        superseded: [],
      }),
    );

    const answer = await post({
      name: 'ci-runner',
      permissions: ['investigation.read'],
    });

    expect(answer.status).toBe(201);
    expect(sent[0]?.url).toBe(`${API}/identity/tokens`);
    expect(bodyOf(sent[0])).toContain('ci-runner');
    expect(await answer.json()).toMatchObject({
      ok: true,
      secret: 'nsre-sentinel',
      superseded: [],
    });
  });

  it('carries which tokens were superseded across, not just whether the call worked', async () => {
    vi.stubGlobal(
      'fetch',
      answering(201, {
        token: { token_id: 'tok-2' },
        secret: 'nsre-sentinel',
        superseded: ['tok-old-1', 'tok-old-2'],
      }),
    );

    const answer = await post({ name: 'ci-runner' });

    expect(await answer.json()).toMatchObject({
      superseded: ['tok-old-1', 'tok-old-2'],
    });
  });

  it('refuses an empty purpose without asking the deployment', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: 'x' }));

    const answer = await post({ name: '  ' });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session rather than asking unauthenticated', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: 'x' }));

    const answer = await post({ name: 'ci-runner' }, false);

    expect(answer.status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('reports the deployment as unreachable rather than as refusing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({ name: 'ci-runner' });

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ ok: false, reachable: false });
  });

  it('names the deployment’s own refusal reason', async () => {
    vi.stubGlobal(
      'fetch',
      answering(400, { detail: "'sorcerer' is not a permission" }),
    );

    const answer = await post({ name: 'ci-runner', permissions: ['sorcerer'] });

    expect(answer.status).toBe(400);
    expect(await answer.json()).toMatchObject({
      reason: "'sorcerer' is not a permission",
    });
  });
});

describe('revoking one machine token', () => {
  it('forwards the id and reports success', async () => {
    vi.stubGlobal('fetch', answering(200, { revoked: 1, token_ids: ['tok-1'] }));

    const answer = await del('tok-1');

    expect(answer.status).toBe(200);
    expect(sent[0]?.url).toBe(`${API}/identity/tokens/tok-1`);
    expect(sent[0]?.init.method).toBe('DELETE');
  });

  it('refuses with no token id named', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    const answer = await del(null);

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    const answer = await del('tok-1', false);

    expect(answer.status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('reports the deployment as unreachable on a network failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await del('tok-1');

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ ok: false, reachable: false });
  });
});
