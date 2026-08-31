import type { ReactNode } from 'react';

import {
  AGENT_INCIDENT_STATES,
  HUMAN_INCIDENT_STATES,
  isSettled,
  isTerminalIncident,
  needsAPerson,
  roleFor,
} from '@/design/status';
import { formatDuration, formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { ActivityFeed, type ActivityEntry } from '../activity';
import { AttentionBlock, type DecisionCardData, type DecisionStep } from '../attention';
import { readFailure } from '../failures';
import { Figure } from '../figure';
import { Panel } from '../panel';
import { panelLabels } from '../labels';
import { DashboardQuickActions } from '../quick-actions';
import { subjectOf } from '../run-subject';
import { SetupHero } from '../setup-hero';
import {
  authorised,
  counts,
  dataOf,
  dependencyOf,
  field,
  flag,
  list,
  number,
  optionalRead,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { NoProviderNotice } from '../first-run/no-provider';
import { outstanding, readSetup } from '../first-run/plan';
import { Tutorial } from '../first-run/tutorial';
// From the plain module rather than from the overlay: this screen renders on
// the server, and reading the flag out of a `'use client'` file made the whole
// dashboard throw before it painted anything.
import {
  TUTORIAL_QUERY_PARAM,
  TUTORIAL_REPLAY_VALUE,
  tutorialDismissed,
} from '../first-run/tutorial-setting';
import { RunBand, inFlightRuns, runCardOf, type RunCardData } from '../run-band';
import { IncidentGroupList } from '../incident-group-list';
import { groupBySubject } from '../incident-groups';
import { viewerNode } from '../tree';
import { may } from '@/session/viewer';
import type { SurfaceContext } from '../context';

/**
 * The screen an operator lands on, in the order of urgency the design fixes.
 *
 * Attention, then figures, then the narrative beside the estate and the
 * guardian. That order is not a layout preference: a number is never more urgent
 * than a decision somebody is waiting on, and putting the statistics first is how
 * a console teaches people that the top of the page is where the decoration
 * lives.
 *
 * Each panel has its own read and its own boundary. The detector and incident
 * counts come from endpoints the deployment does not serve yet; each of those
 * panels says so as an empty state naming the next action rather than as an
 * error, because a deployment nobody has connected anything to is new rather
 * than broken. The estate is served, so an empty one there means an estate
 * with nothing in it.
 *
 * While setup is incomplete, finishing it is the page: a hero dominates the
 * centre, above the figures, and gives way to nothing but its own absence the
 * moment there is nothing left to do (`setup-hero.tsx`).
 */

/** The statuses that mean a run needs somebody rather than that it is working. */
const FAILED = new Set(['failed', 'error', 'cancelled']);

/** How many activity entries the feed shows before it is a list rather than a narrative. */
const FEED_LENGTH = 8;

/** The permission the gateway requires to decide a remediation.
 *
 * `approval.review` (`Permission.APPROVAL_REVIEW`) -- the same right
 * `POST /v1/approvals/{id}/decision` itself checks
 * (`gateway/http/security/console_routes.py`), and the identical constant
 * `screens/approvals.tsx` already gates its own decision controls on.
 */
const DECIDE = 'approval.review';

/** One numbered step of a plan or its reversal, as the approval record serves it. */
function decisionStepsOf(record: unknown, key: string): readonly DecisionStep[] {
  return list(record, key).map((entry) => ({
    ordinal: number(entry, 'ordinal'),
    summary: text(entry, 'summary'),
  }));
}

/** `record` (one `ApprovalView`), as the inline decision band reads it. */
function decisionCardOf(
  record: unknown,
  locale: import('@/i18n/messages').Locale,
  now: Date,
  zone: string,
): DecisionCardData {
  return {
    id: text(record, 'approval_id'),
    title: text(record, 'title'),
    riskClass: text(field(record, 'risk'), 'class'),
    since: timestamp(locale, text(record, 'requested_at'), now, zone).relative,
    steps: decisionStepsOf(record, 'steps'),
    rollback: decisionStepsOf(record, 'rollback'),
  };
}

/**
 * The incidents this screen asks for by name, rather than by hoping.
 *
 * `/v1/incidents` answers with the most recently *opened* page. An estate that
 * closes a lot therefore pushes a still-open incident off that page within a
 * day or two, and the one screen whose job is to say what needs a person stops
 * being able to see it. Naming the states costs one query string and makes the
 * answer complete rather than recent.
 */
const HUMAN_INCIDENT_QUERY = `?${HUMAN_INCIDENT_STATES.map(
  (state) => `state=${state}`,
).join('&')}`;

/** The same, for what the agent is holding rather than what a person is. */
const AGENT_INCIDENT_QUERY = `?${AGENT_INCIDENT_STATES.map(
  (state) => `state=${state}`,
).join('&')}`;

/**
 * How urgent each kind of waiting thing is, smallest first.
 *
 * A failure heads it because a failed run can mean the deployment cannot
 * investigate at all, which is a different order of problem from a queue being
 * long. An approval is next: it is a production change stopped mid-flight. A
 * question has somebody's attention already. A proposal is an improvement, and
 * an improvement waiting is not an incident waiting.
 *
 * An incident's kind is its severity, so the two that carry real severity fall
 * between the question and the proposal, and anything unrecognised sorts last
 * rather than jumping the queue on a word nobody declared.
 */
const ATTENTION_WEIGHT: Readonly<Record<string, number>> = {
  failure: 0,
  approval: 1,
  question: 2,
  critical: 3,
  high: 4,
  proposal: 6,
};

function attentionWeight(kind: string): number {
  return ATTENTION_WEIGHT[kind] ?? 5;
}

/** Return the attention row whose source timestamp is the earliest valid instant. */
/** One thing waiting on a person, for the header's own count -- never rendered
 * as a row itself since the decision band narrowed to pending approvals. */
export interface AttentionRow {
  readonly id: string;
  readonly kind: string;
  readonly title: string;
  readonly detail: string;
  readonly href: string;
  readonly since: string;
  readonly at?: string;
}

export function oldestAttention(
  rows: readonly AttentionRow[],
): AttentionRow | undefined {
  let oldest: AttentionRow | undefined;
  let oldestAt = Number.POSITIVE_INFINITY;
  for (const row of rows) {
    const at = Date.parse(row.at ?? '');
    if (Number.isNaN(at) || at >= oldestAt) continue;
    oldest = row;
    oldestAt = at;
  }
  return oldest;
}

export async function DashboardScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, search, viewer, zone } = context;
  const init = authorised(credential);
  // The tutorial's dismissal is written at this node and read back from it, so
  // it has to resolve to a node that exists rather than to the empty string.
  const node = await viewerNode(viewer, init);

  const [
    approvals,
    proposals,
    runs,
    estate,
    detectors,
    incidents,
    blocked,
    held,
    checklist,
    effective,
  ] = await Promise.all([
    panelRead('/v1/approvals', () => read('/v1/approvals', init)),
    // The same list the sidebar badge counts, so the band and the badge
    // cannot disagree about how many are waiting.
    panelRead('/v1/proposals', () => read('/v1/proposals', init)),
    panelRead('/v1/runs', () => read('/v1/runs', init)),
    panelRead('/v1/estate/summary', () => read('/v1/estate/summary', init)),
    // `/health/ready` is no longer read here: the redesigned Painel has no
    // "is the guardian active" banner in its own content -- that indicator
    // lives in the sidebar footer (shell-level, outside this feature's
    // scope), and reading a source nothing renders is the recomputation
    // this feature's own rule forbids in the other direction.
    panelRead('/v1/detectors', () => read('/v1/detectors', authorised(credential))),
    // Two reads of one listing, because they are two questions. The narrative
    // below wants what happened lately, closures included; the attention band
    // wants everything still open however long ago it opened, and those are
    // not the same page.
    panelRead('/v1/incidents', () => read('/v1/incidents', authorised(credential))),
    panelRead('/v1/incidents', () =>
      read('/v1/incidents', { ...authorised(credential), query: HUMAN_INCIDENT_QUERY }),
    ),
    panelRead('/v1/incidents', () =>
      read('/v1/incidents', { ...authorised(credential), query: AGENT_INCIDENT_QUERY }),
    ),
    panelRead('/v1/setup/checklist', () => read('/v1/setup/checklist', init)),
    optionalRead('/v1/config/{node_id}', () =>
      node === ''
        ? Promise.resolve({})
        : read('/v1/config/{node_id}', { ...init, params: { node_id: node } }),
    ),
  ]);

  const setup = readSetup(dataOf(checklist), field(dataOf(effective), 'values'));
  const replay = search.get(TUTORIAL_QUERY_PARAM) === TUTORIAL_REPLAY_VALUE;

  const runRecords = list(dataOf(runs), 'runs');
  const approvalRecords = list(dataOf(approvals), 'approvals');
  const proposalRecords = list(dataOf(proposals), 'proposals');
  const incidentRecords = list(dataOf(incidents), 'incidents');
  const blockedRecords = list(dataOf(blocked), 'incidents');
  // Narrowed in the query and narrowed again here. A read is a request rather
  // than a guarantee, and a deployment that ignores the parameter would turn
  // this figure into "every open incident the agent has picked up" — the same
  // overstatement as the old attention count, pointing the other way.
  const heldRecords = list(dataOf(held), 'incidents').filter(
    (record) =>
      !needsAPerson(text(record, 'state')) &&
      !isTerminalIncident(text(record, 'state')),
  );
  // What keeps happening, from the unfiltered read: a cause that fired four
  // times and closed each time is exactly what this panel is for, so it must
  // not be narrowed to what is still open.
  const recurring = groupBySubject(incidentRecords).filter((group) => group.count > 1);
  const detectorRecords = list(dataOf(detectors), 'detectors');
  const summary = dataOf(estate);

  // --- What needs a person ---------------------------------------------------
  const attention: AttentionRow[] = [];
  for (const record of approvalRecords) {
    if (text(record, 'state') !== 'pending') continue;
    const id = text(record, 'approval_id');
    attention.push({
      id,
      kind: 'approval',
      title: text(record, 'summary'),
      detail: text(record, 'action'),
      href: `/decisions?tab=actions&selected=${id}`,
      since: timestamp(locale, text(record, 'requested_at'), now, zone).relative,
      at: text(record, 'requested_at'),
    });
  }
  for (const record of proposalRecords) {
    const id = text(record, 'proposal_id');
    if (id === '') continue;
    attention.push({
      id,
      kind: 'proposal',
      title: text(record, 'summary'),
      detail: text(record, 'proposal_type'),
      href: `/decisions?tab=changes&selected=${id}`,
      since: timestamp(locale, text(record, 'proposed_at'), now, zone).relative,
      at: text(record, 'proposed_at'),
    });
  }
  for (const record of blockedRecords) {
    // Belt and braces, and both earn their place. The read above asks for the
    // two states that are a person's problem by name, so nothing else should
    // arrive here; this holds anyway, because the line it replaces compared
    // against `closed` — a word the enumeration does not contain — and so
    // never once skipped anything, which is how every incident the agent had
    // already finished came to be counted as one waiting on a person.
    if (!needsAPerson(text(record, 'state'))) continue;
    const id = text(record, 'public_id');
    attention.push({
      id,
      kind: text(record, 'severity'),
      title: text(record, 'title'),
      detail: text(record, 'summary'),
      href: `/incidents/${id}`,
      since: timestamp(locale, text(record, 'opened_at'), now, zone).relative,
      at: text(record, 'opened_at'),
    });
  }
  for (const record of runRecords) {
    if (!FAILED.has(text(record, 'status'))) continue;
    const id = text(record, 'run_id');
    // A failed run's summary is whatever the deployment put there, and for the
    // failure that matters most that is a raised exception naming an
    // environment variable. It was the first thing on this page: a sentence
    // written for whoever deploys the product, shown to whoever opened the
    // console, on a screen that has a button leading to the fix. A run whose
    // text is not a raised exception is named the same way every other
    // surface names a run — never by printing its raw, possibly markdown
    // document here instead.
    const said = readFailure(text(record, 'summary'), locale);
    const raised = said.technical !== '';
    attention.push({
      id,
      kind: 'failure',
      title: raised ? said.title : subjectOf(record, locale).text,
      detail: raised ? said.action : text(record, 'status'),
      href: raised && said.href !== '' ? said.href : `/runs/${id}`,
      since: timestamp(locale, text(record, 'started_at'), now, zone).relative,
      at: text(record, 'started_at'),
    });
  }

  // Ordered before it is capped, or the cap decides by accident. The rows are
  // pushed in source order — approvals, then proposals, then incidents, then
  // failures — so a cap applied to that order drops failures first, and a
  // failed run is the one row that can mean the product itself cannot
  // investigate. Within a weight, oldest first, because "waiting longest" is
  // what the badge beside the heading is pointing at.
  attention.sort((left, right) => {
    const byKind = attentionWeight(left.kind) - attentionWeight(right.kind);
    if (byKind !== 0) return byKind;
    return Date.parse(left.at ?? '') - Date.parse(right.at ?? '');
  });

  // The pending remediations the inline decision band reads -- oldest
  // requested first, sorted on the raw instant before it is phrased into
  // "since", over the same listing (never a second read of /v1/approvals).
  const pendingDecisions: DecisionCardData[] = approvalRecords
    .filter((record) => text(record, 'state') === 'pending')
    .sort(
      (left, right) =>
        Date.parse(text(left, 'requested_at')) -
        Date.parse(text(right, 'requested_at')),
    )
    .map((record) => decisionCardOf(record, locale, now, zone));

  // --- The narrative ---------------------------------------------------------
  const feed: ActivityEntry[] = [];
  for (const record of incidentRecords) {
    const id = text(record, 'public_id');
    feed.push({
      id: `incident-${id}`,
      kind: 'incident',
      kindLabel: message(locale, 'incidents.list.title'),
      // The same comparison a second time, and the same defect: because
      // nothing ever equalled `closed`, this branch was unreachable and an
      // incident that resolved itself was drawn in the red of a live outage.
      // Only `resolved` earns the success well — an incident a person shut
      // with nothing done did not go well, it stopped.
      outcome:
        text(record, 'state') === 'resolved'
          ? 'success'
          : isTerminalIncident(text(record, 'state'))
            ? 'neutral'
            : 'danger',
      title: text(record, 'title'),
      detail: text(record, 'detector'),
      href: `/incidents/${id}`,
      ...timestamp(locale, text(record, 'opened_at'), now, zone),
    });
  }
  for (const record of runRecords) {
    const id = text(record, 'run_id');
    const status = text(record, 'status');
    // Same translation as the band above, for the same reason: this was the
    // fourth surface repeating the identical stack trace, and a narrative of
    // what happened here reads worst of all as an exception message. The
    // title itself comes from the one place that names a run — never the
    // raw summary a plain sentence used to fall through to here, which for
    // an ordinary investigation is its whole markdown report.
    const said = readFailure(text(record, 'summary'), locale);
    feed.push({
      id: `run-${id}`,
      kind: 'run',
      kindLabel: message(locale, 'runs.list.title'),
      outcome: FAILED.has(status)
        ? 'danger'
        : roleFor(status) === 'success'
          ? 'success'
          : 'info',
      title: subjectOf(record, locale).text,
      detail: said.technical === '' ? status : said.action,
      // Into the list rather than onto the run's own page: the run opens
      // where it sits and the ones around it stay on screen, which is the
      // comparison somebody following a recurring subject actually wants.
      href: `/runs?selected=${id}`,
      ...timestamp(locale, text(record, 'started_at'), now, zone),
    });
  }
  feed.sort((left, right) => right.iso.localeCompare(left.iso));
  const recent = feed.slice(0, FEED_LENGTH);

  // --- The estate ------------------------------------------------------------
  const watched = number(summary, 'total');
  // The persistence contract defines `problems` as degraded or unhealthy. Keep
  // unknown and stale out: they are gaps in observation, not estate faults, and
  // the problem drill-down must contain exactly what this number counts.
  const degraded = number(summary, 'problems');
  const kinds = counts(summary, 'by_kind')
    .map(([kind, count]) => `${formatNumber(locale, count)} ${kind}`)
    .join(' · ');

  const liveDetectors = detectorRecords.filter((record) =>
    flag(record, 'enabled'),
  ).length;

  // The runs the agent is working right now, named rather than counted.
  // `inFlightRuns` is `!isSettled` -- {running, suspended} -- deliberately
  // narrower than the literal "status NOT IN (completed,failed,cancelled)"
  // reading, which still admits `interrupted`: a run a reaper marked that
  // way days ago, with no title, is settled and does not belong here.
  const runsInFlight: RunCardData[] = inFlightRuns(runRecords).map((record) =>
    runCardOf(record, now),
  );

  // What the product exists to do, measured rather than asserted: of the
  // incidents that ended, how many ended without anybody being involved. This
  // is a different question from whether an investigation completed — a run
  // can succeed at telling a person what to go and fix.
  const endedIncidents = incidentRecords.filter((record) =>
    isTerminalIncident(text(record, 'state')),
  );
  const unattended = endedIncidents.filter((record) => flag(record, 'self_resolved'));
  const unattendedRate =
    endedIncidents.length === 0
      ? null
      : Math.round((unattended.length / endedIncidents.length) * 100);

  // How long it takes to get an answer, which is the figure a console that
  // counts investigations never prints. The median rather than the mean: one
  // run that hit its wall clock drags an average somewhere nobody's Tuesday
  // ever was, and this number exists to describe the ordinary case.
  const finished = runRecords
    .map((record) => {
      const opened = Date.parse(text(record, 'started_at'));
      const closed = Date.parse(text(record, 'finished_at'));
      if (Number.isNaN(opened) || Number.isNaN(closed)) return 0;
      return Math.max(0, (closed - opened) / 1000);
    })
    .filter((seconds) => seconds > 0)
    .sort((left, right) => left - right);
  const median =
    finished.length === 0
      ? null
      : (finished[Math.floor((finished.length - 1) / 2)] ?? 0);
  const slowest = finished.length === 0 ? 0 : (finished[finished.length - 1] ?? 0);

  // --- The agent, rather than the estate --------------------------------------
  // Every other figure on this page is about what is being watched. This one is
  // about whether the product itself is doing its job — the fact the reference
  // design leads with and this page, until now, never asked.
  const settledRuns = runRecords.filter((record) => isSettled(text(record, 'status')));
  // By role rather than by the literal word "completed": the persistence
  // store is the only source of a run's status and it never writes
  // "succeeded", but the shared presentation table still resolves that word
  // to the same success role a tool call's own outcome needs it for — so a
  // clean finish counts toward this figure under either spelling, rather
  // than a future drift between the two silently dragging it down.
  const succeededRuns = settledRuns.filter(
    (record) => roleFor(text(record, 'status')) === 'success',
  );
  const successRate =
    settledRuns.length === 0
      ? null
      : Math.round((succeededRuns.length / settledRuns.length) * 100);

  return (
    <>
      {/* Only while something is outstanding, and never once the effective
          configuration records a dismissal. A dismissal that never reached the
          deployment therefore cannot leave a configured one behind an overlay:
          the worst it can do is show this a second time. */}
      {replay ||
      (outstanding(setup) !== 0 &&
        !tutorialDismissed(field(dataOf(effective), 'values'))) ? (
        <Tutorial locale={locale} nodeId={node} replay={replay} />
      ) : null}

      <AreaHeader area={areaFor('dashboard')} locale={locale} />

      {/* Above the attention block and inside the page. A deployment with no
          provider genuinely cannot investigate, and it is told so here rather
          than by a door it cannot open — the figures below stay visible and
          honest at zero. */}
      <NoProviderNotice locale={locale} setup={setup} />

      {/* Is it working, before does it need you. An operator opening this page
          is asking the first question, and the second is only frightening
          when the first has no answer. */}
      <div className="mb-5">
        <RunBand
          locale={locale}
          runs={runsInFlight}
          followedCount={heldRecords.length}
          blockedCount={attention.length}
          moreHref="/runs"
        />
      </div>

      <div className="mb-5">
        <AttentionBlock
          locale={locale}
          decisions={pendingDecisions}
          canDecide={may(viewer, DECIDE)}
        />
      </div>

      {/* While anything remains, finishing setup dominates the page rather
          than sitting in a small side card beside an empty centre. It is
          absent, not shrunk, the moment nothing is left. */}
      <SetupHero locale={locale} setup={setup} source={checklist} />

      {/* Every figure has context and a list behind it. A figure that had neither
          would not compile — see `figure.tsx`. */}
      <div
        data-testid="main-figures"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5 mb-5"
      >
        <Figure
          label={message(locale, 'dashboard.stat.watched')}
          value={formatNumber(locale, watched)}
          context={message(locale, 'dashboard.stat.watched.context', {
            kinds: kinds === '' ? message(locale, 'surface.none') : kinds,
          })}
          href="/resources"
          drillLabel={message(locale, 'dashboard.stat.drill')}
        />
        <Figure
          label={message(locale, 'dashboard.stat.degraded')}
          value={formatNumber(locale, degraded)}
          // A degraded count with nothing beside it is where "24 unhealthy"
          // and "Incidents: none" stopped making sense together. Naming how
          // many detectors are actually switched on is the bridge: a finding
          // is not an incident until one of these turns it into one.
          // ...and where there are none at all, said as the sentence it is
          // rather than as "0 of 0", which the guardian band above was already
          // saying in the same breath.
          context={
            detectorRecords.length === 0
              ? message(locale, 'dashboard.stat.degraded.context.noDetectors', {
                  count: formatNumber(locale, number(summary, 'problems')),
                })
              : message(locale, 'dashboard.stat.degraded.context', {
                  count: formatNumber(locale, number(summary, 'problems')),
                  live: formatNumber(locale, liveDetectors),
                  total: formatNumber(locale, detectorRecords.length),
                })
          }
          href="/resources?health=problem"
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={degraded > 0 ? 'down' : 'flat'}
        />
        {/* The one figure about the product's own promise rather than about
            the estate it watches. */}
        <Figure
          label={message(locale, 'dashboard.stat.unattended')}
          value={
            unattendedRate === null ? '—' : `${formatNumber(locale, unattendedRate)}%`
          }
          context={
            unattendedRate === null
              ? message(locale, 'dashboard.stat.unattended.context.none')
              : message(locale, 'dashboard.stat.unattended.context', {
                  closed: formatNumber(locale, unattended.length),
                  total: formatNumber(locale, endedIncidents.length),
                })
          }
          href="/incidents"
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={
            unattendedRate === null ? 'flat' : unattendedRate >= 80 ? 'up' : 'down'
          }
        />
        {/* The one figure on this page about the agent rather than the
            estate: whether the product itself is doing its job. */}
        <Figure
          label={message(locale, 'dashboard.stat.successRate')}
          value={successRate === null ? '—' : `${formatNumber(locale, successRate)}%`}
          context={
            successRate === null
              ? message(locale, 'dashboard.stat.successRate.context.none')
              : message(locale, 'dashboard.stat.successRate.context', {
                  succeeded: formatNumber(locale, succeededRuns.length),
                  settled: formatNumber(locale, settledRuns.length),
                })
          }
          href={
            successRate !== null && successRate < 100 ? '/runs?status=failed' : '/runs'
          }
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={successRate === null ? 'flat' : successRate === 100 ? 'up' : 'down'}
        />
        {/* How long an answer takes, which every figure beside it leaves
            unanswered: four of them count things, and none of them says
            whether waiting for the agent is worth doing. The median rather
            than the mean, because one run that hit its wall clock drags an
            average somewhere nobody's Tuesday ever was. */}
        <Figure
          label={message(locale, 'dashboard.stat.timeToCause')}
          value={median === null ? '—' : formatDuration(locale, median)}
          context={
            median === null
              ? message(locale, 'dashboard.stat.timeToCause.context.none')
              : message(locale, 'dashboard.stat.timeToCause.context', {
                  settled: formatNumber(locale, finished.length),
                  slowest: formatDuration(locale, slowest),
                })
          }
          href={
            successRate !== null && successRate < 100 ? '/runs?status=failed' : '/runs'
          }
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={successRate === null ? 'flat' : successRate === 100 ? 'up' : 'down'}
        />
      </div>

      {/* What keeps happening, above the narrative rather than inside it. A
          cause that fired nine times is one problem and the feed would tell
          the reader it was nine — which is the whole defect this page was
          reformulated around. */}
      <div className="mb-5" data-testid="recurring-problems">
        <Panel
          title={message(locale, 'dashboard.recurring.title')}
          state={stateOf(incidents, recurring.length === 0)}
          dependency={dependencyOf(incidents)}
          action={
            <span className="text-meta text-muted">
              {message(locale, 'dashboard.recurring.note')}
            </span>
          }
          labels={panelLabels(locale, message(locale, 'dashboard.recurring.title'))}
          empty={{
            heading: message(locale, 'dashboard.recurring.empty.heading'),
            body: message(locale, 'dashboard.recurring.empty.body'),
            actionLabel: message(locale, 'dashboard.recurring.empty.action'),
            href: '/incidents',
          }}
        >
          <IncidentGroupList
            groups={recurring}
            locale={locale}
            now={new Date(now)}
            zone={zone}
          />
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0">
          <Panel
            title={message(locale, 'dashboard.activity.title')}
            state={stateOf(runs, recent.length === 0)}
            dependency={dependencyOf(runs)}
            labels={panelLabels(locale, message(locale, 'dashboard.activity.title'))}
            empty={{
              heading: message(locale, 'dashboard.activity.empty.heading'),
              body: message(locale, 'dashboard.activity.empty.body'),
              actionLabel: message(locale, 'dashboard.activity.empty.action'),
              // "Connect a source" is the catalogue's own job, not the
              // retired editor's.
              href: '/integrations',
            }}
          >
            <ActivityFeed entries={recent} />
          </Panel>
        </div>
        <div className="flex flex-col gap-5 min-w-0">
          {/* The remaining plan is the hero above, not a second copy of itself
              down here. Two checklists on one page is the page disagreeing with
              itself about where the operator should look. */}
          <DashboardQuickActions locale={locale} />
        </div>
      </div>
    </>
  );
}
