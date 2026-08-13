import { SEARCH_ENDPOINT } from './search-endpoint';
import { NOTHING, type Found, type SearchResults } from './search';

/**
 * Asking the courier what answers to a query, from the browser.
 *
 * A courier rather than three `fetch`es straight at the deployment: the session
 * credential is an HTTP-only cookie the browser cannot read and will not send
 * to another host, which is the same reason every other write on this surface
 * goes through one.
 *
 * Every failure resolves to nothing found. A palette that showed an error where
 * its results go would be taking away the navigation half, which still works —
 * and the operator typing into it at that moment is usually the one whose
 * deployment is already having a bad day.
 */

/** One record of the courier's answer, as a `Found` or as nothing. */
function foundOf(record: unknown): Found | null {
  const group: unknown = Reflect.get(Object(record), 'group');
  if (group !== 'resources' && group !== 'incidents' && group !== 'runs') return null;
  const id: unknown = Reflect.get(Object(record), 'id');
  const href: unknown = Reflect.get(Object(record), 'href');
  const label: unknown = Reflect.get(Object(record), 'label');
  const hint: unknown = Reflect.get(Object(record), 'hint');
  if (typeof id !== 'string' || typeof href !== 'string' || typeof label !== 'string') {
    return null;
  }
  return { id, group, label, href, hint: typeof hint === 'string' ? hint : '' };
}

/** What the deployment says answers to `query`. */
export async function askDeployment(
  query: string,
  signal: AbortSignal,
): Promise<SearchResults> {
  try {
    const answer = await fetch(`${SEARCH_ENDPOINT}?q=${encodeURIComponent(query)}`, {
      signal,
      headers: { accept: 'application/json' },
      cache: 'no-store',
    });
    if (!answer.ok) return NOTHING;
    const body: unknown = await answer.json().catch(() => ({}));
    const rows: unknown = Reflect.get(Object(body), 'found');
    return {
      found: (Array.isArray(rows) ? rows : [])
        .map(foundOf)
        .filter((entry): entry is Found => entry !== null),
      partial: Reflect.get(Object(body), 'partial') === true,
    };
  } catch {
    return NOTHING;
  }
}
