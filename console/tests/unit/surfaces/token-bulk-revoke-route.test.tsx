import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * Revoking a set of machine tokens at once, forwarded once.
 *
 * The one gesture `settings/machine-tokens.tsx` offers over a group:
 * "revoke all but the newest". The console already knows which ids are
 * older — it rendered the list — so this forwards an explicit set rather
 * than asking the gateway to decide one on its own.
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

function request(body: unknown, withSession = true): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/token/bulk-revoke`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

async function post(body: unknown, session = true): Promise<Response> {
  const { POST } = await import('@/app/api/token/bulk-revoke/route');
  return POST(request(body, session));
}

describe('revoking many tokens at once', () => {
  it('forwards the ids and the reason, and reports how many were revoked', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { revoked: 2, token_ids: ['tok-old-1', 'tok-old-2'] }),
    );

    const answer = await post({
      token_ids: ['tok-old-1', 'tok-old-2'],
      reason: 'kept only the newest token issued for ci-runner',
    });

    expect(answer.status).toBe(200);
    expect(sent[0]?.url).toBe(`${API}/identity/tokens/revoke`);
    expect(bodyOf(sent[0])).toContain('tok-old-1');
    expect(bodyOf(sent[0])).toContain('kept only the newest');
  });

  it('refuses an empty selection without asking the deployment', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    const answer = await post({ token_ids: [] });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    const answer = await post({ token_ids: ['tok-1'] }, false);

    expect(answer.status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('reports the deployment as unreachable on a network failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({ token_ids: ['tok-1'] });

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ ok: false, reachable: false });
  });

  it('names the deployment’s own refusal reason', async () => {
    vi.stubGlobal(
      'fetch',
      answering(400, { detail: 'that would revoke more than 200 at once' }),
    );

    const answer = await post({ token_ids: ['tok-1'] });

    expect(answer.status).toBe(400);
    expect(await answer.json()).toMatchObject({
      reason: 'that would revoke more than 200 at once',
    });
  });
});
