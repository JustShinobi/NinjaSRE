import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';
import { DeliveryToken } from '@/surfaces/ingress';

/**
 * The credential an operator pastes into their alert router.
 *
 * Two halves, and the interesting assertions are about what neither of them
 * does. The component holds the value in state and nowhere a reload could
 * recover it from, because there is no route that reads a token back. The
 * courier forwards one request and refuses to ask for any scope but the
 * delivery one — the gateway would refuse to exceed the owner's permissions
 * anyway, and refusing to *ask* is the difference between a boundary and a
 * hope.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';
const API = 'http://127.0.0.1:8424';
const SECRET = 'ninja_delivery_9d41c7a2b6e30f58';

const LABELS = {
  issue: 'Issue a delivery token',
  issuing: 'Issuing…',
  shownOnce: 'Copy it now.',
  failed: 'The deployment refused to issue it.',
  unreachable: 'The deployment could not be reached.',
};

interface Sent {
  readonly url: string;
  readonly init: RequestInit;
}

/** What was sent as a body, as text. Every one of these is a JSON string. */
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

describe('the delivery token control', () => {
  it('draws nothing but a button until somebody asks for one', () => {
    render(<DeliveryToken permission="webhook.deliver" labels={LABELS} />);

    expect(screen.queryByTestId('delivery-secret')).toBeNull();
    expect(screen.getByRole('button')).toHaveTextContent(LABELS.issue);
  });

  it('shows the secret once, with the sentence that says so', async () => {
    vi.stubGlobal('fetch', answering(201, { ok: true, secret: SECRET }));

    render(<DeliveryToken permission="webhook.deliver" labels={LABELS} />);
    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByTestId('delivery-secret')).toHaveTextContent(SECRET);
    });
    expect(screen.getByText(LABELS.shownOnce)).toBeInTheDocument();
  });

  it('asks for the scope the deployment named and nothing else', async () => {
    vi.stubGlobal('fetch', answering(201, { ok: true, secret: SECRET }));

    render(<DeliveryToken permission="webhook.deliver" labels={LABELS} />);
    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(sent[0]?.url).toBe('/api/delivery-token');
    expect(bodyOf(sent[0])).toContain('webhook.deliver');
  });

  it('says the deployment refused rather than showing an empty credential', async () => {
    vi.stubGlobal('fetch', answering(403, { ok: false }));

    render(<DeliveryToken permission="webhook.deliver" labels={LABELS} />);
    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByTestId('delivery-token-failure')).toHaveTextContent(
        LABELS.failed,
      );
    });
    expect(screen.queryByTestId('delivery-secret')).toBeNull();
  });

  it('distinguishes a refusal from a deployment nobody could reach', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    render(<DeliveryToken permission="webhook.deliver" labels={LABELS} />);
    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(screen.getByTestId('delivery-token-failure')).toHaveTextContent(
        LABELS.unreachable,
      );
    });
  });

  it('shows nothing when the deployment answered without a secret in it', async () => {
    vi.stubGlobal('fetch', answering(201, { ok: true }));

    render(<DeliveryToken permission="webhook.deliver" labels={LABELS} />);
    await userEvent.click(screen.getByRole('button'));

    await waitFor(() => {
      expect(sent).toHaveLength(1);
    });
    expect(screen.queryByTestId('delivery-secret')).toBeNull();
  });
});

describe('the delivery token courier', () => {
  function request(body: unknown, withSession = true): NextRequest {
    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/delivery-token`, {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'content-type': 'application/json' },
    });
    if (withSession) made.cookies.set(SESSION_COOKIE, 'tok_session');
    return made;
  }

  async function post(body: unknown, session = true): Promise<Response> {
    const { POST } = await import('@/app/api/delivery-token/route');
    return POST(request(body, session));
  }

  it('mints one token, scoped to the delivery permission alone', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: SECRET, token: { scopes: [] } }));

    const answer = await post({ permission: 'webhook.deliver' });

    expect(answer.status).toBe(201);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.url).toBe(`${API}/identity/tokens`);
    expect(bodyOf(sent[0])).toContain('webhook.deliver');
    expect(await answer.json()).toMatchObject({ ok: true, secret: SECRET });
  });

  it('presents the session credential the browser cannot present itself', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: SECRET }));

    await post({ permission: 'webhook.deliver' });

    const headers = new Headers(sent[0]?.init.headers);
    expect(headers.get('authorization')).toBe('Bearer tok_session');
  });

  it('refuses to ask for any other scope', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: SECRET }));

    const answer = await post({ permission: 'org.manage' });

    expect(answer.status).toBe(400);
    expect(sent).toHaveLength(0);
  });

  it('refuses without a session rather than asking unauthenticated', async () => {
    vi.stubGlobal('fetch', answering(201, { secret: SECRET }));

    const answer = await post({ permission: 'webhook.deliver' }, false);

    expect(answer.status).toBe(401);
    expect(sent).toHaveLength(0);
  });

  it('says the deployment was unreachable rather than that it refused', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('fetch failed'))),
    );

    const answer = await post({ permission: 'webhook.deliver' });

    expect(answer.status).toBe(502);
    expect(await answer.json()).toMatchObject({ ok: false, reachable: false });
  });

  it('carries no secret across when the deployment sent none', async () => {
    vi.stubGlobal('fetch', answering(201, {}));

    const answer = await post({ permission: 'webhook.deliver' });

    expect(await answer.json()).toMatchObject({ secret: '' });
  });
});
