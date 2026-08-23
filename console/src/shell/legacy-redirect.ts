import type { SearchParams } from '@/surfaces/context';
import { legacyRouteTarget } from './routes';

/**
 * Where a retired route's request redirects to, or `undefined` when the
 * table names no destination for it.
 *
 * Every query parameter but `tab` rides along: `tab` was how the old screen
 * picked which of its own panes to show, a question the new address answers
 * by being a different address entirely, while a filter like `actor` or
 * `since` still means the same thing on the page it lands on and dropping it
 * would silently narrow what a bookmarked or shared link shows.
 */
export function legacyRedirectHref(
  path: string,
  params: SearchParams,
): string | undefined {
  const rawTab = params.tab;
  const tab = typeof rawTab === 'string' ? rawTab : null;
  const target = legacyRouteTarget(path, tab);
  if (target === undefined) return undefined;

  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (name === 'tab') continue;
    if (typeof value === 'string') {
      search.set(name, value);
    } else if (Array.isArray(value) && typeof value[0] === 'string') {
      search.set(name, value[0]);
    }
  }
  const query = search.toString();
  return query === '' ? target : `${target}?${query}`;
}
