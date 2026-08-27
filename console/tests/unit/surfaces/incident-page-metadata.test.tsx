import { describe, expect, it, vi } from 'vitest';

/**
 * The one branch `tests/unit/surfaces/incident-detail.test.tsx` cannot
 * reach without disturbing the session cookie every other test in that file
 * relies on: a request that carries no session at all. A separate file,
 * with its own `next/headers` mock, is what keeps the two from fighting
 * over the same mocked module.
 */
vi.mock('next/headers', () => ({
  cookies: () => Promise.resolve({ get: () => undefined }),
  headers: () => Promise.resolve({ get: () => null }),
}));

describe('the incident route file’s generateMetadata, with no session', () => {
  it('falls back to the deployment name rather than reading anything', async () => {
    vi.stubEnv('NINJASRE_CONSOLE_DEPLOYMENT', 'HAL9000');
    const PageModule = await import('@/app/(shell)/incidents/[incidentId]/page');

    const metadata = await PageModule.generateMetadata({
      params: Promise.resolve({ incidentId: 'inc-no-session' }),
    });

    expect(metadata.title).toBe('HAL9000');
    vi.unstubAllEnvs();
  });
});
