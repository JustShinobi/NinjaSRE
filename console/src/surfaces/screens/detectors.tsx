import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { panelLabels } from '../labels';
import { Panel } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  flag,
  list,
  number,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';

/**
 * What is being watched for, how well it is covered, and what it last found.
 *
 * Each row carries its own description rather than pointing at documentation:
 * the rationale for a threshold is what somebody needs at the moment they are
 * deciding whether the threshold is wrong, and a file they would have to go and
 * find is a file they will not.
 *
 * Coverage is the column that turns "this detector exists" into "this detector
 * is looking at 84 of 92 things", which are very different claims.
 */

export async function DetectorsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, zone } = context;

  const detectors = await panelRead('/v1/detectors', () =>
    read('/v1/detectors', authorised(credential)),
  );
  const records = list(dataOf(detectors), 'detectors');

  return (
    <>
      <AreaHeader area={areaFor('detectors')} locale={locale} />

      <Panel
        title={message(locale, 'detectors.list.title')}
        state={stateOf(detectors, records.length === 0)}
        dependency={dependencyOf(detectors)}
        labels={panelLabels(locale, message(locale, 'detectors.list.title'))}
        empty={{
          heading: message(locale, 'detectors.empty.heading'),
          body: message(locale, 'detectors.empty.body'),
          actionLabel: message(locale, 'detectors.empty.action'),
          href: '/configuration',
        }}
      >
        <div className="w-full overflow-x-auto">
          <table className="w-full text-small">
            <caption className="sr-only">
              {message(locale, 'detectors.list.caption')}
            </caption>
            <thead>
              <tr>
                {[
                  message(locale, 'detectors.column.name'),
                  message(locale, 'detectors.column.watches'),
                  message(locale, 'detectors.column.severity'),
                  message(locale, 'detectors.column.coverage'),
                  message(locale, 'detectors.column.verdict'),
                  message(locale, 'detectors.column.enabled'),
                ].map((header) => (
                  <th
                    key={header}
                    scope="col"
                    className="text-left text-micro uppercase text-muted px-3 pb-2 edge border-border border-t-0 border-x-0"
                  >
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {records.map((record) => {
                const evaluated = timestamp(
                  locale,
                  text(record, 'last_evaluated_at'),
                  now,
                  zone,
                );
                return (
                  <tr
                    key={text(record, 'detector_id')}
                    data-testid="detector"
                    data-detector={text(record, 'detector_id')}
                  >
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0 font-mono break-all">
                      {text(record, 'name')}
                      {flag(record, 'proposed') ? (
                        <span
                          className="text-meta text-muted ml-2"
                          data-testid="detector-proposed"
                        >
                          {message(locale, 'detectors.proposed')}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                      {text(record, 'description')}
                      {/* A proposed threshold is somebody else's judgement, and
                          the operator deciding whether to enable it needs the
                          sentence that judgement was written in. */}
                      {flag(record, 'proposed') ? (
                        <span
                          className="block text-meta text-muted"
                          data-testid="detector-origin"
                          data-origin={text(record, 'origin')}
                        >
                          {text(record, 'origin_excerpt')}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                      <Badge status={text(record, 'severity')} />
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0 tabular-nums">
                      {formatNumber(locale, number(record, 'subjects_covered'))} /{' '}
                      {formatNumber(locale, number(record, 'subjects_total'))}
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                      <Badge status={text(record, 'last_verdict')} />
                      <span className="text-meta text-muted ml-2">
                        <time dateTime={evaluated.iso} title={evaluated.absolute}>
                          {evaluated.relative}
                        </time>
                      </span>
                    </td>
                    <td className="px-3 py-2 edge border-border border-t-0 border-x-0">
                      <Badge
                        status={flag(record, 'enabled') ? 'healthy' : 'disabled'}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
