import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError, apiOrigin, read } from '@/lib/api';

function answering(status: number, body: unknown): typeof fetch {
  return vi.fn(() =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        status,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('the only way out of the console', () => {
  it('reads the gateway address at request time rather than baking it in', () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', 'http://localhost:8420');
    expect(apiOrigin()).toBe('http://localhost:8420');
  });

  it('falls back to a same-origin request when nothing configures an address', () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    expect(apiOrigin()).toBe('');
  });

  it('returns the body the gateway answered with', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', 'http://localhost:8420');
    vi.stubGlobal('fetch', answering(200, { runs: [{ run_id: 'run-0001' }] }));

    const body = await read('/v1/runs');

    expect(body).toEqual({ runs: [{ run_id: 'run-0001' }] });
  });

  it('sends the request to the configured origin', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', 'http://localhost:8420');
    const fetched = answering(200, { runs: [] });
    vi.stubGlobal('fetch', fetched);

    await read('/v1/runs');

    const [url, options] = vi.mocked(fetched).mock.calls[0] ?? [];
    expect(url).toBe('http://localhost:8420/v1/runs');
    expect(new Headers(options?.headers).get('accept')).toBe('application/json');
  });

  it('raises with the status rather than returning an empty body', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_API_URL', '');
    vi.stubGlobal('fetch', answering(403, { detail: 'no' }));

    await expect(read('/v1/runs')).rejects.toBeInstanceOf(ApiError);
    await expect(read('/v1/runs')).rejects.toMatchObject({ status: 403 });
  });
});
