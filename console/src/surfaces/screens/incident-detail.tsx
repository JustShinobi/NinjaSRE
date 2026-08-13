import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { formatCount, formatNumber, timestamp } from '@/i18n/format';
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
  field,
  list,
  pairs,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { eventsFromReplay } from '../transcript';
import { Transcript } from '../transcript-view';

/**
 * One incident: what is wrong, what is being proposed about it, and how the
 * conclusion was reached.
 *
 * The rail carries the derivation rather than a provider's word for it. That
 * panel is the visible form of "health is derived, not declared": named signals,
 * their values, their thresholds, and a note that the raw provider status is
 * retained. A console that showed `status: unknown` and stopped would be asking
 * an operator to trust a string.
 */

export async function IncidentDetailScreen(
  context: SurfaceContext,
  incidentId: string,
): Promise<ReactNode> {
  const { credential, locale, now, zone } = context;
  const init = authorised(credential);

  const detail = await panelRead('/v1/incidents/{incident_id}', () =>
    read('/v1/incidents/{incident_id}', {
      ...init,
      params: { incident_id: incidentId },
    }),
  );
  const body = dataOf(detail);
  const incident = field(body, 'incident');
  const observations = list(body, 'observations');
  const runId = text(incident, 'run_id');
  const [first] = list(incident, 'subjects');
  const subject = typeof first === 'string' ? first : '';

  const [replay, resource] = await Promise.all([
    // An incident with no run has no transcript, and asking for one at an empty
    // address would be a 404 dressed up as a failure.
    panelRead<unknown>('/v1/runs/{run_id}/replay', () =>
      runId === ''
        ? Promise.resolve({})
        : read('/v1/runs/{run_id}/replay', { ...init, params: { run_id: runId } }),
    ),
    // An incident with no subject has no resource, and the same reasoning as
    // the replay above applies: an empty address answers 404, which would read
    // on the screen as a resource that has gone.
    panelRead<unknown>('/v1/estate/resources/{resource_id}', () =>
      subject === ''
        ? Promise.resolve({})
        : read('/v1/estate/resources/{resource_id}', {
            ...init,
            params: { resource_id: subject },
          }),
    ),
  ]);

  const events = eventsFromReplay(dataOf(replay));
  // The named signals the state was derived from. This is the visible form of
  // "health is derived, not declared": the endpoint says what it concluded and
  // what it concluded it from, and this panel shows both.
  const health = list(field(dataOf(resource), 'derivation'), 'signals');
  const record = field(dataOf(resource), 'resource');
  const timeline = list(body, 'timeline');
  const opened = timestamp(locale, text(incident, 'opened_at'), now, zone);
  const none = message(locale, 'surface.none');

  return (
    <>
      <AreaHeader
        area={areaFor('incidents')}
        locale={locale}
        nested={[
          {
            label:
              text(incident, 'title') === '' ? incidentId : text(incident, 'title'),
          },
        ]}
        actions={
          <>
            <Badge status={text(incident, 'severity')} />
            <Badge status={text(incident, 'state')} />
          </>
        }
      />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 min-w-0 flex flex-col gap-5">
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
            <Transcript
              events={events}
              labels={transcriptLabels(locale, events)}
              times={eventTimes(locale, events, now, zone)}
            />
          </Panel>

          <Panel
            title={message(locale, 'incident.timeline.title')}
            state={stateOf(detail, timeline.length === 0)}
            dependency={dependencyOf(detail)}
            labels={panelLabels(locale, message(locale, 'incident.timeline.title'))}
            empty={{
              heading: message(locale, 'incident.timeline.empty.heading'),
              body: message(locale, 'incident.timeline.empty.body'),
              actionLabel: message(locale, 'incident.timeline.empty.action'),
              href: '/incidents',
            }}
          >
            <ol className="flex flex-col gap-3">
              {timeline.map((entry) => {
                const at = timestamp(locale, text(entry, 'at'), now, zone);
                return (
                  <li
                    key={`${text(entry, 'kind')}-${text(entry, 'at')}`}
                    className="flex gap-3"
                  >
                    <time
                      dateTime={at.iso}
                      title={at.absolute}
                      className="text-meta text-muted tabular-nums shrink-0"
                    >
                      {at.relative}
                    </time>
                    <span className="min-w-0 flex flex-col gap-1">
                      <Badge status={text(entry, 'kind')} />
                      <span className="text-small">{text(entry, 'detail')}</span>
                    </span>
                  </li>
                );
              })}
            </ol>
          </Panel>
        </div>

        <div className="flex flex-col gap-5 min-w-0">
          <Panel
            title={message(locale, 'incident.subject.title')}
            state={stateOf(detail, subject === '')}
            dependency={dependencyOf(detail)}
            labels={panelLabels(locale, message(locale, 'incident.subject.title'))}
            empty={{
              heading: message(locale, 'incidents.empty.heading'),
              body: message(locale, 'incidents.empty.body'),
              actionLabel: message(locale, 'incidents.empty.action'),
              href: '/resources',
            }}
          >
            <dl className="flex flex-col gap-2 text-small">
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'incident.subject.resource')}
                </dt>
                <dd className="ml-auto font-mono break-all">{subject}</dd>
              </div>
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'incident.subject.kind')}
                </dt>
                <dd className="ml-auto">
                  {text(record, 'kind') === '' ? none : text(record, 'kind')}
                </dd>
              </div>
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'incident.subject.health')}
                </dt>
                <dd className="ml-auto">
                  <Badge
                    status={
                      text(record, 'health') === '' ? 'unknown' : text(record, 'health')
                    }
                  />
                </dd>
              </div>
              <div className="flex items-center gap-3">
                <dt className="text-muted">
                  {message(locale, 'incident.subject.lastSeen')}
                </dt>
                <dd className="ml-auto">
                  {text(record, 'last_seen_at') === ''
                    ? none
                    : timestamp(locale, text(record, 'last_seen_at'), now, zone)
                        .relative}
                </dd>
              </div>
            </dl>
          </Panel>

          <Panel
            title={message(locale, 'incident.derivation.title')}
            state={stateOf(resource, health.length === 0 && observations.length === 0)}
            dependency={dependencyOf(resource)}
            labels={panelLabels(locale, message(locale, 'incident.derivation.title'))}
            empty={{
              heading: message(locale, 'incident.derivation.empty.heading'),
              body: message(locale, 'incident.derivation.empty.body'),
              actionLabel: message(locale, 'incident.derivation.empty.action'),
              href: '/detectors',
            }}
          >
            <p className="text-meta text-muted mb-2">
              {message(locale, 'incident.derivation.lead', {
                count: formatNumber(locale, health.length + observations.length),
              })}
            </p>
            <ul data-testid="derivation" className="flex flex-col gap-2 text-small">
              {health.map((check) => (
                <li key={text(check, 'name')} className="flex items-center gap-2">
                  <span className="font-mono min-w-0 truncate">
                    {text(check, 'name')}
                  </span>
                  <Badge status={text(check, 'value')} className="ml-auto" />
                  <span className="text-meta text-muted">{text(check, 'source')}</span>
                </li>
              ))}
              {observations.map((observation) =>
                pairs(observation, 'evidence').map(([name, value]) => (
                  <li
                    key={`${text(observation, 'observation_id')}-${name}`}
                    className="flex items-center gap-2"
                  >
                    <span className="font-mono min-w-0 truncate">{name}</span>
                    <span className="ml-auto tabular-nums">{value}</span>
                  </li>
                )),
              )}
            </ul>
            {/* Said out loud, because the whole point of this panel is that the
                verdict is derived rather than repeated from a provider. */}
            <p className="text-meta text-muted mt-2">
              {message(locale, 'incident.derivation.retained')}
            </p>
          </Panel>

          <p className="text-meta text-muted">
            <time dateTime={opened.iso} title={opened.absolute}>
              {opened.relative}
            </time>{' '}
            · {text(incident, 'detector')}
          </p>
        </div>
      </div>
    </>
  );
}
