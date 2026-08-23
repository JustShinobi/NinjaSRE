import { describe, expect, it } from 'vitest';

import { routeParam } from '@/shell/route-params';

/**
 * The one place a dynamic route parameter is decoded — exactly once, before
 * any page logic sees it — and the invariant this console holds every
 * dynamic route to: encoded once by `bind()` (`src/lib/api.ts`), decoded
 * once here.
 */
describe('routeParam: the edge decode every dynamic route parameter crosses', () => {
  it('decodes a parameter carrying reserved characters', () => {
    const raw = encodeURIComponent('alert:alertmanager:abc123@2026-08-22T23:43:23+00:00');

    expect(routeParam(raw)).toBe('alert:alertmanager:abc123@2026-08-22T23:43:23+00:00');
  });

  it('leaves a parameter with no reserved characters unchanged', () => {
    expect(routeParam('inc_9f2c4a1b8e7d3506')).toBe('inc_9f2c4a1b8e7d3506');
  });

  it('decodes an encoded slash rather than letting it become a segment separator', () => {
    const raw = encodeURIComponent('proxmox/node/pve02');

    expect(routeParam(raw)).toBe('proxmox/node/pve02');
  });

  it('returns the original value rather than throwing on a lone "%"', () => {
    expect(routeParam('100%')).toBe('100%');
  });

  it('returns the original value on a malformed escape sequence', () => {
    expect(routeParam('%zz')).toBe('%zz');
  });

  it("round-trips through bind()'s own encodeURIComponent exactly once", () => {
    const original = 'alert:alertmanager:9f2c@2026-08-22T23:43:23.303208+00:00';
    const asRouterWouldDeliverIt = encodeURIComponent(original);

    const decoded = routeParam(asRouterWouldDeliverIt);
    const reEncoded = encodeURIComponent(decoded);

    expect(decoded).toBe(original);
    expect(reEncoded).toBe(asRouterWouldDeliverIt);
  });
});
