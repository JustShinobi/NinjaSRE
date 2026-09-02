/**
 * What the investigate launcher offers before anything is typed: where the
 * environment already is.
 *
 * Derived from what the console already carries — the incident listing and
 * the estate's own summary — never invented. A deployment where neither read
 * answers offers only the always-true audit suggestion, which is the honest
 * floor rather than a failure.
 *
 * Its own module, with no directive, because two sides need it: the courier
 * under `src/app/api/launcher/` builds one on the server, and the drawer asks
 * for it from the browser when it opens. The drawer asks rather than being
 * handed one by the frame because the three reads behind it were being paid
 * on every render of every screen, for a drawer most page views never open.
 */

export interface LauncherBriefing {
  /** The viewer's own team, named by the organisation tree. Empty when unnamed. */
  readonly teamName: string;
  /** The open subject that keeps firing, when one does. */
  readonly recurring: { readonly subject: string; readonly count: number } | null;
  /** The estate's own count of unhealthy resources right now. */
  readonly unhealthy: number;
}

/** The honest floor: no team named, nothing recurring, nothing unhealthy. */
export const EMPTY_BRIEFING: LauncherBriefing = {
  teamName: '',
  recurring: null,
  unhealthy: 0,
};

/**
 * Where the drawer asks for its briefing.
 *
 * Shared by the courier's route file and the browser client the same way
 * `SEARCH_ENDPOINT` is: a path written twice is a path that gets renamed once.
 */
export const LAUNCHER_ENDPOINT = '/api/launcher';

/**
 * The briefing `body` carries, or the empty one when it is not a briefing.
 *
 * Anything crossing a process boundary is untrusted. A recurring subject
 * without a count would render as "keeps firing (undefined times)", so a body
 * that is not exactly the shape is the floor rather than a partial read.
 */
export function briefingOf(body: unknown): LauncherBriefing {
  const teamName: unknown = Reflect.get(Object(body), 'teamName');
  const unhealthy: unknown = Reflect.get(Object(body), 'unhealthy');
  const recurring: unknown = Reflect.get(Object(body), 'recurring');
  if (typeof teamName !== 'string') return EMPTY_BRIEFING;
  if (typeof unhealthy !== 'number' || !Number.isFinite(unhealthy)) {
    return EMPTY_BRIEFING;
  }
  if (recurring === null) return { teamName, recurring: null, unhealthy };
  const subject: unknown = Reflect.get(Object(recurring), 'subject');
  const count: unknown = Reflect.get(Object(recurring), 'count');
  if (typeof subject !== 'string' || typeof count !== 'number') {
    return EMPTY_BRIEFING;
  }
  return { teamName, recurring: { subject, count }, unhealthy };
}

/**
 * Ask the courier for the briefing, from the browser.
 *
 * A courier rather than three `fetch`es straight at the deployment, for the
 * reason every other read here goes through one: the session credential is an
 * HTTP-only cookie the browser cannot read and will not send to another host.
 *
 * Every failure — a refusal, an abort, a body that is not a briefing —
 * resolves to the empty briefing. The drawer renders that honestly already,
 * and an error where the suggestions go would be taking away the objective
 * field, which still works.
 */
export async function askLauncher(signal: AbortSignal): Promise<LauncherBriefing> {
  try {
    const answer = await fetch(LAUNCHER_ENDPOINT, {
      signal,
      headers: { accept: 'application/json' },
      cache: 'no-store',
    });
    if (!answer.ok) return EMPTY_BRIEFING;
    return briefingOf(await answer.json().catch(() => ({})));
  } catch {
    return EMPTY_BRIEFING;
  }
}
