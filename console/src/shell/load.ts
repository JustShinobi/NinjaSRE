import { ApiError, read } from '@/lib/api';
import { parseViewer, type Viewer } from '@/session/viewer';
import { RUNTIME_STEP } from '@/surfaces/first-run/plan';
import type { AttentionItem } from './attention';
import type { RecentRun } from './commands';
import { EMPTY_BRIEFING, type LauncherBriefing } from './launcher';
import type { Guardian } from './sidebar';
import { NOT_STOPPED, stoppageFrom, type Stoppage } from './stoppage';

export { stoppageFrom, type LauncherBriefing, type Stoppage };

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

/**
 * How many runs either of the frame's two runs reads asks for.
 *
 * The palette offers recent runs by identifier, and twenty is a page of
 * "recent". The attention list asks for the same page size of runs that ended
 * badly. Neither is the whole first page the gateway would otherwise send —
 * the largest payload of every render, read for two small needs.
 */
const RECENT_RUNS_LIMIT = 20;

/**
 * The runs the palette offers by identifier, newest first as the API orders them.
 *
 * A different address from the attention list's read of the same endpoint,
 * on purpose: this wants the newest runs whatever their state, that wants
 * only the ones that ended badly. One address for both would be deduplicated
 * into one read of everything again.
 */
export async function loadRecentRuns(
  credential: string,
): Promise<readonly RecentRun[]> {
  return withDeadline(readRecentRuns(credential), []);
}

async function readRecentRuns(credential: string): Promise<readonly RecentRun[]> {
  try {
    const body = await read('/v1/runs', {
      ...authorised(credential),
      query: `?limit=${String(RECENT_RUNS_LIMIT)}`,
    });
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

/**
 * The statuses that mean a run needs somebody rather than that it is working.
 *
 * The gateway's own terminal words, and the one definition of "ended badly":
 * the query the attention read sends is built from this set, and the same set
 * checks what comes back. `interrupted` is here because it means nobody knows
 * how far the run got, which is exactly a run that needs a person.
 */
const FAILED_STATUSES: ReadonlySet<string> = new Set([
  'failed',
  'cancelled',
  'interrupted',
]);

/** The query that asks the gateway for only the runs that ended badly. */
function failedRunsQuery(): string {
  const statuses = [...FAILED_STATUSES].map((status) => `status=${status}`);
  return `?${[...statuses, `limit=${String(RECENT_RUNS_LIMIT)}`].join('&')}`;
}

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

/**
 * The body a settled read answered with, or nothing when it failed in one of
 * the two ways the frame degrades on.
 *
 * A refusal and an unreachable deployment are a missing count; anything else
 * is a defect and is surfaced, exactly as it was when the reads were made one
 * after the other.
 */
function answered(outcome: PromiseSettledResult<unknown>): unknown {
  if (outcome.status === 'fulfilled') return outcome.value;
  if (outcome.reason instanceof ApiError || outcome.reason instanceof TypeError) {
    return null;
  }
  throw outcome.reason;
}

async function readAttention(credential: string): Promise<readonly AttentionItem[]> {
  const init = authorised(credential);
  // Issued together rather than one after the other: each is a round trip to
  // the deployment on the critical path of every full-page render, and three
  // in sequence was three times the latency for the same three answers. The
  // results are still processed in the order the sources are listed, so the
  // list reads the same whichever endpoint answered first.
  //
  // The proposals list rather than its count, because the band needs a row and
  // not a number — and reading two endpoints for one fact is how the badge and
  // the band come to disagree about how many are waiting.
  //
  // Runs are filtered by the gateway, not here: only the ones that ended badly,
  // and a page of them. That gives this read a different address from the
  // palette's read of the same endpoint, which is intended — the two used to
  // share one address and one fifty-run page, the largest payload of every
  // render, for two small needs.
  const [approvals, proposals, runs] = (
    await Promise.allSettled([
      read('/v1/approvals', init),
      read('/v1/proposals', init),
      read('/v1/runs', { ...init, query: failedRunsQuery() }),
    ])
  ).map(answered);

  const items: AttentionItem[] = [];
  for (const record of records(approvals, 'approvals')) {
    if (text(record, 'state') !== 'pending') continue;
    const id = text(record, 'approval_id');
    if (id === '') continue;
    items.push({
      id,
      kind: 'approval',
      title: text(record, 'summary'),
      detail: text(record, 'action'),
      href: `/decisions?tab=actions&selected=${id}`,
      since: text(record, 'requested_at'),
    });
  }
  for (const record of records(proposals, 'proposals')) {
    const id = text(record, 'proposal_id');
    if (id === '') continue;
    items.push({
      id,
      kind: 'proposal',
      title: text(record, 'summary'),
      detail: text(record, 'proposal_type'),
      href: `/decisions?tab=changes&selected=${id}`,
      since: text(record, 'proposed_at'),
    });
  }
  for (const record of records(runs, 'runs')) {
    // Checked again on the way in: a gateway that does not know the `status`
    // filter answers with every run, and this is what keeps that honest.
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

/** How many rows one subject needs before "keeps coming back" is a fact. */
const RECURRING_FLOOR = 2;

/**
 * What the investigate launcher offers before anything is typed — the
 * `LauncherBriefing` that `./launcher` declares, built from three reads.
 *
 * Read by the launcher courier when the drawer opens, and no longer by the
 * frame: an incident listing, an estate summary and an organisation tree on
 * every render of every screen was the price of a drawer most page views
 * never open. The deadline is the frame's, kept so that a slow read still
 * degrades to the empty briefing rather than holding the drawer's answer.
 */
export async function loadLauncher(
  credential: string,
  teamNodeId: string,
): Promise<LauncherBriefing> {
  return withDeadline(readLauncher(credential, teamNodeId), EMPTY_BRIEFING);
}

async function readLauncher(
  credential: string,
  teamNodeId: string,
): Promise<LauncherBriefing> {
  const init = authorised(credential);
  const [incidents, estate, tree] = await Promise.all([
    read('/v1/incidents', init).catch(() => null),
    read('/v1/estate/summary', init).catch(() => null),
    read('/v1/config', init).catch(() => null),
  ]);

  // The open subject with the most rows behind it. Grouped by the
  // deployment's own correlation key — the same identity the incidents
  // screen groups by — and titled by the newest row's own human sentence.
  let recurring: LauncherBriefing['recurring'] = null;
  if (incidents !== null) {
    const open = records(incidents, 'incidents').filter(
      (row) => !['resolved', 'closed', 'suppressed'].includes(text(row, 'state')),
    );
    const grouped = new Map<string, { count: number; title: string }>();
    for (const row of open) {
      const key = text(row, 'correlation_key') || text(row, 'title');
      if (key === '') continue;
      const held = grouped.get(key);
      grouped.set(key, {
        count: (held?.count ?? 0) + 1,
        title: held?.title ?? (text(row, 'title') || key),
      });
    }
    for (const { count, title } of grouped.values()) {
      if (count >= RECURRING_FLOOR && count > (recurring?.count ?? 0)) {
        recurring = { subject: title, count };
      }
    }
  }

  const byHealth: unknown =
    estate === null ? undefined : Reflect.get(Object(estate), 'by_health');
  const unhealthyFound: unknown =
    byHealth === undefined ? undefined : Reflect.get(Object(byHealth), 'unhealthy');
  const unhealthy =
    typeof unhealthyFound === 'number' && Number.isFinite(unhealthyFound)
      ? unhealthyFound
      : 0;

  const teamName =
    tree === null
      ? ''
      : text(
          records(tree, 'nodes').find((node) => text(node, 'node_id') === teamNodeId),
          'name',
        );

  return { teamName, recurring, unhealthy };
}

/** How many items of each area's kind are waiting, for the sidebar's counts. */
export function countsFrom(
  attention: readonly AttentionItem[],
): Readonly<Record<string, number>> {
  return {
    // Decisions is one area now, for both kinds — a decision waiting is a
    // decision waiting, whichever of its two tabs it would open to.
    decisions: attention.filter(
      (item) => item.kind === 'approval' || item.kind === 'proposal',
    ).length,
    incidents: attention.filter((item) => item.kind === 'incident').length,
    runs: attention.filter((item) => item.kind === 'failure').length,
  };
}
