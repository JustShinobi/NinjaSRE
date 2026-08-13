import { ApiError, read } from '@/lib/api';
import { parseViewer, type Viewer } from '@/session/viewer';
import { RUNTIME_STEP } from '@/surfaces/first-run/plan';
import type { AttentionItem } from './attention';
import type { RecentRun } from './commands';
import type { Guardian } from './sidebar';
import { NOT_STOPPED, stoppageFrom, type Stoppage } from './stoppage';

export { stoppageFrom, type Stoppage };

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
    // The list rather than the count, because the band needs a row and not a
    // number — and reading two endpoints for one fact is how the badge and the
    // band come to disagree about how many are waiting.
    const body = await read('/v1/proposals', authorised(credential));
    for (const record of records(body, 'proposals')) {
      const id = text(record, 'proposal_id');
      if (id === '') continue;
      items.push({
        id,
        kind: 'proposal',
        title: text(record, 'summary'),
        detail: text(record, 'proposal_type'),
        href: `/proposals?selected=${id}`,
        since: text(record, 'proposed_at'),
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

/**
 * Whether every automated write is currently stopped.
 *
 * Read for the frame rather than for the autonomy screen, because the banner it
 * feeds is on every screen. It degrades to **not stopped**, which is the honest
 * direction here and the opposite of the guardian posture's: a banner claiming
 * automation is stopped when the read merely failed would send an operator to
 * release a switch nobody engaged.
 */
export async function loadStopped(credential: string): Promise<Stoppage> {
  return withDeadline(readStopped(credential), NOT_STOPPED);
}

async function readStopped(credential: string): Promise<Stoppage> {
  try {
    const body = await read('/v1/autonomy/kill-switch', authorised(credential));
    return stoppageFrom(body);
  } catch (error) {
    if (error instanceof ApiError || error instanceof TypeError) return NOT_STOPPED;
    throw error;
  }
}

/**
 * What the frame needs to know about the deployment's own setup.
 *
 * Three facts, and each degrades in the direction that is safe to be wrong
 * in. A checklist that could not be read is **not complete**, so the one
 * route that finishes configuring a half-up deployment stays in the
 * navigation of exactly that deployment. Integrations are assumed
 * **configured**, and the runtime is assumed **composed**, for the same
 * reason as each other: both feed an advisory caveat in the investigation
 * drawer rather than the navigation, and a read that failed must not put a
 * warning in front of somebody whose deployment works fine.
 */
export interface SetupState {
  readonly checklistComplete: boolean;
  readonly integrationsConfigured: boolean;
  /**
   * Whether this process holds something that can actually drive an
   * investigation, read from the checklist's own fifth step.
   *
   * This is what lets the investigation drawer say what is missing *before*
   * the click rather than after: starting one would refuse with
   * `InvestigatorNotConfigured` regardless of anything the operator types,
   * and this is the one fact that can be read ahead of that request instead
   * of parsed out of its failure.
   */
  readonly runtimeComposed: boolean;
}

const ASSUMED_SETUP: SetupState = {
  checklistComplete: false,
  integrationsConfigured: true,
  runtimeComposed: true,
};

/** Whether setup is finished, whether anything is connected, and whether a run could actually start. */
export async function loadSetup(credential: string): Promise<SetupState> {
  return withDeadline(readSetupState(credential), ASSUMED_SETUP);
}

async function readSetupState(credential: string): Promise<SetupState> {
  try {
    const body = await read('/v1/setup/checklist', authorised(credential));
    const declared = records(body, 'integrations');
    const runtimeStep = records(body, 'steps').find(
      (entry) => text(entry, 'name') === RUNTIME_STEP,
    );
    return {
      checklistComplete: Reflect.get(Object(body), 'complete') === true,
      // Declared and holding nothing is what `absent` means, so a deployment
      // that declares three integrations and has stored none is unconnected.
      integrationsConfigured: declared.some(
        (entry) => text(entry, 'readiness') !== 'absent',
      ),
      // Absent from the steps this deployment reports — an older backend,
      // before this step existed — reads the same as composed: this fact
      // exists to state a dependency the deployment can prove is missing,
      // not to invent one it has never declared.
      runtimeComposed:
        runtimeStep === undefined || text(runtimeStep, 'state') === 'done',
    };
  } catch (error) {
    if (error instanceof ApiError || error instanceof TypeError) {
      return ASSUMED_SETUP;
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
    proposals: attention.filter((item) => item.kind === 'proposal').length,
    incidents: attention.filter((item) => item.kind === 'incident').length,
    runs: attention.filter((item) => item.kind === 'failure').length,
  };
}
