import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST as resend } from '@/app/api/resend/route';
import { POST as simulate } from '@/app/api/simulate/route';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The two transit couriers, and what each of them refuses.
 *
 * Both exist for the reason every handler under `api/` does: the credential is
 * in an HTTP-only cookie, so a browser cannot present it. Neither *decides*
 * anything, and that is the property under test. The simulation's answer has to
 * come from the function the live ingress path runs, so a matcher here would be
 * the second opinion the whole design exists to avoid; the re-send does not
 * check whether a delivery is re-sendable, because the gateway refuses one that
 * did not fail and a check repeated here could disagree with it.
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
      new Response(JSON.stringify({ rule_id: 'catch-all', outcome: 'delivered' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function bodySent(): string {
  const body = sent?.init.body;
  return typeof body === 'string' ? body : '';
}

describe('simulating a rule', () => {
  it('forwards the payload with the session’s credential', async () => {
    const answer = await simulate(
      request('/api/simulate', { source: 'alertmanager', payload: { a: 1 } }),
    );

    expect(answer.status).toBe(200);
    expect(sent?.url).toContain('/v1/transit/simulate');
    expect(new Headers(sent?.init.headers).get('authorization')).toBe('Bearer a-token');
    expect(bodySent()).toContain('alertmanager');
  });

  it('returns the deployment’s answer verbatim', async () => {
    const answer = await simulate(request('/api/simulate', { delivery_id: 'd-1' }));

    expect(await answer.json()).toEqual({ rule_id: 'catch-all', outcome: 'delivered' });
  });

  it('refuses a request with no session', async () => {
    const answer = await simulate(request('/api/simulate', { source: 'x' }, ''));

    expect(answer.status).toBe(401);
    expect(sent).toBeNull();
  });

  it('refuses a body that is not an object, rather than sending it on', async () => {
    const answer = await simulate(request('/api/simulate', 'not an object'));

    expect(answer.status).toBe(400);
    expect(sent).toBeNull();
  });

  it('reports the deployment being unreachable as a gateway failure', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('no route')));

    const answer = await simulate(request('/api/simulate', { source: 'alertmanager' }));

    expect(answer.status).toBe(502);
    expect(await answer.json()).toEqual({ reachable: false });
  });
});

describe('re-sending a delivery', () => {
  it('names the delivery in the path, encoded', async () => {
    const answer = await resend(
      request('/api/resend', { deliveryId: 'ops:concluded:1' }),
    );

    expect(answer.status).toBe(200);
    expect(sent?.url).toContain('/v1/transit/deliveries/ops%3Aconcluded%3A1/resend');
  });

  it('refuses a request with no session', async () => {
    const answer = await resend(request('/api/resend', { deliveryId: 'd' }, ''));

    expect(answer.status).toBe(401);
    expect(sent).toBeNull();
  });

  it('refuses a request that names no delivery', async () => {
    const answer = await resend(request('/api/resend', {}));

    expect(answer.status).toBe(400);
    expect(sent).toBeNull();
  });

  it('reports the deployment being unreachable as a gateway failure', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('no route')));

    const answer = await resend(request('/api/resend', { deliveryId: 'd' }));

    expect(answer.status).toBe(502);
  });
});
