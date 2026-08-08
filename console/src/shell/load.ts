import { ApiError, read } from '@/lib/api';
import { parseViewer, type Viewer } from '@/session/viewer';
import type { AttentionItem } from './attention';
import type { RecentRun } from './commands';
import type { Guardian } from './sidebar';

/**
 * What the shell needs before it can draw itself, read once per request.
 *
 * The viewer is resolved here and nowhere else. A shell that resolved
 * permissions per component would make one request per control and would
 * disagree with itself while they were in flight; a shell that resolved them
 * per page would let a page forget.
 *
 * Everything except the viewer degrades rather than throws. A notification count
 * that could not be read is a missing count, and a missing count must not be a
 * console nobody can sign in to — the chrome renders, and the panel that owns
 * the data says what happened. The viewer is the exception because there is no
 * honest shell to draw without one.
 */

/**
 * How long one of the shell's own auxiliary reads gets before it is given up on.
 *
 * The frame must render before any data resolves, and the honest way to hold
 * that is a deadline rather than a hope: a notification count that is slow
 * becomes a missing count, and the sidebar, the utility bar and the guardian
 * line are on screen either way. Mirrored in `config/constants/console.py` and
 * held equal by `tests/contract/console/test_console_shell.py`.
 *
 * The viewer has no deadline. There is no honest frame to draw without one, so
 * waiting is the correct behaviour and a refusal is the correct failure.
 */
export const SHELL_READ_TIMEOUT_MS = 2000;

/**
 * `work`, or `fallback` if it takes longer than the deadline.
 *
 * The read is abandoned rather than cancelled: `fetch` does not stop because
 * nobody is listening, and racing it is what keeps this a property of the
 * *frame* rather than of whichever endpoint happened to be slow.
 */
async function withDeadline<T>(work: Promise<T>, fallback: T): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const expiry = new Promise<T>((resolve) => {
    timer = setTimeout(() => {
      resolve(fallback);
    }, SHELL_READ_TIMEOUT_MS);
  });
  try {
    return await Promise.race([work, expiry]);
  } finally {
    clearTimeout(timer);
  }
}

/** Present the credential the request carried, and nothing else. */
function authorised(credential: string): RequestInit {
  return {
    headers: { authorization: `Bearer ${credential}` },
    // The shell is per-viewer and per-instant; a cached copy of it is somebody
    // else's permissions rendered for this person.
    cache: 'no-store',
  };
}

/** Who is looking, as the server resolved it. Throws when it cannot be established. */
export async function loadViewer(credential: string): Promise<Viewer> {
  return parseViewer(await read('/auth/me', authorised(credential)));
}

function records(body: unknown, key: string): readonly unknown[] {
  const found: unknown = Reflect.get(Object(body), key);
  return Array.isArray(found) ? found : [];
}

function text(record: unknown, key: string): string {
  const found: unknown = Reflect.get(Object(record), key);
  return typeof found === 'string' ? found : '';
}

/** The runs the palette offers by identifier, newest first as the API orders them. */
export async function loadRecentRuns(
  credential: string,
): Promise<readonly RecentRun[]> {
  return withDeadline(readRecentRuns(credential), []);
}

async function readRecentRuns(credential: string): Promise<readonly RecentRun[]> {
  try {
    const body = await read('/v1/runs', authorised(credential));
    return records(body, 'runs')
      .map((record) => ({
        id: text(record, 'run_id'),
        status: text(record, 'status'),
        summary: text(record, 'summary') === '' ? null : text(record, 'summary'),
      }))
      .filter((run) => run.id !== '');
  } catch (error) {
    if (error instanceof ApiError || error instanceof TypeError) {
      return [];
    }
    throw error;
  }
}

/** The statuses that mean a run needs somebody rather than that it is working. */
const FAILED_STATUSES: ReadonlySet<string> = new Set(['failed', 'error', 'cancelled']);

/**
 * Everything waiting on a person, from every source that has one today.
 *
 * Approvals awaiting a decision, and runs that ended badly. Agent questions
 * belong here too and arrive with the live layer, which is the feature that
 * introduces the stream they come from — the shape they will take is already
 * the shape of an `AttentionItem`, so adding them is adding a source rather than
 * changing this.
 */
export async function loadAttention(
  credential: string,
): Promise<readonly AttentionItem[]> {
  return withDeadline(readAttention(credential), []);
}

async function readAttention(credential: string): Promise<readonly AttentionItem[]> {
  const items: AttentionItem[] = [];
  try {
    const body = await read('/v1/approvals', authorised(credential));
    for (const record of records(body, 'approvals')) {
      if (text(record, 'state') !== 'pending') continue;
      const id = text(record, 'approval_id');
      if (id === '') continue;
      items.push({
        id,
        kind: 'approval',
        title: text(record, 'summary'),
        detail: text(record, 'action'),
        href: `/approvals/${id}`,
        since: text(record, 'requested_at'),
      });
    }
  } catch (error) {
    if (!(error instanceof ApiError || error instanceof TypeError)) throw error;
  }
  try {
    const body = await read('/v1/runs', authorised(credential));
    for (const record of records(body, 'runs')) {
      if (!FAILED_STATUSES.has(text(record, 'status'))) continue;
      const id = text(record, 'run_id');
      if (id === '') continue;
      items.push({
        id,
        kind: 'failure',
        title: text(record, 'summary'),
        detail: text(record, 'status'),
        href: `/runs/${id}`,
        since: text(record, 'started_at'),
      });
    }
  } catch (error) {
    if (!(error instanceof ApiError || error instanceof TypeError)) throw error;
  }
  return items;
}

/**
 * Whether the guardian is alive, and what it is currently allowed to do.
 *
 * Liveness comes from the deployment's own readiness report, which is the only
 * thing serving it today. **The posture is `propose` until something serves
 * one**: the autonomy policy engine is what will, and guessing a more permissive
 * posture from a deployment that has not told us would be the one direction this
 * must never be wrong in.
 */
export async function loadGuardian(credential: string): Promise<Guardian> {
  return withDeadline(readGuardian(credential), { live: false, posture: 'propose' });
}

async function readGuardian(credential: string): Promise<Guardian> {
  try {
    const body = await read('/health/ready', authorised(credential));
    return { live: Reflect.get(Object(body), 'ready') === true, posture: 'propose' };
  } catch (error) {
    if (error instanceof ApiError || error instanceof TypeError) {
      return { live: false, posture: 'propose' };
    }
    throw error;
  }
}

/** How many items of each area's kind are waiting, for the sidebar's counts. */
export function countsFrom(
  attention: readonly AttentionItem[],
): Readonly<Record<string, number>> {
  return {
    approvals: attention.filter((item) => item.kind === 'approval').length,
    incidents: attention.filter((item) => item.kind === 'incident').length,
    runs: attention.filter((item) => item.kind === 'failure').length,
  };
}
