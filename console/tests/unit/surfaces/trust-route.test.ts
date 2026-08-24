import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/trust/route';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The certificate trust courier: forwards a declaration to
 * `PUT /v1/integrations/{name}/trust` and decides nothing about it.
 *
 * The permission gate itself — `integration.trust_unverified` for the
 * unverified form, `integration.manage` for every form — is enforced by the
 * gateway, proven at `tests/unit/gateway/http/test_certificate_trust_write.py`
 * (`test_accepting_unverified_without_the_dedicated_permission_is_refused`,
 * which asserts the raised `PermissionDenied` names the permission). What
 * this file proves is the courier's own half of that guarantee: a refusal
 * the gateway sends crosses back with the gateway's own wording, intact and
 * unparaphrased, which is the sentence FR-046 requires the console to show.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';

function request(body: unknown, credential = 'tok_console'): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/trust`, {
    method: 'POST',
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

    const answer = await POST(request({ integration: 'proxmox' }, ''));

    expect(answer.status).toBe(401);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('refuses a body that names no integration', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(request({ fingerprints: ['AA:BB'] }));

    expect(answer.status).toBe(400);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('refuses an integration named with an empty string', async () => {
    vi.stubGlobal('fetch', answering(200));

    expect((await POST(request({ integration: '' }))).status).toBe(400);
  });

  it('refuses a body that is not JSON at all', async () => {
    vi.stubGlobal('fetch', answering(200));
    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/trust`, {
      method: 'POST',
      body: 'not json',
      headers: { 'content-type': 'application/json' },
    });
    made.cookies.set(SESSION_COOKIE, 'tok_console');

    expect((await POST(made)).status).toBe(400);
  });
});

describe('what crosses to the gateway', () => {
  it('reaches the trust route of the named integration, by PUT', async () => {
    const fetching = answering(200, '{"anchor":"pinned-fingerprint"}');
    vi.stubGlobal('fetch', fetching);

    await POST(request({ integration: 'proxmox', fingerprints: ['AA:BB'] }));

    const [address, init] = callsOf(fetching)[0] ?? ['', {}];
    expect(address).toContain('/v1/integrations/proxmox/trust');
    expect(init.method).toBe('PUT');
  });

  it('drops a blank line and a blank fingerprint, sending a clean set', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    await POST(
      request({ integration: 'proxmox', fingerprints: ['AA:BB', '', '  ', 42, null] }),
    );

    const [, init] = callsOf(fetching)[0] ?? ['', {}];
    const sent: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    expect(Reflect.get(Object(sent), 'fingerprints')).toEqual(['AA:BB']);
  });

  it('renames the camelCase fields the browser sends to the ones the gateway declares', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    await POST(
      request({
        integration: 'proxmox',
        certificatePem: '-----BEGIN CERTIFICATE-----',
        unverifiedReason: 'lab link with no DNS',
      }),
    );

    const [, init] = callsOf(fetching)[0] ?? ['', {}];
    const sent: unknown = JSON.parse(typeof init.body === 'string' ? init.body : '{}');
    expect(Reflect.get(Object(sent), 'certificate_pem')).toBe(
      '-----BEGIN CERTIFICATE-----',
    );
    expect(Reflect.get(Object(sent), 'unverified_reason')).toBe('lab link with no DNS');
  });

  it('never puts the certificate or the reason in the address', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);

    await POST(
      request({
        integration: 'proxmox',
        certificatePem: '-----BEGIN CERTIFICATE-----\nsecret-shaped-noise',
        unverifiedReason: 'lab link with no DNS',
      }),
    );

    const [address] = callsOf(fetching)[0] ?? [''];
    expect(address).not.toContain('secret-shaped-noise');
    expect(address).not.toContain('lab link');
  });

  it('forwards what the gateway said this declaration now covers', async () => {
    vi.stubGlobal(
      'fetch',
      answering(
        200,
        '{"integration":"proxmox","anchor":"pinned-fingerprint","addresses":["10.20.20.9"],"describes":"verifying against the pinned fingerprint AA:BB:CC…"}',
      ),
    );

    const answer = await POST(
      request({ integration: 'proxmox', fingerprints: ['AA:BB:CC'] }),
    );
    const body: unknown = await answer.json();

    expect(answer.status).toBe(200);
    expect(body).toMatchObject({
      ok: true,
      reachable: true,
      anchor: 'pinned-fingerprint',
      addresses: ['10.20.20.9'],
    });
  });

  it('forwards a permission refusal in the gateway’s own words, naming the permission', async () => {
    const message =
      "This action needs 'integration.trust_unverified' in this organisation. " +
      "The 'ADMIN' role grants it.";
    vi.stubGlobal(
      'fetch',
      answering(
        403,
        JSON.stringify({
          error: { type: 'permission_denied', message, correlation_id: 'c-1' },
        }),
      ),
    );

    const answer = await POST(
      request({ integration: 'proxmox', unverifiedReason: 'lab link with no DNS' }),
    );
    const body: unknown = await answer.json();

    expect(answer.status).toBe(403);
    expect(body).toMatchObject({ ok: false, reason: message });
    expect(String(Reflect.get(Object(body), 'reason'))).toContain(
      'integration.trust_unverified',
    );
  });

  it('forwards a validation refusal the same way', async () => {
    vi.stubGlobal(
      'fetch',
      answering(
        400,
        JSON.stringify({
          error: {
            type: 'bad_request',
            message: 'accepting an unverified certificate needs a reason.',
            correlation_id: 'c-2',
          },
        }),
      ),
    );

    const answer = await POST(
      request({ integration: 'proxmox', unverifiedReason: '   ' }),
    );
    const body: unknown = await answer.json();

    expect(answer.status).toBe(400);
    expect(body).toMatchObject({
      ok: false,
      reason: 'accepting an unverified certificate needs a reason.',
    });
  });

  it('falls back to a `detail` body for a shape the envelope did not produce', async () => {
    vi.stubGlobal('fetch', answering(422, '{"detail":"site is required"}'));

    const answer = await POST(request({ integration: 'proxmox' }));
    const body: unknown = await answer.json();

    expect(body).toMatchObject({ ok: false, reason: 'site is required' });
  });

  it('says nothing of its own when the refusal carries no words', async () => {
    vi.stubGlobal('fetch', answering(500, '{"error":{"message":""}}'));

    const body: unknown = await (
      await POST(request({ integration: 'proxmox' }))
    ).json();

    expect(body).toMatchObject({ ok: false, reason: '' });
  });

  it('says the deployment is unreachable, not that it refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('connect ECONNREFUSED'))),
    );

    const answer = await POST(request({ integration: 'proxmox', fingerprints: [] }));
    const body: unknown = await answer.json();

    expect(answer.status).toBe(502);
    expect(body).toMatchObject({ ok: false, reachable: false });
  });
});
