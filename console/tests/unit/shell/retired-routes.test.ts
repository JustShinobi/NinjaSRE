import { afterEach, describe, expect, it, vi } from 'vitest';

/**
 * The addresses this console retired, and what each of them answers with.
 *
 * A retired address is not a dead one. `/investigations` is the name people
 * remember and share in a link, `/setup` is the word the product's own
 * vocabulary uses for the guided first run, and `/administration` is where a
 * bookmark from before the hybrid navigation lands. All three forward rather
 * than ending in "there is no such page", and every query parameter rides
 * along.
 *
 * Each of these had the same shape of gap: `legacyRedirectHref(...) ?? '/x'`,
 * with only the left half ever exercised. The fallback is the branch that runs
 * for a bare address with no query at all — which is the one a person typing
 * from memory produces, and so the likeliest of the two to be taken.
 */

const redirected = vi.hoisted(() => ({ to: '' }));

vi.mock('next/navigation', () => ({
  redirect: (href: string) => {
    redirected.to = href;
    // The real one throws to unwind the render; nothing here depends on that,
    // and a throw would only make each assertion a try/catch.
    return undefined;
  },
}));

afterEach(() => {
  redirected.to = '';
  vi.resetModules();
});

/** Render one route module with `params` as its query, and report where it sent. */
async function follow(
  module: string,
  params: Readonly<Record<string, string>> = {},
): Promise<string> {
  const route: { default: (props: unknown) => Promise<unknown> } = await import(module);
  await route.default({ searchParams: Promise.resolve(params) });
  return redirected.to;
}

describe('an address the navigation retired still answers', () => {
  it('sends /investigations to the area it became', async () => {
    expect(await follow('@/app/(shell)/investigations/page')).toBe('/runs');
  });

  it('carries a query across with it', async () => {
    expect(await follow('@/app/(shell)/investigations/page', { state: 'failed' })).toBe(
      '/runs?state=failed',
    );
  });

  it('sends /setup to the guided first run', async () => {
    expect(await follow('@/app/(shell)/setup/page')).toBe('/first-run');
  });

  it('sends /administration to the page People became', async () => {
    expect(await follow('@/app/(shell)/administration/page')).toBe(
      '/settings/members-roles',
    );
  });

  it('sends the audit half of /administration to its own page', async () => {
    expect(await follow('@/app/(shell)/administration/page', { tab: 'audit' })).toBe(
      '/settings/audit-log',
    );
  });

  /**
   * The one retired address that is not entirely retired.
   *
   * Continuous observation has no Settings page yet — none of the nine the
   * subnav lists replaces it — so this tab keeps rendering rather than
   * forwarding, and every other variant of the address goes to whichever page
   * took its subject over.
   */
  it('sends the intake half of /signals to Alert intake', async () => {
    expect(await follow('@/app/(shell)/signals/page', { tab: 'intake' })).toBe(
      '/settings/alert-intake',
    );
  });
});
