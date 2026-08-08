import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { Link } from '@/components/action';
import { formatCurrency, formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { eventTimes, panelLabels, transcriptLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  panelRead,
  read,
  readProjectedPanel,
  stateOf,
  text,
} from '../read';
import { eventsFromReplay, usageFrom } from '../transcript';
import { Transcript } from '../transcript-view';

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

export async function RunDetailScreen(
  context: SurfaceContext,
  runId: string,
): Promise<ReactNode> {
  const { credential, locale, now, zone } = context;
  const init = authorised(credential);

  const bound = { ...init, params: { run_id: runId } };
  const [detail, replay, incidents] = await Promise.all([
    panelRead('/v1/runs/{run_id}', () => read('/v1/runs/{run_id}', bound)),
    panelRead('/v1/runs/{run_id}/replay', () =>
      read('/v1/runs/{run_id}/replay', bound),
    ),
    readProjectedPanel('/v1/incidents', credential),
  ]);

  const run = dataOf(detail);
  const replayed = dataOf(replay);
  const events = eventsFromReplay({
    ...Object(replayed),
    summary: text(run, 'summary'),
  });
  const usage = usageFrom(replayed);

  const incident = list(dataOf(incidents), 'incidents').find(
    (record) => text(record, 'run_id') === runId,
  );

  const started = timestamp(locale, text(run, 'started_at'), now, zone);

  return (
    <>
      <AreaHeader
        area={areaFor('runs')}
        locale={locale}
        nested={[{ label: runId }]}
        actions={<Badge status={text(run, 'status')} />}
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0 flex flex-col gap-5">
          <Panel
            title={message(locale, 'run.summary.title')}
            state={stateOf(detail, text(run, 'summary') === '')}
            dependency={dependencyOf(detail)}
            labels={panelLabels(locale, message(locale, 'run.summary.title'))}
            empty={{
              heading: message(locale, 'transcript.empty.heading'),
              body: message(locale, 'transcript.empty.body'),
              actionLabel: message(locale, 'transcript.empty.action'),
              href: '/runs',
            }}
          >
            <p className="text-small">{text(run, 'summary')}</p>
            <p className="text-meta text-muted mt-2">
              <time dateTime={started.iso} title={started.absolute}>
                {started.relative}
              </time>{' '}
              · {text(run, 'trigger')}
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
                {message(locale, 'transcript.events', {
                  count: formatNumber(locale, events.length),
                })}
              </span>
            }
          >
            <Transcript
              events={events}
              labels={transcriptLabels(locale, events)}
              times={eventTimes(locale, events, now, zone)}
            />
          </Panel>
        </div>

        <div className="flex flex-col gap-5 min-w-0">
          <Panel
            title={message(locale, 'run.usage.title')}
            state={stateOf(replay, usage.byTurn.length === 0)}
            dependency={dependencyOf(replay)}
            labels={panelLabels(locale, message(locale, 'run.usage.title'))}
            empty={{
              heading: message(locale, 'run.usage.empty.heading'),
              body: message(locale, 'run.usage.empty.body'),
              actionLabel: message(locale, 'run.usage.empty.action'),
              href: '/runs',
            }}
          >
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
                <span className="text-muted">{message(locale, 'run.usage.cost')}</span>
                <span className="ml-auto tabular-nums">
                  {formatCurrency(locale, usage.cost, CURRENCY)}
                </span>
              </div>

              <table className="w-full text-meta">
                <caption className="sr-only">
                  {message(locale, 'run.usage.model')}
                </caption>
                <thead>
                  <tr>
                    <th
                      scope="col"
                      className="text-left text-micro uppercase text-muted pb-1"
                    >
                      {message(locale, 'run.usage.model')}
                    </th>
                    <th
                      scope="col"
                      className="text-right text-micro uppercase text-muted pb-1"
                    >
                      {message(locale, 'run.usage.turns')}
                    </th>
                    <th
                      scope="col"
                      className="text-right text-micro uppercase text-muted pb-1"
                    >
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
                    <th
                      scope="col"
                      className="text-left text-micro uppercase text-muted pb-1"
                    >
                      {message(locale, 'run.usage.turn')}
                    </th>
                    <th
                      scope="col"
                      className="text-right text-micro uppercase text-muted pb-1"
                    >
                      {message(locale, 'run.usage.calls')}
                    </th>
                    <th
                      scope="col"
                      className="text-right text-micro uppercase text-muted pb-1"
                    >
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
                        {formatCurrency(locale, turn.cost, CURRENCY)}
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
          </Panel>

          <Panel
            title={message(locale, 'run.links.title')}
            state={stateOf(detail, incident === undefined)}
            dependency={dependencyOf(detail)}
            labels={panelLabels(locale, message(locale, 'run.links.title'))}
            empty={{
              heading: message(locale, 'run.links.empty.heading'),
              body: message(locale, 'run.links.empty.body'),
              actionLabel: message(locale, 'run.links.empty.action'),
              href: '/resources',
            }}
          >
            <dl className="flex flex-col gap-2 text-small">
              <div className="flex items-center gap-3">
                <dt className="text-muted">{message(locale, 'run.links.incident')}</dt>
                <dd className="ml-auto min-w-0 truncate">
                  <Link href={`/incidents/${text(incident, 'incident_id')}`}>
                    {text(incident, 'title')}
                  </Link>
                </dd>
              </div>
              <div className="flex flex-col gap-1">
                <dt className="text-muted">{message(locale, 'run.links.resources')}</dt>
                {list(incident, 'subjects').map((subject) => (
                  <dd key={String(subject)} className="min-w-0 truncate">
                    <Link href={`/resources?selected=${String(subject)}`}>
                      {String(subject)}
                    </Link>
                  </dd>
                ))}
              </div>
            </dl>
          </Panel>
        </div>
      </div>
    </>
  );
}
