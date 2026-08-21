import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DELETE, POST } from '@/app/api/credential/route';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The credential courier, held to the four things its own docstring says it
 * does not do.
 *
 * It carries a secret because it has to: the session credential is an
 * HTTP-only, `SameSite=Strict` cookie on the console's host, so a form posted
 * straight at the gateway arrives unauthenticated. The property the handler
 * claims is not "the secret never enters this process" — it does — but "this
 * process keeps none of it". Every claim below is one somebody could break
 * with an edit that looks harmless.
 *
 * The one that is easiest to break silently is the shape check. `String({})`
 * is `"[object Object]"`, and a vault will store that as happily as a real
 * key; a field whose value is not a string has to be *dropped* rather than
 * coerced, or a probe becomes a stored credential.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';

function request(
  method: 'POST' | 'DELETE',
  body: unknown,
  credential = 'tok_console',
): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/credential`, {
    method,
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (credential !== '') made.cookies.set(SESSION_COOKIE, credential);
  return made;
}

function answering(status: number, body = '{}'): typeof fetch {
  return vi.fn(() => Promise.resolve(new Response(body, { status })));
}

function callsOf(fetching: typeof fetch): [string, RequestInit][] {
  return (fetching as unknown as ReturnType<typeof vi.fn>).mock.calls as [
    string,
    RequestInit,
  ][];
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('what has to be true before anything is sent', () => {
  it('refuses a caller with no session rather than asking the gateway', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(
      request('POST', { integration: 'datadog', values: {} }, ''),
    );

    expect(answer.status).toBe(401);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('refuses a body that names no integration', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(request('POST', { values: { api_key: 'k' } }));

    expect(answer.status).toBe(400);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('refuses an integration named with an empty string', async () => {
    vi.stubGlobal('fetch', answering(200));

    expect((await POST(request('POST', { integration: '', values: {} }))).status).toBe(
      400,
    );
  });

  it('refuses values that are not a record', async () => {
    vi.stubGlobal('fetch', answering(200));

    for (const values of [null, ['api_key'], 'api_key', 7]) {
      const answer = await POST(request('POST', { integration: 'datadog', values }));
      expect(answer.status, JSON.stringify(values)).toBe(400);
    }
  });

  it('refuses a body that is not JSON at all', async () => {
    vi.stubGlobal('fetch', answering(200));
    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/credential`, {
      method: 'POST',
      body: 'not json',
      headers: { 'content-type': 'application/json' },
    });
    made.cookies.set(SESSION_COOKIE, 'tok_console');

    expect((await POST(made)).status).toBe(400);
  });
});

describe('what crosses to the gateway', () => {
  it('drops a field whose value is not a string, rather than coercing it', async () => {
    const fetching = answering(
      200,
      '{"state":"stored","version":1,"fields":["api_key"]}',
    );
    vi.stubGlobal('fetch', fetching);

    await POST(
      request('POST', {
        integration: 'datadog',
        values: { api_key: 'real', probe: { nested: true }, count: 7 },
      }),
    );

    const [, init] = callsOf(fetching)[0] ?? ['', {}];
    const sent = typeof init.body === 'string' ? init.body : '';
    expect(sent).toContain('api_key');
    expect(sent).not.toContain('object Object');
    expect(sent).not.toContain('probe');
    expect(sent).not.toContain('count');
  });

  it('never puts a value in the address', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    await POST(
      request('POST', {
        integration: 'datadog',
        values: { api_key: 'sk-not-a-real-key' },
      }),
    );

    const [address] = callsOf(fetching)[0] ?? [''];
    expect(address).toContain('/v1/integrations/datadog/credential');
    expect(address).not.toContain('sk-not-a-real-key');
  });

  it('forwards what the gateway said the credential now is', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, '{"state":"stored","version":3,"fields":["api_key","site"]}'),
    );

    const answer = await POST(
      request('POST', { integration: 'datadog', values: { api_key: 'k' } }),
    );
    const body: unknown = await answer.json();

    expect(answer.status).toBe(200);
    expect(body).toMatchObject({
      ok: true,
      reachable: true,
      state: 'stored',
      version: 3,
    });
  });

  it('forwards a refusal in the gateway’s own words', async () => {
    vi.stubGlobal('fetch', answering(422, '{"detail":"site is required"}'));

    const answer = await POST(
      request('POST', { integration: 'datadog', values: { api_key: 'k' } }),
    );
    const body: unknown = await answer.json();

    expect(answer.status).toBe(422);
    expect(body).toMatchObject({ ok: false, reason: 'site is required' });
  });

  it('says nothing of its own when the refusal carries no words', async () => {
    vi.stubGlobal('fetch', answering(500, '{"detail":{"unexpected":"shape"}}'));

    const body: unknown = await (
      await POST(request('POST', { integration: 'datadog', values: { api_key: 'k' } }))
    ).json();

    expect(body).toMatchObject({ ok: false, reason: '' });
  });

  it('survives an answer that is not JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('<html>', { status: 502 }))),
    );

    const body: unknown = await (
      await POST(request('POST', { integration: 'datadog', values: { api_key: 'k' } }))
    ).json();

    expect(body).toMatchObject({ ok: false, reachable: true, version: 0 });
  });

  it('says the deployment is unreachable, not that it refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('connect ECONNREFUSED'))),
    );

    const answer = await POST(
      request('POST', { integration: 'datadog', values: { api_key: 'k' } }),
    );
    const body: unknown = await answer.json();

    expect(answer.status).toBe(502);
    expect(body).toMatchObject({ ok: false, reachable: false });
  });
});

describe('disconnecting an integration', () => {
  it('refuses a caller with no session', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    expect(
      (await DELETE(request('DELETE', { integration: 'datadog' }, ''))).status,
    ).toBe(401);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('refuses a body that names no integration', async () => {
    vi.stubGlobal('fetch', answering(200));

    expect((await DELETE(request('DELETE', { integration: '' }))).status).toBe(400);
    expect((await DELETE(request('DELETE', {}))).status).toBe(400);
  });

  it('reports how many versions the deployment removed', async () => {
    vi.stubGlobal('fetch', answering(200, '{"versions_removed":4}'));

    const body: unknown = await (
      await DELETE(request('DELETE', { integration: 'datadog' }))
    ).json();

    expect(body).toMatchObject({ ok: true, reachable: true, versionsRemoved: 4 });
  });

  it('forwards the refusal rather than inventing one', async () => {
    vi.stubGlobal(
      'fetch',
      answering(404, '{"detail":"nothing is stored for datadog"}'),
    );

    const answer = await DELETE(request('DELETE', { integration: 'datadog' }));

    expect(answer.status).toBe(404);
    expect(await answer.json()).toMatchObject({
      reason: 'nothing is stored for datadog',
    });
  });

  it('says the deployment is unreachable when it cannot be asked', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('connect ECONNREFUSED'))),
    );

    const answer = await DELETE(request('DELETE', { integration: 'datadog' }));

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ reachable: false });
  });
});
