import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST as decide } from '@/app/api/decision/route';
import { POST as preview } from '@/app/api/preview/route';
import { POST as write } from '@/app/api/config/route';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The two couriers, and what each of them refuses.
 *
 * Both exist for one reason: the credential is in an HTTP-only cookie, so a
 * browser cannot present it and a decision or a preview made on a screen has to
 * pass through the console's own process. Neither *decides* anything — that is
 * the property under test. The preview returns the deployment's answer verbatim
 * and holds no merge; the decision forwards a verdict and refuses exactly one
 * thing on its own account, which is a rejection with no reason.
 */

const ORIGIN = 'http://localhost:3000';

function request(path: string, body: unknown, credential = 'a-token'): NextRequest {
  const made = new NextRequest(`${ORIGIN}${path}`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (credential !== '') {
    made.cookies.set(SESSION_COOKIE, credential);
  }
  return made;
}

let sent: { url: string; init: RequestInit } | null = null;

beforeEach(() => {
  sent = null;
  vi.stubGlobal('fetch', (url: unknown, init: RequestInit) => {
    sent = { url: String(url), init };
    return Promise.resolve(
      new Response(JSON.stringify({ changes: [{ path: 'a', before: 1, after: 2 }] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** What was actually put on the wire, as text. */
function bodySent(): string {
  const body = sent?.init.body;
  return typeof body === 'string' ? body : '';
}

describe('deciding an approval', () => {
  it('forwards an approval with the session’s credential', async () => {
    const answer = await decide(
      request('/api/decision', { interactionId: 'int-1', verdict: 'approve' }),
    );

    expect(answer.status).toBe(200);
    expect(sent?.url).toContain('/v1/interactions/int-1/approve');
    expect(
      new Headers(sent?.init.headers).get('authorization'),
      'the credential never leaves the server, so this is where it is presented',
    ).toBe('Bearer a-token');
  });

  it('refuses a rejection with no reason, rather than forwarding one', async () => {
    const answer = await decide(
      request('/api/decision', {
        interactionId: 'int-1',
        verdict: 'reject',
        reason: '  ',
      }),
    );

    expect(answer.status).toBe(422);
    expect(sent, 'a reasonless rejection reached the deployment').toBeNull();
  });

  it('forwards a rejection that carries one, with the reason', async () => {
    await decide(
      request('/api/decision', {
        interactionId: 'int-1',
        verdict: 'reject',
        reason: 'the snapshot is the only pre-change rollback',
      }),
    );

    expect(bodySent()).toContain('the only pre-change rollback');
  });

  it('refuses a verdict it has never heard of', async () => {
    const answer = await decide(
      request('/api/decision', { interactionId: 'int-1', verdict: 'maybe' }),
    );

    expect(answer.status).toBe(400);
    expect(sent).toBeNull();
  });

  it('refuses a request carrying no session', async () => {
    const answer = await decide(
      request('/api/decision', { interactionId: 'int-1', verdict: 'approve' }, ''),
    );

    expect(answer.status).toBe(401);
  });

  it('says the deployment was unreachable rather than that it refused', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('no route to host')));

    const answer = await decide(
      request('/api/decision', { interactionId: 'int-1', verdict: 'approve' }),
    );

    // Different problems for different people: one is retried, the other is
    // somebody going to look at an outage.
    expect(answer.status).toBe(502);
  });
});

describe('previewing a configuration change', () => {
  it('asks the deployment and returns its answer', async () => {
    const answer = await preview(
      request('/api/preview', { nodeId: 'org-northwind', patch: { 'a.b': '2' } }),
    );

    expect(sent?.url).toContain('/v1/config/org-northwind/preview');
    const body: unknown = await answer.json();
    // Verbatim. A reshaping here would be the second opinion the whole design
    // exists to avoid.
    expect(body).toEqual({ changes: [{ path: 'a', before: 1, after: 2 }] });
  });

  it('refuses a request with no patch in it', async () => {
    const answer = await preview(request('/api/preview', { nodeId: 'org-northwind' }));

    expect(answer.status).toBe(400);
    expect(sent).toBeNull();
  });

  it('names what was missing when it refuses, so the screen has words to show', async () => {
    // "The deployment refused:" with nothing after the colon was this body:
    // a 400 whose JSON carried no reason at all.
    const answer = await preview(request('/api/preview', { nodeId: '', patch: {} }));

    expect(answer.status).toBe(400);
    const body: unknown = await answer.json();
    const reason: unknown = Reflect.get(Object(body), 'reason');
    expect(typeof reason).toBe('string');
    expect(String(reason)).not.toBe('');
  });

  it('refuses a request carrying no session', async () => {
    const answer = await preview(
      request('/api/preview', { nodeId: 'n', patch: {} }, ''),
    );

    expect(answer.status).toBe(401);
  });

  it('says the deployment was unreachable rather than that nothing would change', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('no route to host')));

    const answer = await preview(
      request('/api/preview', { nodeId: 'n', patch: { a: '1' } }),
    );

    expect(answer.status).toBe(502);
  });
});

describe('writing a configuration change', () => {
  it('carries a refusal whose detail is not a string, as readable text', async () => {
    // The gateway's validation errors arrive as structures. A courier that
    // only forwarded a string `detail` turned every one of them into
    // "refused:" with nothing after the colon.
    vi.stubGlobal('fetch', () =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            detail: [
              {
                path: 'models.investigator.model',
                msg: 'is not a configuration field',
              },
            ],
          }),
          { status: 400, headers: { 'content-type': 'application/json' } },
        ),
      ),
    );

    const answer = await write(
      request('/api/config', { nodeId: 'org-northwind', patch: { a: '1' } }),
    );

    expect(answer.status).toBe(400);
    const body: unknown = await answer.json();
    const reason = String(Reflect.get(Object(body), 'reason') ?? '');
    expect(reason).toContain('is not a configuration field');
  });

  it('names what was missing when it refuses a nodeless request', async () => {
    const answer = await write(request('/api/config', { nodeId: '', patch: {} }));

    expect(answer.status).toBe(400);
    const body: unknown = await answer.json();
    expect(String(Reflect.get(Object(body), 'reason') ?? '')).not.toBe('');
  });
});
