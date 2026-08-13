import { NextResponse, type NextRequest } from 'next/server';

import { apiOrigin } from '@/lib/api';
import { SESSION_COOKIE } from '@/session/cookies';
import {
  SEARCH_PAGE,
  incidentsMatching,
  resourcesMatching,
  runsMatching,
  worthSearching,
  type Found,
} from '@/shell/search';

/**
 * Answering "where is the thing called this".
 *
 * A courier, like every other read here: the session credential is an HTTP-only
 * cookie the browser cannot read and will not send to another host, so the
 * search cannot be three `fetch`es from the palette.
 *
 * Three reads, in parallel, and each one independent. A deployment whose
 * incident store is unavailable still finds resources — a search that failed
 * whole because one of its three sources did would be a search that stops
 * working exactly when somebody is looking for the thing that broke.
 *
 * The filtering is not done by the deployment because the deployment cannot: the
 * estate endpoint filters by kind, health, source and label, and has no text
 * parameter. So a page is read and matched here, and the answer says when it
 * only saw a page — "nothing matches" and "nothing matches in the first two
 * hundred" are different answers and only one of them means the thing is absent.
 */

/** One source, and how to turn its records into things the palette can show. */
interface Source {
  readonly path: string;
  readonly key: string;
  readonly match: (records: readonly unknown[], needle: string) => readonly Found[];
}

/** The page bound, as it goes into a query string. */
const PAGE = String(SEARCH_PAGE);

const SOURCES: readonly Source[] = [
  {
    path: `/v1/estate/resources?limit=${PAGE}`,
    key: 'resources',
    match: resourcesMatching,
  },
  { path: `/v1/incidents?limit=${PAGE}`, key: 'incidents', match: incidentsMatching },
  { path: `/v1/runs?limit=${PAGE}`, key: 'runs', match: runsMatching },
];

/** The array under `key`, or none when the body does not carry one. */
function recordsOf(body: unknown, key: string): readonly unknown[] {
  const found: unknown = Reflect.get(Object(body), key);
  return Array.isArray(found) ? found : [];
}

/** What one source contributed, and whether it held more than was read. */
async function fromSource(
  source: Source,
  needle: string,
  credential: string,
): Promise<{ found: readonly Found[]; partial: boolean }> {
  try {
    const answer = await fetch(`${apiOrigin()}${source.path}`, {
      headers: { authorization: `Bearer ${credential}`, accept: 'application/json' },
      cache: 'no-store',
    });
    if (!answer.ok) return { found: [], partial: false };
    const body: unknown = await answer.json().catch(() => ({}));
    const records = recordsOf(body, source.key);
    return {
      found: source.match(records, needle),
      // A full page back is the deployment telling us there may be more. The
      // page bound is ours, so this is the only place that can notice.
      partial: records.length >= SEARCH_PAGE,
    };
  } catch {
    // One unreachable source contributes nothing and takes nothing away. The
    // search an operator runs while something is down must still find the rest.
    return { found: [], partial: false };
  }
}

/** Find whatever answers to `q` across the estate, the incidents and the runs. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const credential = request.cookies.get(SESSION_COOKIE)?.value;
  if (credential === undefined || credential === '') {
    return NextResponse.json({ found: [], partial: false }, { status: 401 });
  }

  const query = request.nextUrl.searchParams.get('q') ?? '';
  if (!worthSearching(query)) {
    return NextResponse.json({ found: [], partial: false });
  }
  const needle = query.trim().toLowerCase();

  const answers = await Promise.all(
    SOURCES.map((source) => fromSource(source, needle, credential)),
  );

  return NextResponse.json({
    found: answers.flatMap((answer) => answer.found),
    partial: answers.some((answer) => answer.partial),
  });
}
