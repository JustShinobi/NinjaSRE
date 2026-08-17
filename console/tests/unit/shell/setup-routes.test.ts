import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The three couriers the guided first run writes through, and what each of them
 * refuses to do.
 *
 * They exist for one reason: the credential that authenticates a request to the
 * deployment is an HTTP-only, `SameSite=Strict` cookie set on this host, and a
 * browser will not send it anywhere else. So these forward, once, and hold
 * nothing — which is exactly the claim worth testing, because "it kept nothing"
 * is invisible in a screenshot and obvious in an assertion.
 *
 * The credential one is the one that matters. Everything below about it is a
 * place the value must *not* end up: not in the outbound URL, not in the
 * response, not in a log line, and not in anything this process keeps.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';
const API = 'http://127.0.0.1:8424';

/** The value hunted for. A sentinel rather than a shape: a test that looked for
 * "forty hex characters" would pass against a log line carrying this one. */
const SENTINEL = 'sk-ant-unit-9d41c7a2b6e30f58';

interface Sent {
  readonly url: string;
  readonly init: RequestInit;
}

let sent: Sent[] = [];

function answering(
  status: number,
  body: unknown,
): (url: unknown, init?: RequestInit) => Promise<Response> {
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

/** What was sent as a body, as text. Every one of these is a JSON string. */
function bodyOf(request: Sent | undefined): string {
  return typeof request?.init.body === 'string' ? request.init.body : '';
}

function request(path: string, body: unknown, withSession = true): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}${path}`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
}

beforeEach(() => {
  sent = [];
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', API);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('the credential courier', () => {
  const WRITTEN = {
    integration: 'anthropic',
    state: 'usable',
    usable: true,
    version: 1,
    fields: ['ANTHROPIC_API_KEY'],
  };

  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/credential/route');
    return POST(request('/api/credential', body, session));
  }

  it('forwards one PUT to the deployment, with the value only in the body', async () => {
    vi.stubGlobal('fetch', answering(200, WRITTEN));

    const answer = await post({
      integration: 'anthropic',
      values: { ANTHROPIC_API_KEY: SENTINEL },
    });

    expect(answer.status).toBe(200);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.url).toBe(`${API}/v1/integrations/anthropic/credential`);
    expect(sent[0]?.url).not.toContain(SENTINEL);
    expect(sent[0]?.init.method).toBe('PUT');
    expect(bodyOf(sent[0])).toContain(SENTINEL);
  });

  it('presents the session credential the browser cannot present itself', async () => {
    vi.stubGlobal('fetch', answering(200, WRITTEN));

    await post({ integration: 'anthropic', values: { k: SENTINEL } });

    const headers = new Headers(sent[0]?.init.headers);
    expect(headers.get('authorization')).toBe('Bearer tok_session');
  });

  it('returns the field names and the version, and no value', async () => {
    vi.stubGlobal('fetch', answering(200, WRITTEN));

    const answer = await post({
      integration: 'anthropic',
      values: { ANTHROPIC_API_KEY: SENTINEL },
    });
    const text = await answer.text();

    expect(text).toContain('ANTHROPIC_API_KEY');
    expect(text).toContain('"version":1');
    // The whole guarantee, in one assertion: there is no field in the answer a
    // value could be sitting in.
    expect(text).not.toContain(SENTINEL);
  });

  it('refuses without a session rather than forwarding an anonymous write', async () => {
    vi.stubGlobal('fetch', answering(200, WRITTEN));

    const answer = await post({ integration: 'anthropic', values: {} }, false);

    expect(answer.status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('refuses a body that is not a credential write', async () => {
    vi.stubGlobal('fetch', answering(200, WRITTEN));

    expect((await post({ values: {} })).status).toBe(400);
    expect((await post({ integration: 'anthropic', values: 'nope' })).status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('drops a field whose value is not a string rather than coercing it', async () => {
    vi.stubGlobal('fetch', answering(200, WRITTEN));

    await post({ integration: 'anthropic', values: { good: SENTINEL, bad: { a: 1 } } });

    // `String({})` is a credential of "[object Object]", which the vault would
    // store without complaint.
    expect(bodyOf(sent[0])).not.toContain('object Object');
    expect(bodyOf(sent[0])).toContain(SENTINEL);
  });

  it('forwards the deployment’s own refusal, which names fields and quotes none', async () => {
    vi.stubGlobal('fetch', answering(400, { detail: 'api_token is required' }));

    const answer = await post({ integration: 'metrics-store', values: {} });
    const body: unknown = await answer.json();

    expect(answer.status).toBe(400);
    expect(Reflect.get(Object(body), 'ok')).toBe(false);
    expect(Reflect.get(Object(body), 'reason')).toBe('api_token is required');
  });

  it('says the deployment could not be reached rather than that it refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({ integration: 'anthropic', values: { k: SENTINEL } });
    const body: unknown = await answer.json();

    expect(answer.status).toBe(502);
    expect(Reflect.get(Object(body), 'reachable')).toBe(false);
  });
});

describe('the verification courier', () => {
  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/verify/route');
    return POST(request('/api/verify', body, session));
  }

  it('reaches the provider route for a provider and the integration route for one', async () => {
    vi.stubGlobal('fetch', answering(200, { verified: true, detail: 'it answered' }));

    await post({ kind: 'provider', name: 'anthropic' });
    await post({ kind: 'integration', name: 'metrics-store' });

    expect(sent[0]?.url).toBe(`${API}/v1/providers/anthropic/verify`);
    expect(sent[1]?.url).toBe(`${API}/v1/integrations/metrics-store/verify`);
  });

  it('reports a stored credential nobody checked as not verified', async () => {
    // The integration route answers `usable`; the provider route answers
    // `verified`. Collapsing the two into one word for the caller is fine;
    // collapsing them into one *claim* is the thing that must not happen.
    vi.stubGlobal('fetch', answering(200, { state: 'usable', usable: false }));

    const answer = await post({ kind: 'integration', name: 'metrics-store' });
    const body: unknown = await answer.json();

    expect(Reflect.get(Object(body), 'verified')).toBe(false);
  });

  it('carries the remedy through, which is what names a skipped field', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, {
        verified: false,
        detail: 'the endpoint refused the key',
        remedy: 'ANTHROPIC_API_KEY was skipped at setup',
      }),
    );

    const answer = await post({ kind: 'provider', name: 'anthropic' });
    const body: unknown = await answer.json();

    expect(Reflect.get(Object(body), 'remedy')).toContain('ANTHROPIC_API_KEY');
  });

  it('refuses a kind it does not serve, and a request with no session', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    expect((await post({ kind: 'everything', name: 'x' })).status).toBe(400);
    expect((await post({ kind: 'provider', name: '' })).status).toBe(400);
    expect((await post({ kind: 'provider', name: 'x' }, false)).status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('separates a deployment that refused from one that was not there', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({ kind: 'provider', name: 'anthropic' });

    expect(answer.status).toBe(502);
    expect(Reflect.get(Object(await answer.json()), 'reachable')).toBe(false);
  });

  it('asks the vendor’s own report for a usable integration, and carries its degradations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: unknown, init?: RequestInit) => {
        const address = String(url);
        sent.push({ url: address, init: init ?? {} });
        if (address.endsWith('/verify/report')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ report: { degradations: ['clock is 90s out'] } }),
              { status: 200, headers: { 'content-type': 'application/json' } },
            ),
          );
        }
        return Promise.resolve(
          new Response(JSON.stringify({ usable: true, state: 'usable' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        );
      }),
    );

    const answer = await post({ kind: 'integration', name: 'metrics-store' });
    const body: unknown = await answer.json();

    expect(sent[1]?.url).toBe(`${API}/v1/integrations/metrics-store/verify/report`);
    expect(Reflect.get(Object(body), 'findings')).toEqual(['clock is 90s out']);
  });

  it('finds nothing to report for a provider, or for a vendor with no report to give', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: unknown, init?: RequestInit) => {
        const address = String(url);
        sent.push({ url: address, init: init ?? {} });
        if (address.endsWith('/verify/report')) {
          return Promise.resolve(new Response('', { status: 404 }));
        }
        return Promise.resolve(
          new Response(JSON.stringify({ usable: true, state: 'usable' }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
          }),
        );
      }),
    );

    // A provider has no report route at all — `findingsFor` is never asked.
    const provider = await post({ kind: 'provider', name: 'anthropic' });
    expect(Reflect.get(Object(await provider.json()), 'findings')).toEqual([]);
    expect(sent).toHaveLength(1);

    sent = [];
    // An integration whose vendor answers the report route with a 404 — a
    // working deployment with nothing further to say, not a failure.
    const integration = await post({ kind: 'integration', name: 'metrics-store' });
    expect(Reflect.get(Object(await integration.json()), 'findings')).toEqual([]);
  });
});

describe('the configuration courier', () => {
  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/config/route');
    return POST(request('/api/config', body, session));
  }

  it('forwards the patch verbatim, so a preview and a save are of one document', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { values: { 'models.investigator.model': 'm' } }),
    );
    const patch = { 'models.investigator.provider': 'ollama' };

    await post({ nodeId: 'team-a', patch });

    expect(sent[0]?.url).toBe(`${API}/v1/config/team-a`);
    expect(sent[0]?.init.method).toBe('PUT');
    // Wrapped in `patch` and otherwise untouched. A handler that merged or
    // reordered would make the preview a preview of something else. `remove`
    // travels beside it, empty when the caller named nothing to clear — see
    // `console/tests/unit/surfaces/routes.test.ts` for the non-empty case.
    expect(JSON.parse(bodyOf(sent[0]))).toEqual({ patch, remove: [] });
  });

  it('refuses a patch with no node, and a request with no session', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    expect((await post({ patch: {} })).status).toBe(400);
    expect((await post({ nodeId: 'team-a', patch: 'nope' })).status).toBe(400);
    expect((await post({ nodeId: 'team-a', patch: {} }, false)).status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('says the deployment could not be reached when it could not', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({ nodeId: 'team-a', patch: { a: 'b' } });

    expect(answer.status).toBe(502);
    expect(Reflect.get(Object(await answer.json()), 'reachable')).toBe(false);
  });
});
