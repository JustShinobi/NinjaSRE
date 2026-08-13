import type { ReactNode } from 'react';

import { isSettled } from '@/design/status';
import { formatCount, formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import { ActivityFeed, type ActivityEntry } from '../activity';
import { AttentionBlock, type AttentionRow } from '../attention';
import { readFailure } from '../failures';
import { Figure } from '../figure';
import { Panel } from '../panel';
import { panelLabels } from '../labels';
import { DashboardQuickActions } from '../quick-actions';
import { SetupHero } from '../setup-hero';
import {
  authorised,
  countOf,
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
import { tutorialDismissed } from '../first-run/tutorial-setting';
import { viewerNode } from '../tree';
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

export async function DashboardScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, viewer, zone } = context;
  const init = authorised(credential);
  // The tutorial's dismissal is written at this node and read back from it, so
  // it has to resolve to a node that exists rather than to the empty string.
  const node = await viewerNode(viewer, init);

  const [
    approvals,
    proposals,
    runs,
    estate,
    health,
    detectors,
    incidents,
    checklist,
    effective,
  ] = await Promise.all([
    panelRead('/v1/approvals', () => read('/v1/approvals', init)),
    // The same list the sidebar badge counts, so the band and the badge
    // cannot disagree about how many are waiting.
    panelRead('/v1/proposals', () => read('/v1/proposals', init)),
    panelRead('/v1/runs', () => read('/v1/runs', init)),
    panelRead('/v1/estate/summary', () => read('/v1/estate/summary', init)),
    panelRead('/health/ready', () => read('/health/ready', init)),
    panelRead('/v1/detectors', () => read('/v1/detectors', authorised(credential))),
    panelRead('/v1/incidents', () => read('/v1/incidents', authorised(credential))),
    panelRead('/v1/setup/checklist', () => read('/v1/setup/checklist', init)),
    optionalRead('/v1/config/{node_id}', () =>
      node === ''
        ? Promise.resolve({})
        : read('/v1/config/{node_id}', { ...init, params: { node_id: node } }),
    ),
  ]);

  const setup = readSetup(dataOf(checklist), field(dataOf(effective), 'values'));

  const runRecords = list(dataOf(runs), 'runs');
  const approvalRecords = list(dataOf(approvals), 'approvals');
  const proposalRecords = list(dataOf(proposals), 'proposals');
  const incidentRecords = list(dataOf(incidents), 'incidents');
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
      href: `/approvals?selected=${id}`,
      since: timestamp(locale, text(record, 'requested_at'), now, zone).relative,
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
      href: `/proposals?selected=${id}`,
      since: timestamp(locale, text(record, 'proposed_at'), now, zone).relative,
    });
  }
  for (const record of incidentRecords) {
    if (text(record, 'state') === 'closed') continue;
    const id = text(record, 'incident_id');
    attention.push({
      id,
      kind: text(record, 'severity'),
      title: text(record, 'title'),
      detail: text(record, 'summary'),
      href: `/incidents/${id}`,
      since: timestamp(locale, text(record, 'opened_at'), now, zone).relative,
    });
  }
  for (const record of runRecords) {
    if (!FAILED.has(text(record, 'status'))) continue;
    const id = text(record, 'run_id');
    // A failed run's summary is whatever the deployment put there, and for the
    // failure that matters most that is a raised exception naming an
    // environment variable. It was the first thing on this page: a sentence
    // written for whoever deploys the product, shown to whoever opened the
    // console, on a screen that has a button leading to the fix.
    const said = readFailure(text(record, 'summary'), locale);
    const raised = said.technical !== '';
    attention.push({
      id,
      kind: 'failure',
      title: raised ? said.title : text(record, 'summary'),
      detail: raised ? said.action : text(record, 'status'),
      href: raised && said.href !== '' ? said.href : `/runs/${id}`,
      since: timestamp(locale, text(record, 'started_at'), now, zone).relative,
    });
  }

  const oldest = attention[attention.length - 1];

  // --- The narrative ---------------------------------------------------------
  const feed: ActivityEntry[] = [];
  for (const record of incidentRecords) {
    const id = text(record, 'incident_id');
    feed.push({
      id: `incident-${id}`,
      kind: 'incident',
      kindLabel: message(locale, 'incidents.list.title'),
      outcome: text(record, 'state') === 'closed' ? 'success' : 'danger',
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
    // what happened here reads worst of all as an exception message.
    const said = readFailure(text(record, 'summary'), locale);
    feed.push({
      id: `run-${id}`,
      kind: 'run',
      kindLabel: message(locale, 'runs.list.title'),
      outcome: FAILED.has(status)
        ? 'danger'
        : status === 'succeeded'
          ? 'success'
          : 'info',
      title: said.title === '' ? id : said.title,
      detail: said.technical === '' ? status : said.action,
      href: `/runs/${id}`,
      ...timestamp(locale, text(record, 'started_at'), now, zone),
    });
  }
  feed.sort((left, right) => right.iso.localeCompare(left.iso));
  const recent = feed.slice(0, FEED_LENGTH);

  // --- The estate ------------------------------------------------------------
  const watched = number(summary, 'total');
  const healthy = countOf(summary, 'by_health', 'healthy');
  // Not knowing and being broken are different facts, and the tile is the one
  // place they are added together — because the question it answers is "how
  // much of the estate am I not confident about".
  const degraded =
    number(summary, 'problems') +
    countOf(summary, 'by_health', 'unknown') +
    countOf(summary, 'by_health', 'stale');
  const kinds = counts(summary, 'by_kind')
    .map(([kind, count]) => `${formatNumber(locale, count)} ${kind}`)
    .join(' · ');

  const liveDetectors = detectorRecords.filter((record) =>
    flag(record, 'enabled'),
  ).length;
  const failedRuns = runRecords.filter((record) =>
    FAILED.has(text(record, 'status')),
  ).length;

  // --- The agent, rather than the estate --------------------------------------
  // Every other figure on this page is about what is being watched. This one is
  // about whether the product itself is doing its job — the fact the reference
  // design leads with and this page, until now, never asked.
  const settledRuns = runRecords.filter((record) => isSettled(text(record, 'status')));
  const succeededRuns = settledRuns.filter(
    (record) => text(record, 'status') === 'succeeded',
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
      {outstanding(setup) === 0 ||
      tutorialDismissed(field(dataOf(effective), 'values')) ? null : (
        <Tutorial locale={locale} nodeId={node} />
      )}

      <AreaHeader area={areaFor('dashboard')} locale={locale} />

      {/* Above the attention block and inside the page. A deployment with no
          provider genuinely cannot investigate, and it is told so here rather
          than by a door it cannot open — the figures below stay visible and
          honest at zero. */}
      <NoProviderNotice locale={locale} setup={setup} />

      <AttentionBlock
        heading={formatCount(
          locale,
          attention.length,
          'dashboard.attention.count.one',
          'dashboard.attention.count',
        )}
        oldest={message(locale, 'dashboard.attention.oldest', {
          age: oldest === undefined ? '' : oldest.since,
        })}
        rows={attention}
        openLabel={message(locale, 'surface.open')}
      />

      {attention.length === 0 ? (
        <div className="mb-5">
          <Panel
            title={message(locale, 'dashboard.attention.title')}
            state={stateOf(approvals, true)}
            dependency={dependencyOf(approvals)}
            labels={panelLabels(locale, message(locale, 'dashboard.attention.title'))}
            empty={{
              heading: message(locale, 'dashboard.attention.empty.heading'),
              body: message(locale, 'dashboard.attention.empty.body'),
              actionLabel: message(locale, 'dashboard.attention.empty.action'),
              href: '/runs',
            }}
          />
        </div>
      ) : null}

      {/* While anything remains, finishing setup dominates the page rather
          than sitting in a small side card beside an empty centre. It is
          absent, not shrunk, the moment nothing is left. */}
      <SetupHero locale={locale} setup={setup} source={checklist} />

      {/* Every figure has a period, a comparison and a list behind it. A figure
          that had none of those would not compile — see `figure.tsx`. */}
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
          label={message(locale, 'dashboard.stat.healthy')}
          value={formatNumber(locale, healthy)}
          context={message(locale, 'dashboard.stat.healthy.context', {
            count: formatNumber(locale, healthy),
            total: formatNumber(locale, watched),
          })}
          href="/resources?health=healthy"
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={healthy === watched && watched > 0 ? 'up' : 'flat'}
        />
        <Figure
          label={message(locale, 'dashboard.stat.degraded')}
          value={formatNumber(locale, degraded)}
          // A degraded count with nothing beside it is where "24 unhealthy"
          // and "Incidents: none" stopped making sense together. Naming how
          // many detectors are actually switched on is the bridge: a finding
          // is not an incident until one of these turns it into one.
          context={message(locale, 'dashboard.stat.degraded.context', {
            count: formatNumber(locale, number(summary, 'problems')),
            live: formatNumber(locale, liveDetectors),
            total: formatNumber(locale, detectorRecords.length),
          })}
          href="/resources?health=degraded"
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={degraded > 0 ? 'down' : 'flat'}
        />
        <Figure
          label={message(locale, 'dashboard.stat.runs')}
          value={formatNumber(locale, runRecords.length)}
          context={message(locale, 'dashboard.stat.runs.context', {
            failed: formatNumber(locale, failedRuns),
          })}
          href="/runs"
          drillLabel={message(locale, 'dashboard.stat.drill')}
          trend={failedRuns > 0 ? 'down' : 'flat'}
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
              href: '/configuration',
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

          <Panel
            title={message(locale, 'dashboard.guardian.title')}
            state={stateOf(health, false)}
            dependency={dependencyOf(health)}
            labels={panelLabels(locale, message(locale, 'dashboard.guardian.title'))}
            empty={{
              heading: message(locale, 'dashboard.guardian.empty.heading'),
              body: message(locale, 'dashboard.guardian.empty.body'),
              actionLabel: message(locale, 'dashboard.guardian.empty.action'),
              href: '/autonomy',
            }}
          >
            {/* Liveness is on the overview rather than buried in settings for
                one reason: a guardian that stopped looks exactly like a cluster
                with no problems. */}
            <dl className="flex flex-col gap-2 text-small">
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'dashboard.guardian.liveness')}
                </dt>
                <dd className="ml-auto" data-testid="guardian-liveness">
                  {flag(dataOf(health), 'ready')
                    ? message(locale, 'shell.guardian.active')
                    : message(locale, 'shell.guardian.silent')}
                </dd>
              </div>
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'dashboard.guardian.posture')}
                </dt>
                <dd className="ml-auto">
                  {message(locale, 'shell.guardian.posture.propose')}
                </dd>
              </div>
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'dashboard.guardian.detectors')}
                </dt>
                <dd className="ml-auto tabular-nums">
                  {message(locale, 'dashboard.guardian.detectors.value', {
                    live: formatNumber(locale, liveDetectors),
                    total: formatNumber(locale, detectorRecords.length),
                  })}
                </dd>
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}
