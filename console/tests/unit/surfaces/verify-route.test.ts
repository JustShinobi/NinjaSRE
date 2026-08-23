import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/verify/route';
import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The verify courier, and the one decision in it that made "Test again" useless.
 *
 * There are two questions behind this control and they are not the same. The
 * cheap one asks the deployment's own vault whether a credential is stored; the
 * expensive one asks the vendor. The courier used to ask the vendor *only when
 * the cheap answer had already come back positive* — which is exactly backwards
 * for a self-hosted vendor that ships no authentication, because for those the
 * cheap answer carries no information at all and the vendor's is the only one
 * worth having.
 *
 * So the report is now asked for on every integration the gateway answered for,
 * and what the vendor said is what decides the word on the chip.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';

function request(body: unknown, credential = 'tok_console'): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}/api/verify`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (credential !== '') made.cookies.set(SESSION_COOKIE, credential);
  return made;
}

/** Answers the shallow verify with `verdict`, and the deep report with `report`. */
function answering(
  verdict: { status: number; body: unknown },
  report: { status: number; body: unknown },
): typeof fetch {
  return vi.fn((url: unknown) =>
    Promise.resolve(
      String(url).endsWith('/verify/report')
        ? new Response(JSON.stringify(report.body), { status: report.status })
        : new Response(JSON.stringify(verdict.body), { status: verdict.status }),
    ),
  );
}

function urlsOf(fetching: typeof fetch): string[] {
  return (fetching as unknown as ReturnType<typeof vi.fn>).mock.calls.map((call) =>
    String((call as unknown[])[0]),
  );
}

/** The shape the gateway's report route actually serves: a named wrapper. */
function wrapped(integration: string, report: Record<string, unknown>): unknown {
  return { integration, report: { integration, ...report } };
}

const REACHABLE = wrapped('alertmanager', {
  ok: true,
  degraded: false,
  degradations: [],
  connectivity: { reachable: true, detail: 'Alertmanager answered.', status_code: 200 },
  permissions: [],
  missing_permissions: [],
});

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('asking the vendor', () => {
  it('asks for the report even when the credential state is not usable', async () => {
    // The whole defect. Alertmanager stores no credential, so the cheap answer
    // is "nothing is stored" — and the vendor is answering perfectly well.
    const fetching = answering(
      {
        status: 200,
        body: { integration: 'alertmanager', state: 'missing', usable: false },
      },
      { status: 200, body: REACHABLE },
    );
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(request({ kind: 'integration', name: 'alertmanager' }));
    const body: unknown = await answer.json();

    expect(urlsOf(fetching).some((url) => url.endsWith('/verify/report'))).toBe(true);
    expect(Reflect.get(Object(body), 'verified')).toBe(true);
    expect(Reflect.get(Object(body), 'reason')).toBe('Alertmanager answered.');
  });

  it('never asks a provider for one, because there is no such route', async () => {
    const fetching = answering(
      { status: 200, body: { verified: true, detail: 'ready' } },
      { status: 404, body: {} },
    );
    vi.stubGlobal('fetch', fetching);

    await POST(request({ kind: 'provider', name: 'google_gemini' }));

    expect(urlsOf(fetching).some((url) => url.endsWith('/verify/report'))).toBe(false);
  });

  it('keeps working when the deployment composed no deep verifier', async () => {
    // A 404 here is a working deployment saying it cannot reach vendors, not a
    // failure — the credential state it did answer is still worth showing.
    const fetching = answering(
      {
        status: 200,
        body: { integration: 'redis', state: 'configured', usable: true },
      },
      { status: 404, body: { detail: 'no deep verifier is composed' } },
    );
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(request({ kind: 'integration', name: 'redis' }));
    const body: unknown = await answer.json();

    expect(answer.status).toBe(200);
    expect(Reflect.get(Object(body), 'verified')).toBe(true);
  });

  it('lets the vendor overrule a credential the vault was happy with', async () => {
    const fetching = answering(
      {
        status: 200,
        body: { integration: 'grafana', state: 'configured', usable: true },
      },
      {
        status: 200,
        body: wrapped('grafana', {
          ok: false,
          degraded: false,
          degradations: [],
          connectivity: {
            reachable: false,
            detail: '401 Unauthorized',
            status_code: 401,
          },
          permissions: [],
          missing_permissions: [],
        }),
      },
    );
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(request({ kind: 'integration', name: 'grafana' }));
    const body: unknown = await answer.json();

    expect(Reflect.get(Object(body), 'verified')).toBe(false);
    expect(Reflect.get(Object(body), 'reason')).toBe('401 Unauthorized');
  });

  it('carries a degradation without calling the vendor a failure', async () => {
    const fetching = answering(
      {
        status: 200,
        body: { integration: 'prometheus', state: 'configured', usable: true },
      },
      {
        status: 200,
        body: wrapped('prometheus', {
          ok: true,
          degraded: true,
          degradations: ['its clock is 42.0s from the platform’s'],
          connectivity: {
            reachable: true,
            detail: 'Prometheus answered.',
            status_code: 200,
          },
          permissions: [],
          missing_permissions: [],
        }),
      },
    );
    vi.stubGlobal('fetch', fetching);

    const answer = await POST(request({ kind: 'integration', name: 'prometheus' }));
    const body: unknown = await answer.json();

    expect(Reflect.get(Object(body), 'verified')).toBe(true);
    expect(Reflect.get(Object(body), 'degraded')).toBe(true);
    expect(Reflect.get(Object(body), 'findings')).toEqual([
      'its clock is 42.0s from the platform’s',
    ]);
  });
});
