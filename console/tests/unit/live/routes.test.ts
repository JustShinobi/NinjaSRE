import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SESSION_COOKIE } from '@/session/cookies';

/**
 * The three couriers this feature adds, and the one thing each refuses.
 *
 * They exist for the reason every handler under `src/app/api/` exists: the
 * credential is in an HTTP-only cookie, so a browser cannot present it to the
 * deployment. None of them decides anything about the domain — the deployment's
 * status comes back as the deployment's status, which is what makes an
 * optimistic write that the server refused revert *with the server's reason*
 * rather than with one this console made up.
 */

const CONSOLE_ORIGIN = 'http://localhost:8423';

function request(path: string, body: unknown, credential = 'tok_live'): NextRequest {
  const made = new NextRequest(`${CONSOLE_ORIGIN}${path}`, {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
  if (credential !== '') made.cookies.set(SESSION_COOKIE, credential);
  return made;
}

/** What a request carried, as the text it was sent as. */
function readBody(init: RequestInit | undefined): string {
  return typeof init?.body === 'string' ? init.body : '';
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
  vi.stubEnv('NINJASRE_CONSOLE_API_URL', 'http://127.0.0.1:8424');
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('steering a run', () => {
  it('takes over through the route the deployment serves for it, not by cancelling', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/run/route');

    const response = await POST(
      request('/api/run', { runId: 'run-3', action: 'take-over' }),
    );

    expect(response.status).toBe(200);
    const [address, init] = callsOf(fetching)[0] ?? ['', {}];
    expect(address).toBe('http://127.0.0.1:8424/v1/investigations/run-3/take-over');
    expect(new Headers(init.headers).get('authorization')).toBe('Bearer tok_live');
  });

  it('resumes, cancels and adds context through their own routes', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/run/route');

    await POST(request('/api/run', { runId: 'run-3', action: 'resume' }));
    await POST(request('/api/run', { runId: 'run-3', action: 'cancel' }));
    await POST(
      request('/api/run', {
        runId: 'run-3',
        action: 'message',
        text: 'look at node02',
      }),
    );

    const addresses = callsOf(fetching).map(([address]) => address);
    expect(addresses).toEqual([
      'http://127.0.0.1:8424/v1/investigations/run-3/resume',
      'http://127.0.0.1:8424/v1/investigations/run-3/cancel',
      'http://127.0.0.1:8424/v1/investigations/run-3/messages',
    ]);
    const last = callsOf(fetching)[2]?.[1];
    expect(readBody(last)).toContain('look at node02');
  });

  it('starts an investigation without a run to start it on', async () => {
    const fetching = answering(202, '{"run_id":"run-9"}');
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/run/route');

    const response = await POST(
      request('/api/run', { action: 'start', text: 'the primary is unreachable' }),
    );

    expect(response.status).toBe(202);
    expect(await response.json()).toMatchObject({ runId: 'run-9' });
    expect(callsOf(fetching)[0]?.[0]).toBe('http://127.0.0.1:8424/v1/investigations');
  });

  it('refuses adding context with nothing in it, and an action it does not serve', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/run/route');

    expect(
      (
        await POST(
          request('/api/run', { runId: 'run-3', action: 'message', text: '  ' }),
        )
      ).status,
    ).toBe(400);
    expect(
      (await POST(request('/api/run', { runId: 'run-3', action: 'delete-everything' })))
        .status,
    ).toBe(400);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('refuses without a session rather than reaching the deployment unauthenticated', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/run/route');

    const response = await POST(
      request('/api/run', { runId: 'run-3', action: 'cancel' }, ''),
    );

    expect(response.status).toBe(401);
    expect(callsOf(fetching)).toHaveLength(0);
  });

  it('returns the deployment’s own refusal, so a rollback can state its reason', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response('{"detail":"this run has already finished"}', { status: 409 }),
        ),
      ),
    );
    const { POST } = await import('@/app/api/run/route');

    const response = await POST(
      request('/api/run', { runId: 'run-3', action: 'cancel' }),
    );

    expect(response.status).toBe(409);
    expect(await response.json()).toMatchObject({
      applied: false,
      reason: 'this run has already finished',
    });
  });

  it('says a deployment it cannot reach is unreachable rather than refusing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('connection refused'))),
    );
    const { POST } = await import('@/app/api/run/route');

    const response = await POST(
      request('/api/run', { runId: 'run-3', action: 'cancel' }),
    );

    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ reachable: false });
  });
});

describe('answering an agent’s question', () => {
  it('answers the interaction the question belongs to, and resumes the run', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/answer/route');

    const response = await POST(
      request('/api/answer', { interactionId: 'int-1', text: 'the datastore' }),
    );

    expect(response.status).toBe(200);
    const [address, init] = callsOf(fetching)[0] ?? ['', {}];
    expect(address).toBe('http://127.0.0.1:8424/v1/interactions/int-1/answer');
    expect(readBody(init)).toContain('the datastore');
  });

  it('refuses an empty answer, because an empty answer resumes a run with nothing', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/answer/route');

    const response = await POST(
      request('/api/answer', { interactionId: 'int-1', text: '' }),
    );

    expect(response.status).toBe(400);
    expect(callsOf(fetching)).toHaveLength(0);
  });
});

describe('the stream courier', () => {
  it('turns the cursor into the header the deployment reads, and pipes the body through', async () => {
    const fetching = vi.fn(() =>
      Promise.resolve(
        new Response('id: run-3:1\ndata: {}\n\n', {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        }),
      ),
    );
    vi.stubGlobal('fetch', fetching);
    const { GET } = await import('@/app/api/stream/[runId]/route');

    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/stream/run-3?cursor=run-3%3A1`);
    made.cookies.set(SESSION_COOKIE, 'tok_live');
    const response = await GET(made, { params: Promise.resolve({ runId: 'run-3' }) });

    expect(response.status).toBe(200);
    expect(response.headers.get('content-type')).toBe('text/event-stream');
    const [address, init] = callsOf(fetching)[0] ?? ['', {}];
    expect(address).toBe('http://127.0.0.1:8424/v1/investigations/run-3/stream');
    expect(new Headers(init.headers).get('last-event-id')).toBe('run-3:1');
    // Byte for byte: a courier that renumbered events would be a second opinion
    // about the order a run happened in.
    expect(await response.text()).toBe('id: run-3:1\ndata: {}\n\n');
  });

  it('presents no cursor at all on a first connection', async () => {
    const fetching = vi.fn(() =>
      Promise.resolve(
        new Response('', {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        }),
      ),
    );
    vi.stubGlobal('fetch', fetching);
    const { GET } = await import('@/app/api/stream/[runId]/route');

    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/stream/run-3`);
    made.cookies.set(SESSION_COOKIE, 'tok_live');
    await GET(made, { params: Promise.resolve({ runId: 'run-3' }) });

    expect(new Headers(callsOf(fetching)[0]?.[1].headers).has('last-event-id')).toBe(
      false,
    );
  });

  it('passes a refusal through as a refusal, so the session can end once', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response('', { status: 401 }))),
    );
    const { GET } = await import('@/app/api/stream/[runId]/route');

    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/stream/run-3`);
    made.cookies.set(SESSION_COOKIE, 'tok_live');
    const response = await GET(made, { params: Promise.resolve({ runId: 'run-3' }) });

    expect(response.status).toBe(401);
  });

  it('refuses without a session', async () => {
    const made = new NextRequest(`${CONSOLE_ORIGIN}/api/stream/run-3`);
    const response = await GET_of(made);

    expect(response.status).toBe(401);
  });
});

async function GET_of(made: NextRequest): Promise<Response> {
  const { GET } = await import('@/app/api/stream/[runId]/route');
  return GET(made, { params: Promise.resolve({ runId: 'run-3' }) });
}

describe('the browser reading a stream', () => {
  function streaming(chunks: readonly string[]): Response {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder();
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    });
    return new Response(body, {
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
    });
  }

  it('reads whole frames out of chunks that do not line up with them', async () => {
    const { fetchStreamSource } = await import('@/live/transport');
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          streaming([
            ': heartbeat\n\nid: run-3:0\ndata: {"run_id":"run-3",',
            '"sequence":0}\n\n',
          ]),
        ),
      ),
    );
    const seen: string[] = [];
    let opened = 0;
    const errors: number[] = [];

    const handle = fetchStreamSource.open('/api/stream/run-3', {
      onOpen: () => {
        opened += 1;
      },
      onFrame: (data) => seen.push(data),
      onError: (status) => errors.push(status),
    });
    await vi.waitFor(() => {
      expect(errors).toHaveLength(1);
    });
    handle.close();

    expect(opened).toBe(1);
    // The keep-alive is not an event, and the frame split across two chunks is.
    expect(seen).toEqual(['{"run_id":"run-3","sequence":0}']);
    // A stream that ends is a stream to reopen, not a run that is over.
    expect(errors).toEqual([0]);
  });

  it('reports a refusal as its status and a failure to connect as nought', async () => {
    const { fetchStreamSource } = await import('@/live/transport');
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('no route to host'))),
    );
    const errors: number[] = [];

    const handle = fetchStreamSource.open('/api/stream/run-3', {
      onOpen: () => undefined,
      onFrame: () => undefined,
      onError: (status) => errors.push(status),
    });
    await vi.waitFor(() => {
      expect(errors).toEqual([0]);
    });
    handle.close();
  });

  it('says nothing more once the screen has closed it', async () => {
    const { fetchStreamSource } = await import('@/live/transport');
    let release = (): void => undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            release = (): void => {
              resolve(streaming(['data: {}\n\n']));
            };
          }),
      ),
    );
    const errors: number[] = [];

    const handle = fetchStreamSource.open('/api/stream/run-3', {
      onOpen: () => undefined,
      onFrame: () => undefined,
      onError: (status) => errors.push(status),
    });
    handle.close();
    release();
    await Promise.resolve();

    expect(errors).toEqual([]);
  });
});

describe('the answer courier at its edges', () => {
  it('refuses without a session, and says a deployment it cannot reach is unreachable', async () => {
    const { POST } = await import('@/app/api/answer/route');

    vi.stubGlobal('fetch', answering(200));
    expect(
      (await POST(request('/api/answer', { interactionId: 'i', text: 'x' }, '')))
        .status,
    ).toBe(401);

    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('connection refused'))),
    );
    const unreachable = await POST(
      request('/api/answer', { interactionId: 'i', text: 'x' }),
    );
    expect(unreachable.status).toBe(502);
    expect(await unreachable.json()).toMatchObject({ reachable: false });
  });

  it('carries a chosen option beside the words when one was chosen', async () => {
    const fetching = answering(200);
    vi.stubGlobal('fetch', fetching);
    const { POST } = await import('@/app/api/answer/route');

    await POST(
      request('/api/answer', {
        interactionId: 'i',
        text: 'the datastore',
        option: 'the datastore',
      }),
    );

    expect(readBody(callsOf(fetching)[0]?.[1])).toContain('selected_option');
  });

  it('states the deployment’s reason when it refuses an answer', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: 'this interaction is closed' }), {
            status: 409,
          }),
        ),
      ),
    );
    const { POST } = await import('@/app/api/answer/route');

    const response = await POST(
      request('/api/answer', { interactionId: 'i', text: 'x' }),
    );

    expect(await response.json()).toMatchObject({
      reason: 'this interaction is closed',
    });
  });
});
