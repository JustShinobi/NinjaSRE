import { cache } from 'react';

import { deployment, type Deployment } from '@/shell/deployment';
import { loadViewer } from '@/shell/load';
import { requestCredential, requestLocale } from '@/shell/request';
import type { Locale } from '@/i18n/messages';
import type { Viewer } from '@/session/viewer';

/**
 * What every screen is handed, resolved once per request.
 *
 * The viewer is resolved here as well as in the layout, and that is deliberate
 * rather than an oversight: a client-side route transition fetches the *page*
 * segment without re-rendering the layout, so a page that relied on the layout
 * having resolved a viewer would render with nobody's permissions on exactly the
 * navigations people make most. `cache` collapses the two reads back into one
 * whenever they do happen together.
 *
 * `now` is taken once per request rather than per component. Two panels that
 * each read the clock disagree by whatever the render took, and a list whose
 * first row says "4m ago" and whose last says "5m ago" about the same instant is
 * a list somebody will spend an afternoon on.
 */

/** Who is looking, in what language, at which deployment, and when. */
export interface SurfaceContext {
  readonly credential: string;
  readonly locale: Locale;
  readonly viewer: Viewer;
  readonly deployment: Deployment;
  readonly now: Date;
  readonly zone: string;
  /** The address's query, which is where every screen keeps what it is showing. */
  readonly search: URLSearchParams;
}

/**
 * An instant to read every relative time against, instead of the clock.
 *
 * Unset in a deployment, where the clock is the right answer. The visual capture
 * sets it, because the committed dataset carries one fixed instant and a screen
 * that renders "17 hours ago" against the real clock says "18 hours ago" an hour
 * later — a baseline that fails on the hour and on nothing else. Mirrored in
 * `config/constants/console.py`.
 */
export const CLOCK_ENV = 'NINJASRE_CONSOLE_CLOCK';

/** The instant this request renders against: the fixed one, or now. */
function requestClock(): Date {
  const fixed = process.env[CLOCK_ENV];
  if (fixed === undefined || fixed === '') return new Date();
  const parsed = new Date(fixed);
  // An unparseable instant falls back to the clock rather than to 1970, which
  // would render every timestamp as "56 years ago" and look like a data fault.
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

/** The viewer, resolved at most once for a whole render. */
const viewerFor = cache(async (credential: string): Promise<Viewer> =>
  loadViewer(credential),
);

/** What Next hands a page as its search parameters. */
export type SearchParams = Readonly<Record<string, string | string[] | undefined>>;

/** `params` as a query, taking the first value of anything repeated. */
export function searchFrom(params: SearchParams): URLSearchParams {
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (typeof value === 'string') {
      search.set(name, value);
    } else if (Array.isArray(value) && typeof value[0] === 'string') {
      search.set(name, value[0]);
    }
  }
  return search;
}

/**
 * The context this request renders in.
 *
 * Throws when there is no credential. The middleware refuses an unauthenticated
 * request before routing reaches a page, so reaching here without one is a
 * defect in the guard rather than a state to render — and rendering an empty
 * screen for it would hide the defect behind something that looks like no data.
 */
export async function surfaceContext(
  params: SearchParams = {},
): Promise<SurfaceContext> {
  const credential = await requestCredential();
  if (credential === null) {
    throw new Error('a surface was rendered for a request that carries no session');
  }
  const [locale, viewer] = await Promise.all([requestLocale(), viewerFor(credential)]);
  const site = deployment();
  return {
    credential,
    locale,
    viewer,
    deployment: site,
    now: requestClock(),
    zone: site.timezone,
    search: searchFrom(params),
  };
}
