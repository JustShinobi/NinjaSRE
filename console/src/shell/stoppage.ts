/**
 * What the deployment says about the emergency stop, read the same way twice.
 *
 * Its own module, with no `'use client'` and no import of the server's reading
 * helpers, for the reason `first-run/tutorial-setting.ts` exists: both sides
 * need it. The shell resolves the stoppage on the server before the frame is
 * drawn, and the stop control resolves it again in the browser from the answer
 * its courier hands back. A copy of this reading on the client would be a
 * second opinion about who stopped the estate, which is the one fact on this
 * screen that must not have two versions.
 */

/**
 * Whether every automated write is currently stopped, and who did it.
 *
 * `by` and `since` are `null` whenever they are not known — a read that
 * degraded, a deployment old enough to answer `engaged` with no `scopes`, or
 * the switch simply not being engaged. Reporting `null` rather than a guess is
 * the same rule the guardian posture follows: the direction this must never be
 * wrong in is claiming a fact nobody gave the shell.
 */
export interface Stoppage {
  readonly engaged: boolean;
  readonly by: string | null;
  readonly since: string | null;
}

export const NOT_STOPPED: Stoppage = { engaged: false, by: null, since: null };

/** The scope key an organisation-wide switch is held under, mirroring the gateway's own. */
const ORGANISATION_SCOPE = '*';

function text(record: unknown, key: string): string {
  const found: unknown = Reflect.get(Object(record), key);
  return typeof found === 'string' ? found : '';
}

/**
 * A `Stoppage` from the gateway's `KillSwitchView` — `{ engaged, scopes }`.
 *
 * `scopes` is the full report, every scope any switch is engaged for, not only
 * the caller's own — the organisation's is preferred because it is the widest
 * reason and the one an operator most needs to see first; failing that, the
 * first scope the deployment reports is still more honest than nothing.
 */
export function stoppageFrom(body: unknown): Stoppage {
  const engaged = Reflect.get(Object(body), 'engaged') === true;
  if (!engaged) return NOT_STOPPED;
  const scopes: unknown = Reflect.get(Object(body), 'scopes');
  const table: Record<string, unknown> =
    typeof scopes === 'object' && scopes !== null
      ? (scopes as Record<string, unknown>)
      : {};
  const chosen: unknown = table[ORGANISATION_SCOPE] ?? Object.values(table)[0];
  const by = text(chosen, 'engaged_by');
  const since = text(chosen, 'engaged_at');
  return {
    engaged: true,
    by: by === '' ? null : by,
    since: since === '' ? null : since,
  };
}
