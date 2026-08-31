import type { ReactNode } from 'react';

import NextLink from 'next/link';

import {
  AGENT_INCIDENT_STATES,
  HUMAN_INCIDENT_STATES,
  isSettled,
  isTerminalIncident,
  needsAPerson,
  roleFor,
} from '@/design/status';
import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { ActivityFeed, collapseFeed, type ActivityFeedEntry } from '../activity-feed';
import { AttentionBlock, type DecisionCardData, type DecisionStep } from '../attention';
import { readFailure } from '../failures';
import { KpiTiles, type KpiData } from '../kpi-tiles';
import { Panel } from '../panel';
import { panelLabels } from '../labels';
import { subjectOf } from '../run-subject';
import { SetupHero } from '../setup-hero';
import { SubjectStrip } from '../subject-strip';
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
import {
  groupBySubject,
  subjectsInWindow,
  SUBJECT_WINDOW_HOURS,
} from '../incident-groups';
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
    overview,
    incidents,
    resources,
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
    // The five KPI tiles' one source (FR-019): a value, its breakdown and its
    // daily series, never recomputed here from a second read of the estate,
    // the runs or the incidents this screen used to query directly for the
    // same numbers. `/v1/estate/summary` and `/v1/detectors` are no longer
    // read on this screen either, for the identical reason `/health/ready`
    // already isn't: the "watched" count and the "no detector enabled"
    // legend are the overview's own fields, computed server-side.
    panelRead('/v1/overview', () => read('/v1/overview', init)),
    // Two reads of one listing, because they are two questions. The narrative
    // below wants what happened lately, closures included; the attention band
    // wants everything still open however long ago it opened, and those are
    // not the same page.
    panelRead('/v1/incidents', () => read('/v1/incidents', authorised(credential))),
    // The estate's own name for a recurring subject (FR-024/SC-007): a raw
    // resource id must never stand alone as "O que insiste em acontecer"'s
    // subtitle when the estate already has a name for it. The same read the
    // Incidents screen already makes for the identical reason, not a second
    // opinion computed here.
    panelRead('/v1/estate/resources', () => read('/v1/estate/resources', init)),
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
  // What keeps happening, from the unfiltered read, cut to the trailing 48h
  // window "O que insiste em acontecer" draws (FR-022/FR-023): a cause that
  // fired four times in the window and closed each time is exactly what this
  // panel is for, so it must not be narrowed to what is still open, and must
  // not count a firing from last month as part of what insists *now*.
  const recurring = subjectsInWindow(
    groupBySubject(incidentRecords),
    now,
    SUBJECT_WINDOW_HOURS,
  ).filter((group) => group.count > 1);
  // How many firings those subjects account for between them -- the sum of
  // exactly the `N×` counts the rows themselves show, so the header and the
  // rows can never disagree about how much is happening.
  const firings = recurring.reduce((total, group) => total + group.count, 0);
  // What the estate calls every resource it holds, resolved once for the
  // whole page from the same read -- never a second request, and never per
  // row. A subject the estate does not hold at all simply has no entry, and
  // `SubjectStrip` renders that honestly, as the shortened id, rather than
  // inventing one -- the same map and the same fallback the Incidents screen
  // already builds from this endpoint (`screens/incidents.tsx`).
  const subjectNames = new Map<string, string>();
  if (resources.status === 'ready') {
    for (const record of list(dataOf(resources), 'resources')) {
      const id = text(record, 'resource_id');
      const name = text(record, 'display_name');
      if (id !== '' && name !== '') subjectNames.set(id, name);
    }
  }
  const overviewData = dataOf(overview);
  // Distinct from any one KPI's own `value` being `null` (nothing in the
  // window can answer that KPI yet): this is the whole document failing to
  // arrive, which every tile must say together rather than each guessing on
  // its own from a `kpiOf` that degrades a missing document to five empty
  // KPIs by construction.
  const overviewFailed = overviewData === undefined;

  /** `overviewData[name]`'s own `{value, breakdown, series, note}`, read
   * defensively: a missing document (`overviewFailed`) degrades every field
   * to its own honest absence rather than throwing, because `KpiTiles` is
   * what decides whether to show that absence as "read failed" or as an
   * unmeasured `null` value -- never this function. */
  function kpiOf(name: string): KpiData {
    const kpi = field(overviewData, name);
    return {
      value: (() => {
        const found = field(kpi, 'value');
        return typeof found === 'number' && Number.isFinite(found) ? found : null;
      })(),
      breakdown: Object.fromEntries(counts(kpi, 'breakdown')),
      series: list(kpi, 'series').map((point) => ({
        date: text(point, 'date'),
        value: number(point, 'value'),
      })),
      note: text(kpi, 'note'),
    };
  }

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

  // --- The narrative -----------------------------------------------------
  // Four kinds, the shapes `Main.dc.html` draws for each: an investigation
  // starting or ending, an incident opening or closing on its own, a
  // remediation proposed or decided. Built from the three listings this
  // screen already reads -- never a fourth endpoint for the narrative alone
  // -- then folded by `collapseFeed` before the cap, so a repeating cause
  // costs one row rather than one per firing (the audit's own example:
  // DNSResolverProbeFailed, five times over, with no shape or hierarchy).
  const feed: ActivityFeedEntry[] = [];
  for (const record of runRecords) {
    const id = text(record, 'run_id');
    const status = text(record, 'status');
    feed.push({
      id: `run-started-${id}`,
      kind: 'investigation',
      outcome: 'info',
      title: message(locale, 'dashboard.liveActivity.investigationStarted'),
      detail: subjectOf(record, locale).text,
      href: `/runs?selected=${id}`,
      subjectKey: '',
      count: 1,
      ...timestamp(locale, text(record, 'started_at'), now, zone),
    });
    // A run still working has not resolved into anything yet -- only a
    // settled one earns its own second entry in the narrative.
    if (!isSettled(status)) continue;
    const said = readFailure(text(record, 'summary'), locale);
    const succeeded = roleFor(status) === 'success';
    feed.push({
      id: `run-ended-${id}`,
      kind: 'resolution',
      outcome: FAILED.has(status) ? 'danger' : succeeded ? 'success' : 'info',
      title: message(
        locale,
        succeeded
          ? 'dashboard.liveActivity.causeFound'
          : 'dashboard.liveActivity.investigationEnded',
      ),
      detail: said.technical === '' ? subjectOf(record, locale).text : said.action,
      href: `/runs?selected=${id}`,
      subjectKey: '',
      count: 1,
      ...timestamp(locale, text(record, 'finished_at'), now, zone),
    });
  }
  for (const record of incidentRecords) {
    const id = text(record, 'public_id');
    feed.push({
      id: `incident-opened-${id}`,
      kind: 'incident',
      outcome: 'danger',
      title: message(locale, 'dashboard.liveActivity.incidentOpened'),
      detail: text(record, 'title'),
      href: `/incidents/${id}`,
      // The key firings of the same cause collapse by -- FR-026 names only
      // "aberto, fechado sozinho" for an incident's own entries, so the
      // self-resolved closure below carries none: it never repeats the way
      // a fresh firing does, and folding it would fold two different facts.
      subjectKey: text(record, 'correlation_key'),
      count: 1,
      ...timestamp(locale, text(record, 'opened_at'), now, zone),
    });
    const closedAt = text(record, 'closed_at');
    if (flag(record, 'self_resolved') && closedAt !== '') {
      feed.push({
        id: `incident-closed-${id}`,
        kind: 'resolution',
        outcome: 'success',
        title: message(locale, 'dashboard.liveActivity.incidentSelfResolved'),
        detail: text(record, 'title'),
        href: `/incidents/${id}`,
        subjectKey: '',
        count: 1,
        ...timestamp(locale, closedAt, now, zone),
      });
    }
  }
  // Decisions: an approval this screen already reads for the band above,
  // read a second time here for the narrative rather than a parallel store --
  // proposals stay out of the feed the same way they stayed out of the
  // decision band once it narrowed to what a person actually decides.
  for (const record of approvalRecords) {
    const id = text(record, 'approval_id');
    if (id === '') continue;
    feed.push({
      id: `approval-proposed-${id}`,
      kind: 'approval',
      outcome: 'warning',
      title: message(locale, 'dashboard.liveActivity.decisionProposed'),
      detail: text(record, 'summary'),
      href: `/decisions?tab=actions&selected=${id}`,
      subjectKey: '',
      count: 1,
      ...timestamp(locale, text(record, 'requested_at'), now, zone),
    });
    const decidedAt = text(record, 'decided_at');
    if (decidedAt !== '') {
      feed.push({
        id: `approval-decided-${id}`,
        kind: 'approval',
        outcome: text(record, 'state') === 'approved' ? 'success' : 'neutral',
        title: message(locale, 'dashboard.liveActivity.decisionDecided'),
        detail: text(record, 'summary'),
        href: `/decisions?tab=actions&selected=${id}`,
        subjectKey: '',
        count: 1,
        ...timestamp(locale, decidedAt, now, zone),
      });
    }
  }
  feed.sort((left, right) => right.iso.localeCompare(left.iso));
  const recent = collapseFeed(feed).slice(0, FEED_LENGTH);

  // The runs the agent is working right now, named rather than counted.
  // `inFlightRuns` is `!isSettled` -- {running, suspended} -- deliberately
  // narrower than the literal "status NOT IN (completed,failed,cancelled)"
  // reading, which still admits `interrupted`: a run a reaper marked that
  // way days ago, with no title, is settled and does not belong here.
  const runsInFlight: RunCardData[] = inFlightRuns(runRecords).map((record) =>
    runCardOf(record, now),
  );

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

      {/* Every KPI reads only from the overview `GET /v1/overview` served --
          no client recomputation of a number that endpoint already answers
          (FR-019). `overviewFailed` is the whole document missing; a `null`
          on one KPI's own `value` is narrower and handled inside the tile. */}
      <KpiTiles
        locale={locale}
        failed={overviewFailed}
        watched={kpiOf('watched')}
        degraded={kpiOf('degraded')}
        selfResolved={kpiOf('self_resolved')}
        successRate={kpiOf('success_rate')}
        timeToCause={kpiOf('time_to_cause')}
      />

      {/* The last row of the page, and one row rather than two: what keeps
          happening in the wider column, what the deployment has been doing in
          the narrower one. A cause that fired nine times is one row on the
          left — the defect this page was reformulated around — and the
          narrative on the right is what those nine firings looked like as
          they arrived. Stacking them put a third of a screen between two
          readings of the same estate, and left the narrower column with
          nothing to hold but a list of links. */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0" data-testid="recurring-problems">
          <Panel
            title={message(locale, 'dashboard.recurring.title')}
            state={stateOf(incidents, recurring.length === 0)}
            dependency={dependencyOf(incidents)}
            // How many subjects, how many firings between them, and on which
            // of the two the rows are grouped — the three facts a reader
            // would otherwise add up by counting rows. Absent when there are
            // no rows, because "0 subjects · 0 firings" is a claim about the
            // estate that a failed read has no standing to make.
            action={
              recurring.length === 0 ? undefined : (
                <span data-testid="recurring-tally" className="text-meta text-muted">
                  {message(
                    locale,
                    recurring.length === 1
                      ? 'dashboard.recurring.tally.one'
                      : 'dashboard.recurring.tally',
                    {
                      subjects: formatNumber(locale, recurring.length),
                      firings: formatNumber(locale, firings),
                    },
                  )}
                </span>
              )
            }
            labels={panelLabels(locale, message(locale, 'dashboard.recurring.title'))}
            empty={{
              heading: message(locale, 'dashboard.recurring.empty.heading'),
              body: message(locale, 'dashboard.recurring.empty.body'),
              actionLabel: message(locale, 'dashboard.recurring.empty.action'),
              href: '/incidents',
            }}
          >
            <div className="flex flex-col gap-3 min-w-0">
              <SubjectStrip
                locale={locale}
                now={now}
                groups={recurring}
                subjectNames={subjectNames}
              />
              {/* The strip draws five; this names every one of them and
                  opens the screen where they all live, grouped the same way.
                  It is the panel's way out whether or not anything was cut,
                  because a reader who wants the whole list should not have to
                  wait for a sixth subject to be offered it. */}
              <NextLink
                href="/incidents"
                data-testid="recurring-more"
                className="text-meta text-accent hover:underline self-start"
              >
                {message(
                  locale,
                  recurring.length === 1
                    ? 'dashboard.recurring.more.one'
                    : 'dashboard.recurring.more',
                  { count: formatNumber(locale, recurring.length) },
                )}
              </NextLink>
            </div>
          </Panel>
        </div>
        <div className="min-w-0" data-testid="live-activity">
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
            <div className="flex flex-col gap-3 min-w-0">
              <ActivityFeed locale={locale} entries={recent} />
              {/* Eight entries is a narrative; the rest of it is the run
                  listing, which is where most of what this feed says
                  happened — an investigation starting, a cause found —
                  carries on in full. Incidents and decisions each reach their
                  own area from their own entry. */}
              <NextLink
                href="/runs"
                data-testid="activity-more"
                className="text-meta text-accent hover:underline self-start"
              >
                {message(locale, 'dashboard.activity.more')}
              </NextLink>
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
