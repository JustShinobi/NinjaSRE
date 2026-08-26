import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { Link } from '@/components/action';
import { Breadcrumb } from '@/components/navigation';
import { PageHeader } from '@/components/layout';
import {
  formatCount,
  formatCurrency,
  formatDuration,
  formatNumber,
  timestamp,
} from '@/i18n/format';
import { message } from '@/i18n/messages';
import { areaFor, trailFor } from '@/shell/routes';
import { rulerFromReplay } from '../changes';
import type { SurfaceContext } from '../context';
import { readFailure } from '../failures';
import { eventTimes, panelLabels, transcriptLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  field,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { Report } from '../report';
import { subjectOf } from '../run-subject';
import { isLiveRun } from '@/design/status';
import { AddContext, AnswerControls, TakeoverControls } from '@/live/controls';
import { LiveRun } from '@/live/live-run';
import { may } from '@/session/viewer';
import { eventsFromReplay, usageFrom } from '../transcript';
import { Transcript } from '../transcript-view';
import { triggerLabel } from '../run-trigger';

/**
 * One run, read back.
 *
 * The transcript is the same component a live run uses; the difference between
 * the two is which reader built the events, and there is nothing below this line
 * that can tell. The cost breakdown is beside it rather than under it because
 * task routing sends different classes of work to different models, and "which
 * model did this cost me" is a question with an answer only when the split is on
 * the screen.
 */

/** The currency the deployment reports cost in. */
const CURRENCY = 'USD';

/** How long a run took, in seconds, or nought while it is still going. */
function durationOf(record: unknown): number {
  const started = Date.parse(text(record, 'started_at'));
  const finished = Date.parse(text(record, 'finished_at'));
  if (Number.isNaN(started) || Number.isNaN(finished)) return 0;
  return Math.max(0, (finished - started) / 1000);
}

export async function RunDetailScreen(
  context: SurfaceContext,
  runId: string,
): Promise<ReactNode> {
  const { credential, locale, now, viewer, zone } = context;
  const init = authorised(credential);

  const bound = { ...init, params: { run_id: runId } };
  const [detail, replay, incidents, interactions] = await Promise.all([
    panelRead('/v1/runs/{run_id}', () => read('/v1/runs/{run_id}', bound)),
    panelRead('/v1/runs/{run_id}/replay', () =>
      read('/v1/runs/{run_id}/replay', bound),
    ),
    panelRead('/v1/incidents', () => read('/v1/incidents', authorised(credential))),
    panelRead('/v1/investigations/{run_id}/interactions', () =>
      read('/v1/investigations/{run_id}/interactions', bound),
    ),
  ]);

  const run = dataOf(detail);
  const replayed = dataOf(replay);
  // A run that is still doing something is watched; one that has settled is
  // read back. Affirmative rather than "not settled" — a status neither
  // vocabulary recognises is drawn as the unknown word it is and offered
  // nothing, instead of defaulting to live the way the negated check used to.
  const running = isLiveRun(text(run, 'status'));
  const steerable = may(viewer, 'investigation.run');
  const open = list(dataOf(interactions), 'interactions').filter(
    (record) => field(record, 'is_open') !== false,
  );

  // The name of this run, computed once by the one place every surface that
  // names a run calls — the header below, the tab title (`page.tsx`) and the
  // runs list column all read the same function over the same record.
  const subject = subjectOf(run, locale);

  // What this screen says when the deployment's own text is an exception
  // rather than a document — still the only translator of a failure, and
  // still not the source of a successful run's name (`subject` above never
  // calls into this for that).
  const said = readFailure(text(run, 'summary'), locale);
  const reportText = text(run, 'report').trim();
  const headlineSentence = text(run, 'headline').trim() === '' ? '' : subject.full;

  // The transcript's own replay reader is handed the replay exactly as the
  // deployment served it — no summary spliced in. The report panel below is
  // where a run's document lives now, once, rather than as a second,
  // undisclosed copy styled as the transcript's own concluding word.
  const events = eventsFromReplay(replayed);
  const usage = usageFrom(replayed);

  const incident = list(dataOf(incidents), 'incidents').find(
    (record) => text(record, 'run_id') === runId,
  );
  // What this run's own record names — never the correlated incident's
  // subjects, which describe the incident rather than what this
  // investigation actually touched.
  const touchedResources = list(run, 'touched_resources').map(String);
  const linksReadFailed = incidents.status === 'error';
  const linksEmpty = incident === undefined && touchedResources.length === 0;

  const started = timestamp(locale, text(run, 'started_at'), now, zone);
  const seconds = durationOf(run);

  // Whether this run has nothing to show but the reason it never started. A run
  // in that state fills its cost and its links panels with an empty state whose
  // action is a navigation somewhere else, twice, which reads as more to do
  // than there is — the honest sentence is one line, not a call to action.
  const failedBeforeStart = !running && said.technical !== '' && events.length === 0;

  // The page's own name and its own metadata. Reused from the area only for the
  // breadcrumb's first crumb — a detail page's title is the thing it is showing,
  // never the list it was opened from, and its subtitle is what happened rather
  // than what the whole area is for.
  const area = areaFor('runs');
  const Icon = area.icon;
  const title = subject.text;
  const trail = trailFor(area, [{ label: subject.text }]);
  const trigger = triggerLabel(locale, text(run, 'trigger'));
  const subtitle = [
    started.relative,
    trigger,
    seconds === 0 ? '' : formatDuration(locale, seconds),
    usage.priced && usage.cost > 0 ? formatCurrency(locale, usage.cost, CURRENCY) : '',
  ]
    .filter((part) => part !== '')
    .join(' · ');

  // The footer, and it is drawn from the transcript rather than from a query of
  // its own. A run that never asked what changed has no ruler: an empty axis on
  // every investigation would read as "nothing changed", which is a claim only a
  // run that asked can make.
  const ruler = rulerFromReplay(replayed, { startedAt: text(run, 'started_at') });

  return (
    <>
      {/* Not `AreaHeader`: that component always names the area itself —
          "Investigations" and its list subtitle — which is true of the list and
          not of one run inside it. The composition below is the same one
          `AreaHeader` uses, with this run's own subject and metadata in the two
          slots the area's fixed title and context would otherwise fill. */}
      <div data-testid="page-header" data-area={area.id}>
        {trail.length > 1 ? (
          <Breadcrumb
            label={message(locale, 'breadcrumb.label')}
            trail={trail.map((crumb) => ({
              label: crumb.translate ? message(locale, crumb.label) : crumb.label,
              ...(crumb.href === undefined ? {} : { href: crumb.href }),
            }))}
          />
        ) : null}
        <PageHeader
          title={title}
          titleTooltip={subject.truncated ? subject.full : undefined}
          context={subtitle}
          icon={<Icon size="head" />}
          actions={<Badge status={text(run, 'status')} />}
        />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0 flex flex-col gap-5">
          <Panel
            title={message(locale, 'run.summary.title')}
            state={stateOf(
              detail,
              !said.known && reportText === '' && headlineSentence === '',
            )}
            dependency={dependencyOf(detail)}
            labels={panelLabels(locale, message(locale, 'run.summary.title'))}
            empty={{
              heading: message(locale, 'transcript.empty.heading'),
              body: message(locale, 'transcript.empty.body'),
              actionLabel: message(locale, 'transcript.empty.action'),
              href: '/runs',
            }}
          >
            {/* A recognised failure always wins this panel, even when the
                deployment's `report` field happens to carry the same raw
                exception text — the translation is the better reading of it.
                Otherwise the rendered document, when there is one; otherwise
                the headline itself, so a panel with a name but no document
                is not left blank; otherwise nothing, which is the empty
                state above. The header already says the name once, so this
                panel never repeats it next to the document. */}
            {said.known ? (
              <>
                <p className="text-small">{said.title}</p>
                {said.action === '' ? null : (
                  <p className="text-small text-muted mt-1">{said.action}</p>
                )}
                <details className="mt-2" data-testid="run-technical-detail">
                  <summary className="text-meta text-muted cursor-pointer">
                    {message(locale, 'failure.technical')}
                  </summary>
                  <p className="text-meta text-muted mt-1 whitespace-pre-wrap break-words">
                    {said.technical}
                  </p>
                </details>
              </>
            ) : reportText !== '' ? (
              <>
                <Report text={reportText} />
                {/* Reuses the same disclosure label the failure translation
                    already has, rather than a new catalogue key: both are
                    "the raw text behind the friendly reading above", and
                    `data-testid="report-raw"` still lets a test address this
                    one on its own. */}
                <details className="mt-2" data-testid="report-raw">
                  <summary className="text-meta text-muted cursor-pointer">
                    {message(locale, 'failure.technical')}
                  </summary>
                  <p className="text-meta text-muted mt-1 whitespace-pre-wrap break-words">
                    {reportText}
                  </p>
                </details>
              </>
            ) : headlineSentence !== '' ? (
              <p className="text-small">{headlineSentence}</p>
            ) : null}
            <p className="text-meta text-muted mt-2">
              <time dateTime={started.iso} title={started.absolute}>
                {started.relative}
              </time>{' '}
              · {trigger}
            </p>
          </Panel>

          <Panel
            title={message(locale, 'transcript.title')}
            state={stateOf(replay, events.length === 0)}
            dependency={dependencyOf(replay)}
            labels={panelLabels(locale, message(locale, 'transcript.title'))}
            empty={{
              heading: message(locale, 'transcript.empty.heading'),
              body: message(locale, 'transcript.empty.body'),
              actionLabel: message(locale, 'transcript.empty.action'),
              href: '/runs',
            }}
            action={
              <span className="text-meta text-muted">
                {formatCount(
                  locale,
                  events.length,
                  'transcript.events.one',
                  'transcript.events',
                )}
              </span>
            }
          >
            {running ? (
              // Seeded with nothing on purpose. The deployment's catch-up read
              // is inclusive of the whole log, so the stream *is* the transcript
              // — and seeding it with the replay as well would put every event
              // on the screen twice under two different identities.
              <LiveRun
                runId={runId}
                locale={locale}
                seed={{}}
                now={now.toISOString()}
                zone={zone}
              />
            ) : (
              <Transcript
                events={events}
                labels={transcriptLabels(locale, events)}
                times={eventTimes(locale, events, now, zone)}
              />
            )}
          </Panel>
        </div>

        <div className="flex flex-col gap-5 min-w-0">
          {/* Only while there is something to steer. A run that has finished is
              steered by nobody, and a panel of disabled controls on every
              completed run would change the resting shape of a screen that was
              already right. */}
          {steerable && running ? (
            <Panel
              title={message(locale, 'live.takeover.title')}
              state={stateOf(detail, false)}
              dependency={dependencyOf(detail)}
              labels={panelLabels(locale, message(locale, 'live.takeover.title'))}
              empty={{
                heading: message(locale, 'live.ended.completed'),
                body: message(locale, 'run.links.empty.body'),
                actionLabel: message(locale, 'transcript.empty.action'),
                href: '/runs',
              }}
            >
              <div className="flex flex-col gap-4">
                <TakeoverControls runId={runId} locale={locale} running={running} />
                <AddContext runId={runId} locale={locale} />
              </div>
            </Panel>
          ) : null}

          {open.map((interaction) => (
            <Panel
              key={text(interaction, 'interaction_id')}
              title={message(locale, 'live.question.title')}
              state={stateOf(interactions, false)}
              dependency={dependencyOf(interactions)}
              labels={panelLabels(locale, message(locale, 'live.question.title'))}
              empty={{
                heading: message(locale, 'live.question.title'),
                body: message(locale, 'live.question.required'),
                actionLabel: message(locale, 'transcript.empty.action'),
                href: '/runs',
              }}
            >
              {steerable ? (
                <AnswerControls
                  runId={runId}
                  locale={locale}
                  interactionId={text(interaction, 'interaction_id')}
                  question={text(interaction, 'text')}
                  options={list(interaction, 'options').map(String)}
                />
              ) : (
                <p className="text-small">{text(interaction, 'text')}</p>
              )}
            </Panel>
          ))}

          <Panel
            title={message(locale, 'run.usage.title')}
            // A run that failed before it began has nothing to break down, and
            // that is not this panel's error to report — the empty state below
            // is for a read that came back empty, not for a run that never spent
            // anything. Collapsing it here keeps the CTA for the read failure
            // this panel actually depends on, and drops it for the one it does
            // not.
            state={stateOf(replay, usage.byTurn.length === 0 && !failedBeforeStart)}
            dependency={dependencyOf(replay)}
            labels={panelLabels(locale, message(locale, 'run.usage.title'))}
            empty={{
              heading: message(locale, 'run.usage.empty.heading'),
              body: message(locale, 'run.usage.empty.body'),
              actionLabel: message(locale, 'run.usage.empty.action'),
              href: '/runs',
            }}
          >
            {failedBeforeStart && usage.byTurn.length === 0 ? (
              // One line, not a call to action pointing back at the list this
              // run was already opened from.
              <p className="text-small text-muted">
                {message(locale, 'run.usage.empty.heading')}
              </p>
            ) : (
              <div className="flex flex-col gap-4 text-small">
                <div className="flex items-center gap-3">
                  <span className="text-muted">
                    {message(locale, 'run.usage.tokens')}
                  </span>
                  <span className="ml-auto tabular-nums">
                    {formatNumber(locale, usage.tokens)}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-muted">
                    {message(locale, 'run.usage.cost')}
                  </span>
                  <span data-testid="run-cost" className="ml-auto tabular-nums">
                    {/* "$0.00" over thirty-six thousand tokens is not a
                        measurement, it is the absence of one wearing a
                        number. The gateway distinguishes the two and this
                        reads which it is. */}
                    {usage.priced
                      ? formatCurrency(locale, usage.cost, CURRENCY)
                      : message(locale, 'run.usage.unpriced')}
                  </span>
                </div>

                <table className="w-full text-meta">
                  <caption className="sr-only">
                    {message(locale, 'run.usage.model')}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="text-left text-micro text-muted pb-1">
                        {message(locale, 'run.usage.model')}
                      </th>
                      <th scope="col" className="text-right text-micro text-muted pb-1">
                        {message(locale, 'run.usage.turns')}
                      </th>
                      <th scope="col" className="text-right text-micro text-muted pb-1">
                        {message(locale, 'run.usage.tokens')}
                      </th>
                    </tr>
                  </thead>
                  <tbody data-testid="usage-by-model">
                    {usage.byModel.map((model) => (
                      <tr key={model.model}>
                        <td className="py-1 break-all">{model.model}</td>
                        <td className="py-1 text-right tabular-nums">
                          {formatNumber(locale, model.turns)}
                        </td>
                        <td className="py-1 text-right tabular-nums">
                          {formatNumber(locale, Math.round(model.tokens))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <table className="w-full text-meta">
                  <caption className="sr-only">
                    {message(locale, 'run.usage.turn')}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col" className="text-left text-micro text-muted pb-1">
                        {message(locale, 'run.usage.turn')}
                      </th>
                      <th scope="col" className="text-right text-micro text-muted pb-1">
                        {message(locale, 'run.usage.calls')}
                      </th>
                      <th scope="col" className="text-right text-micro text-muted pb-1">
                        {message(locale, 'run.usage.cost')}
                      </th>
                    </tr>
                  </thead>
                  <tbody data-testid="usage-by-turn">
                    {usage.byTurn.map((turn) => (
                      <tr key={turn.turn}>
                        <td className="py-1 tabular-nums">
                          {formatNumber(locale, turn.turn)}
                        </td>
                        <td className="py-1 text-right tabular-nums">
                          {formatNumber(locale, turn.calls)}
                        </td>
                        <td className="py-1 text-right tabular-nums">
                          {usage.priced
                            ? formatCurrency(locale, turn.cost, CURRENCY)
                            : message(locale, 'run.usage.unpriced.short')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Said rather than implied: the run reports one total and this is
                  that total divided, so nobody spends an afternoon reconciling a
                  per-turn figure against a meter. */}
                <p className="text-meta text-muted">
                  {message(locale, 'run.usage.apportioned')}
                </p>
              </div>
            )}
          </Panel>

          <Panel
            title={message(locale, 'run.links.title')}
            // A failed read of the correlation source is reported as a read
            // failure, never folded into "nothing linked" — the two are
            // different facts and only one of them is this screen's to
            // assert. A run with nothing linked because it failed before it
            // began is not a read that came back empty either, and does not
            // need that read's call to action.
            state={
              linksReadFailed
                ? 'error'
                : stateOf(detail, linksEmpty && !failedBeforeStart)
            }
            dependency={
              linksReadFailed ? dependencyOf(incidents) : dependencyOf(detail)
            }
            labels={panelLabels(locale, message(locale, 'run.links.title'))}
            empty={{
              heading: message(locale, 'run.links.empty.heading'),
              body: message(locale, 'run.links.empty.body'),
              actionLabel: message(locale, 'run.links.empty.action'),
              href: '/resources',
            }}
          >
            {linksEmpty ? (
              <p className="text-small text-muted">
                {message(locale, 'run.links.empty.heading')}
              </p>
            ) : (
              <dl className="flex flex-col gap-2 text-small">
                {incident === undefined ? null : (
                  <div className="flex items-center gap-3">
                    <dt className="text-muted">
                      {message(locale, 'run.links.incident')}
                    </dt>
                    <dd className="ml-auto min-w-0 truncate">
                      <Link
                        data-testid="run-incident-link"
                        href={`/incidents/${text(incident, 'public_id')}`}
                      >
                        {text(incident, 'title')}
                      </Link>
                    </dd>
                  </div>
                )}
                {touchedResources.length === 0 ? null : (
                  <div className="flex flex-col gap-1">
                    <dt className="text-muted">
                      {message(locale, 'run.links.resources')}
                    </dt>
                    {touchedResources.map((resource) => (
                      <dd key={resource} className="min-w-0 truncate">
                        <Link href={`/resources?selected=${resource}`}>{resource}</Link>
                      </dd>
                    ))}
                  </div>
                )}
              </dl>
            )}
          </Panel>
        </div>
      </div>

      {ruler === undefined ? null : (
        <Panel
          title={message(locale, 'run.changes.title')}
          state="ready"
          labels={panelLabels(locale, message(locale, 'run.changes.title'))}
          empty={{
            heading: message(locale, 'run.changes.title'),
            body: message(locale, 'run.changes.body'),
            actionLabel: message(locale, 'transcript.empty.action'),
            href: '/resources',
          }}
        >
          <div className="flex flex-col gap-4" data-testid="change-ruler">
            <p className="text-meta text-muted">{ruler.statement}</p>

            {/* The ruler itself. One track, marks positioned along it by the
                fraction of the window each one fell at — the same axis for the
                deploy and for the moment the investigation began, which is the
                whole point of drawing it rather than listing it. */}
            <div className="relative h-6 rounded-full bg-subtle">
              {ruler.investigation === undefined ? null : (
                <span
                  data-testid="investigation-mark"
                  aria-label={message(locale, 'run.changes.investigation')}
                  className="absolute top-0 h-6 w-0.5 bg-danger"
                  style={{
                    insetInlineStart: `${String(ruler.investigation.percent)}%`,
                  }}
                />
              )}
              {ruler.marks.map((mark) => (
                <span
                  key={mark.id}
                  data-testid="change-mark"
                  data-strength={mark.strength}
                  data-applied={String(mark.applied)}
                  aria-label={`${mark.id} ${mark.title}`}
                  className={
                    mark.temporalOnly
                      ? 'absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-muted'
                      : 'absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full bg-info'
                  }
                  style={{ insetInlineStart: `${String(mark.percent)}%` }}
                />
              ))}
            </div>

            <p className="text-micro text-muted">
              {message(locale, 'run.changes.window', {
                start: timestamp(locale, ruler.start, now, zone).absolute,
                end: timestamp(locale, ruler.end, now, zone).absolute,
              })}
            </p>

            {/* Named beside the ruler, not only on hover. A row of unlabelled
                ticks is a picture; the identifier is what somebody types into a
                terminal next. */}
            <ul className="flex flex-col gap-1 text-meta">
              {ruler.marks.map((mark) => (
                <li key={mark.id} className="flex flex-col">
                  <span>
                    <span className="text-strong">{mark.id}</span>{' '}
                    <span className="text-muted">{mark.title}</span>
                  </span>
                  <span className="text-micro text-muted">{mark.detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>
      )}
    </>
  );
}
