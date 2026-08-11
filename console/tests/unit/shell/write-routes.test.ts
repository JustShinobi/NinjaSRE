import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The four couriers this feature's write surfaces go through.
 *
 * Each exists for the same reason every courier here does — the session
 * credential is an HTTP-only, `SameSite=Strict` cookie the browser will not send
 * to another host — and what is worth asserting about each is the same three
 * things: which address it reaches, that it refuses without a session, and that
 * a deployment it could not reach is reported as *unreachable* rather than as a
 * refusal. An operator told the deployment refused them goes looking for a
 * permission; one told it could not be reached goes and looks at the machine.
 *
 * The two multi-operation handlers get a fourth assertion, and it is the one
 * that keeps them from being open proxies: an operation the table does not name
 * cannot be reached through them at all.
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

/** What the last forwarded request put on the wire, as text. */
function sentBody(): string {
  const body = sent[0]?.init.body;
  return typeof body === 'string' ? body : '';
}

function unreachable() {
  return vi.fn(() => Promise.reject(new TypeError('fetch failed')));
}

function request(
  path: string,
  body: unknown,
  { session = true, method = 'POST' } = {},
): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}${path}`, {
    method,
    ...(body === null ? {} : { body: JSON.stringify(body) }),
    headers: { 'content-type': 'application/json' },
  });
  if (session) made.cookies.set(SESSION_COOKIE, 'tok_session');
  return made;
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

describe('the emergency stop', () => {
  async function engage(session = true): Promise<Response> {
    const { POST } = await import('@/app/api/kill-switch/route');
    return POST(
      request('/api/kill-switch', { reason: 'the controller is lying' }, { session }),
    );
  }

  it('forwards an engagement with the reason, and reports what came back', async () => {
    vi.stubGlobal('fetch', answering(200, { engaged: true }));

    const answer = await engage();

    expect(sent[0]?.url).toBe(`${API}/v1/autonomy/kill-switch`);
    expect(await answer.json()).toMatchObject({ ok: true, engaged: true });
  });

  it('forwards a release with no body at all', async () => {
    vi.stubGlobal('fetch', answering(200, { engaged: false }));
    const { DELETE } = await import('@/app/api/kill-switch/route');

    await DELETE(request('/api/kill-switch', null, { method: 'DELETE' }));

    expect(sent[0]?.init.method).toBe('DELETE');
    expect(sent[0]?.init.body).toBeUndefined();
  });

  it('refuses without a session rather than asking unauthenticated', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    expect((await engage(false)).status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('refuses a release without a session too', async () => {
    vi.stubGlobal('fetch', answering(200, {}));
    const { DELETE } = await import('@/app/api/kill-switch/route');

    const answer = await DELETE(
      request('/api/kill-switch', null, { session: false, method: 'DELETE' }),
    );

    expect(answer.status).toBe(401);
  });

  it('says the deployment could not be reached, not that it refused', async () => {
    vi.stubGlobal('fetch', unreachable());

    const answer = await engage();

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ ok: false, reachable: false });
  });
});

describe('machine tokens', () => {
  async function issue(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/token/route');
    return POST(request('/api/token', body, { session }));
  }

  it('forwards an issuance and returns the secret exactly as it came', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: 'nsre-sentinel' }));

    const answer = await issue({
      name: 'ci-runner',
      permissions: ['investigation.read'],
    });

    expect(sent[0]?.url).toBe(`${API}/identity/tokens`);
    expect(await answer.json()).toMatchObject({ ok: true, secret: 'nsre-sentinel' });
  });

  it('carries a lifetime when one was asked for, and omits it otherwise', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: 'x' }));

    await issue({ name: 'ci-runner', lifetimeDays: 30 });
    expect(sentBody()).toContain('lifetime_days');

    sent = [];
    await issue({ name: 'ci-runner' });
    expect(sentBody()).not.toContain('lifetime_days');
  });

  it('refuses a token nobody said what it is for', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    expect((await issue({ name: '  ' })).status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    expect((await issue({ name: 'ci-runner' }, false)).status).toBe(401);
  });

  it('reports an unreachable deployment as unreachable', async () => {
    vi.stubGlobal('fetch', unreachable());

    expect((await issue({ name: 'ci-runner' })).status).toBe(502);
  });

  it('revokes by identifier, and refuses without one', async () => {
    vi.stubGlobal('fetch', answering(200, { revoked: 1 }));
    const { DELETE } = await import('@/app/api/token/route');

    const named = await DELETE(
      request('/api/token?token_id=tok-1', null, { method: 'DELETE' }),
    );
    expect(named.status).toBe(200);
    expect(sent[0]?.url).toBe(`${API}/identity/tokens/tok-1`);

    const unnamed = await DELETE(request('/api/token', null, { method: 'DELETE' }));
    expect(unnamed.status).toBe(400);
  });

  it('refuses a revocation without a session, and reports an unreachable one', async () => {
    vi.stubGlobal('fetch', answering(200, {}));
    const { DELETE } = await import('@/app/api/token/route');

    const refused = await DELETE(
      request('/api/token?token_id=tok-1', null, { session: false, method: 'DELETE' }),
    );
    expect(refused.status).toBe(401);

    vi.stubGlobal('fetch', unreachable());
    const silent = await DELETE(
      request('/api/token?token_id=tok-1', null, { method: 'DELETE' }),
    );
    expect(silent.status).toBe(502);
  });
});

describe('the autonomy policy', () => {
  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/autonomy/route');
    return POST(request('/api/autonomy', body, { session }));
  }

  it('sends each named operation to its own address and method', async () => {
    vi.stubGlobal('fetch', answering(200, { summary: 'nothing' }));

    await post({ nodeId: 'team-platform', operation: 'save', payload: { rules: [] } });
    expect(sent[0]?.url).toBe(`${API}/v1/autonomy/policy/team-platform`);
    expect(sent[0]?.init.method).toBe('PUT');

    sent = [];
    await post({ nodeId: 'team-platform', operation: 'preview', payload: {} });
    expect(sent[0]?.url).toBe(`${API}/v1/autonomy/policy/team-platform/preview`);
    expect(sent[0]?.init.method).toBe('POST');

    sent = [];
    await post({
      nodeId: 'team-platform',
      operation: 'dry-run',
      payload: { enabled: true },
    });
    expect(sent[0]?.url).toBe(`${API}/v1/autonomy/policy/team-platform/dry-run`);
  });

  it('grants an override at its own address, with a reason in the body', async () => {
    vi.stubGlobal('fetch', answering(201, { name: 'incident-widen' }));

    await post({
      nodeId: 'team-platform',
      operation: 'override',
      payload: { name: 'incident-widen', level: 'act_on_low_risk', reason: 'paged' },
    });

    expect(sent[0]?.url).toBe(`${API}/v1/autonomy/policy/team-platform/overrides`);
    expect(sent[0]?.init.method).toBe('POST');
    expect(sentBody()).toContain('incident-widen');
  });

  it('revokes an override by name, as a DELETE with no body', async () => {
    vi.stubGlobal('fetch', answering(200, { name: 'incident-widen' }));

    await post({
      nodeId: 'team-platform',
      operation: 'revoke-override',
      payload: { name: 'incident-widen' },
    });

    expect(sent[0]?.url).toBe(
      `${API}/v1/autonomy/policy/team-platform/overrides/incident-widen`,
    );
    expect(sent[0]?.init.method).toBe('DELETE');
    expect(sent[0]?.init.body).toBeUndefined();
  });

  it('encodes an override name that needs it', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    await post({
      nodeId: 'team-platform',
      operation: 'revoke-override',
      payload: { name: 'a name/with slash' },
    });

    expect(sent[0]?.url).toBe(
      `${API}/v1/autonomy/policy/team-platform/overrides/${encodeURIComponent('a name/with slash')}`,
    );
  });

  it('will not revoke an override nobody named', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    const answer = await post({
      nodeId: 'team-platform',
      operation: 'revoke-override',
      payload: {},
    });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('reports a revocation the deployment refused, naming where it has to happen', async () => {
    vi.stubGlobal(
      'fetch',
      answering(404, {
        detail:
          'this node granted no override named incident-widen; an inherited override is revoked at the node that granted it',
      }),
    );

    const answer = await post({
      nodeId: 'team-platform',
      operation: 'revoke-override',
      payload: { name: 'incident-widen' },
    });

    expect(answer.status).toBe(404);
    const body: unknown = await answer.clone().json();
    expect(await answer.json()).toMatchObject({ ok: false });
    expect(Reflect.get(Object(body), 'reason')).toContain(
      'is revoked at the node that granted it',
    );
  });

  it('returns the deployment’s answer verbatim under its own key', async () => {
    vi.stubGlobal(
      'fetch',
      answering(200, { summary: 'two would change', considered: 41 }),
    );

    const answer = await post({ nodeId: 'n', operation: 'preview', payload: {} });

    expect(await answer.json()).toMatchObject({
      ok: true,
      answer: { summary: 'two would change', considered: 41 },
    });
  });

  it('carries the deployment’s refusal reason back', async () => {
    vi.stubGlobal('fetch', answering(400, { detail: 'that is not a level' }));

    const answer = await post({ nodeId: 'n', operation: 'save', payload: {} });

    expect(answer.status).toBe(400);
    expect(await answer.json()).toMatchObject({
      ok: false,
      reason: 'that is not a level',
    });
  });

  it('will not forward an operation the table does not name', async () => {
    // The property that keeps one handler for five operations from being a way
    // to address an arbitrary path on the deployment.
    vi.stubGlobal('fetch', answering(200, {}));

    expect(
      (await post({ nodeId: 'n', operation: 'delete-everything', payload: {} })).status,
    ).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('will not forward an operation with no node to apply it to', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    expect((await post({ operation: 'save', payload: {} })).status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session, and reports an unreachable deployment', async () => {
    vi.stubGlobal('fetch', answering(200, {}));
    expect((await post({ nodeId: 'n', operation: 'save' }, false)).status).toBe(401);

    vi.stubGlobal('fetch', unreachable());
    expect((await post({ nodeId: 'n', operation: 'save' })).status).toBe(502);
  });
});

describe('single sign-on', () => {
  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/sso/route');
    return POST(request('/api/sso', body, { session }));
  }

  it('sends each named operation to its own address and method', async () => {
    vi.stubGlobal('fetch', answering(200, { verified: false }));

    await post({ operation: 'save', payload: { provider: 'keycloak' } });
    expect(sent[0]?.url).toBe(`${API}/identity/sso`);
    expect(sent[0]?.init.method).toBe('PUT');

    sent = [];
    await post({ operation: 'test', payload: { claims: {} } });
    expect(sent[0]?.url).toBe(`${API}/identity/sso/test`);

    sent = [];
    await post({ operation: 'activate', payload: {} });
    expect(sent[0]?.url).toBe(`${API}/identity/sso/activate`);
  });

  it('returns the deployment’s answer, which is where `verified` is decided', async () => {
    vi.stubGlobal('fetch', answering(200, { is_active: false, verified: true }));

    const answer = await post({ operation: 'test', payload: { claims: {} } });

    expect(await answer.json()).toMatchObject({ answer: { verified: true } });
  });

  it('carries a refusal reason back rather than flattening it', async () => {
    vi.stubGlobal('fetch', answering(400, { detail: 'run the test first' }));

    const answer = await post({ operation: 'activate', payload: {} });

    expect(answer.status).toBe(400);
    expect(await answer.json()).toMatchObject({ reason: 'run the test first' });
  });

  it('will not forward an operation the table does not name', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    expect((await post({ operation: 'deactivate', payload: {} })).status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session, and reports an unreachable deployment', async () => {
    vi.stubGlobal('fetch', answering(200, {}));
    expect((await post({ operation: 'save', payload: {} }, false)).status).toBe(401);

    vi.stubGlobal('fetch', unreachable());
    expect((await post({ operation: 'save', payload: {} })).status).toBe(502);
  });
});

describe('role grants', () => {
  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/grants/route');
    return POST(request('/api/grants', body, { session }));
  }

  it('sends each named operation to its own address and method', async () => {
    vi.stubGlobal(
      'fetch',
      answering(201, {
        grant_id: 'grant-1',
        principal_id: 'user-avery',
        role: 'owner',
      }),
    );

    await post({
      operation: 'add',
      payload: { principal_id: 'user-avery', role: 'owner' },
    });
    expect(sent[0]?.url).toBe(`${API}/identity/grants`);
    expect(sent[0]?.init.method).toBe('POST');

    sent = [];
    vi.stubGlobal('fetch', answering(200, { grant_id: 'grant-1' }));
    await post({ operation: 'remove', payload: { grant_id: 'grant-1' } });
    expect(sent[0]?.url).toBe(`${API}/identity/grants/grant-1`);
    expect(sent[0]?.init.method).toBe('DELETE');
  });

  it('encodes a grant identifier that needs it', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    await post({ operation: 'remove', payload: { grant_id: 'grant with space' } });

    expect(sent[0]?.url).toBe(
      `${API}/identity/grants/${encodeURIComponent('grant with space')}`,
    );
  });

  it('returns the deployment’s answer verbatim under its own key', async () => {
    vi.stubGlobal(
      'fetch',
      answering(201, {
        grant_id: 'grant-9',
        principal_id: 'user-avery',
        role: 'owner',
      }),
    );

    const answer = await post({
      operation: 'add',
      payload: { principal_id: 'user-avery', role: 'owner' },
    });

    expect(await answer.json()).toMatchObject({
      ok: true,
      answer: { grant_id: 'grant-9', principal_id: 'user-avery', role: 'owner' },
    });
  });

  it('reads the refusal from the {"error": {...}} envelope this route answers', async () => {
    vi.stubGlobal(
      'fetch',
      answering(400, {
        error: {
          type: 'bad_request',
          message: "'ceo' is not a role this deployment has",
          correlation_id: 'corr-1',
        },
      }),
    );

    const answer = await post({
      operation: 'add',
      payload: { principal_id: 'user-avery', role: 'ceo' },
    });

    expect(answer.status).toBe(400);
    expect(await answer.json()).toMatchObject({
      ok: false,
      reason: "'ceo' is not a role this deployment has",
    });
  });

  it('carries the last-owner refusal back with its own status', async () => {
    vi.stubGlobal(
      'fetch',
      answering(409, {
        error: {
          type: 'conflict',
          message:
            'removing this grant would leave the organisation with no owner; grant ownership to somebody else first',
          correlation_id: 'corr-2',
        },
      }),
    );

    const answer = await post({
      operation: 'remove',
      payload: { grant_id: 'grant-1' },
    });

    expect(answer.status).toBe(409);
    const body: unknown = await answer.json();
    expect(Reflect.get(Object(body), 'ok')).toBe(false);
    expect(String(Reflect.get(Object(body), 'reason'))).toContain(
      'grant ownership to somebody else first',
    );
  });

  it('will not forward an operation the table does not name', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    expect((await post({ operation: 'delete-everything', payload: {} })).status).toBe(
      400,
    );
    expect(sent).toHaveLength(0);
  });

  it('will not remove a grant nobody named', async () => {
    vi.stubGlobal('fetch', answering(200, {}));

    const answer = await post({ operation: 'remove', payload: {} });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('treats a body that is not JSON as naming no operation, rather than crashing', async () => {
    vi.stubGlobal('fetch', answering(200, {}));
    const { POST } = await import('@/app/api/grants/route');
    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/grants`, {
      method: 'POST',
      body: 'not json',
      headers: { 'content-type': 'application/json' },
    });
    made.cookies.set(SESSION_COOKIE, 'tok_session');

    expect((await POST(made)).status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('treats a reply that is not JSON as an empty one, rather than crashing', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(new Response('not json', { status: 200 })),
    );

    const answer = await post({
      operation: 'add',
      payload: { principal_id: 'user-avery', role: 'owner' },
    });

    expect(answer.status).toBe(200);
    expect(await answer.json()).toMatchObject({ ok: true, reason: '' });
  });

  it('refuses without a session, and reports an unreachable deployment', async () => {
    vi.stubGlobal('fetch', answering(200, {}));
    expect(
      (
        await post(
          { operation: 'add', payload: { principal_id: 'user-avery', role: 'owner' } },
          false,
        )
      ).status,
    ).toBe(401);

    vi.stubGlobal('fetch', unreachable());
    expect(
      (
        await post({
          operation: 'add',
          payload: { principal_id: 'user-avery', role: 'owner' },
        })
      ).status,
    ).toBe(502);
  });
});
