import { describe, expect, it } from 'vitest';

import { resolveCta } from '@/design/empty-state';

/**
 * The CTA contract, held against the one list of what routes exist.
 *
 * An empty state's action is a destination and a verb. The verb was already
 * required — `EmptyState` itself refuses to render one with a blank label —
 * so what is missing is the destination half: nothing stopped a screen from
 * writing `href: '/configuration'` for a route this console renamed or
 * dropped last week, and the mistake would not surface until somebody
 * clicked it. `resolveCta` is the one place a screen builds that destination,
 * and it is checked against `routes.ts` — the same manifest the sign-in
 * guard, the role matrix and the palette already hold everything else
 * against — rather than typed as a bare string a reviewer has to trust.
 */

describe('resolving a CTA target', () => {
  it('turns a route the manifest knows into an href, unembellished', () => {
    const resolved = resolveCta({ route: '/integrations' });

    expect(resolved.href).toBe('/integrations');
    expect(resolved.permission).toBe('integration.manage');
  });

  it('carries an anchor as a fragment', () => {
    const resolved = resolveCta({ route: '/agent', anchor: 'models' });

    expect(resolved.href).toBe('/agent#models');
  });

  it('carries a filter as a query string', () => {
    const resolved = resolveCta({
      route: '/integrations',
      query: { category: 'communication' },
    });

    expect(resolved.href).toBe('/integrations?category=communication');
  });

  it('combines a filter and an anchor in one address', () => {
    const resolved = resolveCta({
      route: '/signals',
      anchor: 'destinations',
      query: { tab: 'destinations' },
    });

    expect(resolved.href).toBe('/signals?tab=destinations#destinations');
  });

  it('refuses a route this console does not serve, rather than building a dead link', () => {
    expect(() => resolveCta({ route: '/configuration/advanced' })).toThrow(
      /is not a route this console serves/,
    );
  });

  it('carries the permission the destination requires, so a caller can hide the CTA', () => {
    const resolved = resolveCta({ route: '/autonomy' });

    expect(resolved.permission).toBe('config.write');
  });
});
