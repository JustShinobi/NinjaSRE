import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Creating a person with a local password, forwarded once.
 *
 * The interesting half is what this courier must never do: it does not
 * decide whether the caller may create a person (the gateway's own route
 * table does, before this file's `fetch` ever returns), and it never lets a
 * refusal say more than the deployment itself said — the same discipline
 * `../../surfaces/grants.tsx`'s own courier already holds for granting a
 * role.
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
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/principals`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/principals/route');
  return POST(postRequest(body, session));
}

describe('creating a person with a local password', () => {
  it('forwards the three fields and returns the created principal', async () => {
    vi.stubGlobal(
      'fetch',
      answering(201, {
        user_id: 'user-jordan',
        email: 'jordan@northwind.example',
        display_name: 'Jordan Blake',
        kind: 'user',
        is_active: true,
      }),
    );

    const answer = await post({
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      password: 's3cret-first-pass',
    });

    expect(answer.status).toBe(201);
    expect(sent[0]?.url).toBe(`${API}/identity/principals`);
    expect(bodyOf(sent[0])).toContain('jordan@northwind.example');
    expect(bodyOf(sent[0])).toContain('s3cret-first-pass');
    expect(await answer.json()).toMatchObject({
      ok: true,
      answer: { user_id: 'user-jordan', display_name: 'Jordan Blake' },
    });
  });

  it('refuses without a session rather than asking unauthenticated', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    const answer = await post(
      {
        email: 'jordan@northwind.example',
        display_name: 'Jordan Blake',
        password: 'x',
      },
      false,
    );

    expect(answer.status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('refuses a missing email without asking the deployment', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    const answer = await post({ display_name: 'Jordan Blake', password: 'x' });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses a missing display name without asking the deployment', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    const answer = await post({ email: 'jordan@northwind.example', password: 'x' });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses a missing password without asking the deployment', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    const answer = await post({
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
    });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('reports the deployment as unreachable rather than as refusing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      password: 'x',
    });

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ ok: false, reachable: false });
  });

  it("names the deployment's own refusal reason, without inventing one", async () => {
    vi.stubGlobal(
      'fetch',
      answering(409, {
        error: {
          type: 'conflict',
          message:
            "a principal already exists with the email 'jordan@northwind.example'",
          correlation_id: 'abc123',
        },
      }),
    );

    const answer = await post({
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      password: 'x',
    });

    expect(answer.status).toBe(409);
    expect(await answer.json()).toMatchObject({
      ok: false,
      reason: "a principal already exists with the email 'jordan@northwind.example'",
    });
  });

  it('carries no reason when the refusal names none, rather than inventing one', async () => {
    vi.stubGlobal('fetch', answering(403, {}));

    const answer = await post({
      email: 'jordan@northwind.example',
      display_name: 'Jordan Blake',
      password: 'x',
    });

    expect(answer.status).toBe(403);
    expect(await answer.json()).toMatchObject({ ok: false, reason: '' });
  });
});
