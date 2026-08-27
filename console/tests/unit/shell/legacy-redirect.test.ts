import { describe, expect, it } from 'vitest';

import { legacyRedirectHref } from '@/shell/legacy-redirect';

/**
 * What survives when an address a person bookmarked stops existing.
 *
 * The rule the redirect encodes is not "keep the query string": it is that a
 * parameter which still means something on the page being landed on rides
 * along, and the one that only meant something to the old screen does not.
 * `tab` chose between panes of a screen that no longer has panes; `actor` and
 * `since` narrow a list, and dropping them would quietly widen what somebody
 * shared a link to.
 */

describe('legacyRedirectHref', () => {
  it('answers nothing for a path the table does not name', () => {
    expect(legacyRedirectHref('/nowhere-in-particular', {})).toBeUndefined();
  });

  it('redirects a retired address with no parameters to the bare destination', () => {
    const found = legacyRedirectHref('/investigations', {});
    expect(found).toBe('/runs');
  });

  it('drops the tab that chose between panes of a screen that has none', () => {
    expect(legacyRedirectHref('/investigations', { tab: 'running' })).toBe('/runs');
  });

  it('carries a filter that still means the same thing on the new page', () => {
    expect(legacyRedirectHref('/investigations', { actor: 'ada' })).toBe(
      '/runs?actor=ada',
    );
  });

  it('carries the first value when a parameter arrived more than once', () => {
    expect(legacyRedirectHref('/investigations', { actor: ['ada', 'grace'] })).toBe(
      '/runs?actor=ada',
    );
  });

  it('ignores a repeated parameter whose first value is not a string', () => {
    expect(legacyRedirectHref('/investigations', { actor: [] })).toBe('/runs');
  });

  it('ignores a tab that arrived as a list rather than a word', () => {
    // Not a string, so it names no pane — and it is dropped for being `tab`
    // regardless, which is what keeps the two rules from disagreeing.
    expect(legacyRedirectHref('/investigations', { tab: ['running'] })).toBe('/runs');
  });

  it('carries several filters at once', () => {
    const found = legacyRedirectHref('/investigations', {
      actor: 'ada',
      since: 'yesterday',
      tab: 'running',
    });
    expect(found?.startsWith('/runs?')).toBe(true);
    expect(found).toContain('actor=ada');
    expect(found).toContain('since=yesterday');
    expect(found).not.toContain('tab=');
  });
});
