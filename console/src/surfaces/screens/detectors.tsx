import type { ReactNode } from 'react';

import { Badge } from '@/components/status';
import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { AreaHeader } from '@/shell/area';
import { areaFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { DetectorControls } from '../detector-controls';
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
  type PanelData,
} from '../read';
import { Schedules, type ScheduleRecord } from '../schedules';

/**
 * What is being watched for, how well it is covered, and what it last found —
 * and, beside it, what is watched for on a clock rather than by a detector.
 *
 * Each row carries its own description rather than pointing at documentation:
 * the rationale for a threshold is what somebody needs at the moment they are
 * deciding whether the threshold is wrong, and a file they would have to go and
 * find is a file they will not.
 *
 * Coverage is the column that turns "this detector exists" into "this detector
 * is looking at 84 of 92 things", which are very different claims.
 *
 * A scheduled investigation belongs on this screen rather than in an area of
 * its own: it is the other mechanism by which something runs without a person
 * starting it, and an operator checking what is watching this team's estate
 * should not have to know which of the two produced a given entry.
 *
 * `GET /v1/schedules` itself takes `schedule.manage` — there is no read-only
 * view of a schedule — so the whole panel, not only its writes, is fetched and
 * shown only for a viewer who holds it. Absent, not disabled.
 */

/** Who may see or change this team's scheduled investigations. */
const SCHEDULE_MANAGE = 'schedule.manage';

/** `data` read as a bare array, and an empty one when it is not. */
function rowsOf(data: unknown): readonly unknown[] {
  return Array.isArray(data) ? data : [];
}

export async function DetectorsScreen(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, viewer, zone } = context;
  const init = authorised(credential);

  const detectors = await panelRead('/v1/detectors', () => read('/v1/detectors', init));
  const records = list(dataOf(detectors), 'detectors');

  const canManageSchedules = may(viewer, SCHEDULE_MANAGE);
  const schedules: PanelData<unknown> = canManageSchedules
    ? await panelRead('/v1/schedules', () => read('/v1/schedules', init))
    : { status: 'ready', data: [] };
  const scheduleRows = rowsOf(dataOf(schedules));
  const scheduleRecords: readonly ScheduleRecord[] = scheduleRows.map(
    (row): ScheduleRecord => {
      const nextRunAt = text(row, 'next_run_at');
      return {
        jobId: text(row, 'job_id'),
        name: text(row, 'name'),
        cron: text(row, 'cron'),
        objective: text(row, 'objective'),
        timezone: text(row, 'timezone'),
        enabled: flag(row, 'enabled'),
        nextRun: nextRunAt === '' ? null : timestamp(locale, nextRunAt, now, zone),
      };
    },
  );

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
                      <div className="flex flex-col items-start gap-2">
                        <Badge
                          status={flag(record, 'enabled') ? 'healthy' : 'disabled'}
                        />
                        <DetectorControls
                          detectorId={text(record, 'detector_id')}
                          enabled={flag(record, 'enabled')}
                          viewer={viewer}
                          labels={{
                            dryRun: message(locale, 'detectors.control.dryRun'),
                            dryRunning: message(locale, 'detectors.control.dryRunning'),
                            wouldFire: message(locale, 'detectors.control.wouldFire'),
                            wouldNotFire: message(
                              locale,
                              'detectors.control.wouldNotFire',
                            ),
                            observations: message(
                              locale,
                              'detectors.control.observations',
                            ),
                            noObservations: message(
                              locale,
                              'detectors.control.noObservations',
                            ),
                            enable: message(locale, 'detectors.control.enable'),
                            enabling: message(locale, 'detectors.control.enabling'),
                            disable: message(locale, 'detectors.control.disable'),
                            disabling: message(locale, 'detectors.control.disabling'),
                            cancel: message(locale, 'detectors.control.cancel'),
                            failed: message(locale, 'detectors.control.failed'),
                            unreachable: message(
                              locale,
                              'detectors.control.unreachable',
                            ),
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Panel>

      {canManageSchedules ? (
        <div className="mt-5">
          <Panel
            title={message(locale, 'schedules.title')}
            state={stateOf(schedules, false)}
            dependency={dependencyOf(schedules)}
            labels={panelLabels(locale, message(locale, 'schedules.title'))}
            empty={{
              heading: message(locale, 'schedules.empty.heading'),
              body: message(locale, 'schedules.empty.body'),
              actionLabel: message(locale, 'schedules.empty.action'),
              href: '/detectors',
            }}
          >
            <Schedules
              schedules={scheduleRecords}
              viewer={viewer}
              labels={{
                column: {
                  name: message(locale, 'schedules.column.name'),
                  cron: message(locale, 'schedules.column.cron'),
                  objective: message(locale, 'schedules.column.objective'),
                  timezone: message(locale, 'schedules.column.timezone'),
                  nextRun: message(locale, 'schedules.column.nextRun'),
                  enabled: message(locale, 'schedules.column.enabled'),
                },
                never: message(locale, 'schedules.never'),
                enable: message(locale, 'schedules.enable'),
                enabling: message(locale, 'schedules.enabling'),
                disable: message(locale, 'schedules.disable'),
                disabling: message(locale, 'schedules.disabling'),
                save: message(locale, 'schedules.save'),
                saving: message(locale, 'schedules.saving'),
                delete: message(locale, 'schedules.delete'),
                deleteConsequence: message(locale, 'schedules.deleteConsequence'),
                deleteCancel: message(locale, 'schedules.deleteCancel'),
                deleteClose: message(locale, 'schedules.deleteClose'),
                create: {
                  title: message(locale, 'schedules.create.title'),
                  jobId: message(locale, 'schedules.create.jobId'),
                  name: message(locale, 'schedules.create.name'),
                  cron: message(locale, 'schedules.create.cron'),
                  objective: message(locale, 'schedules.create.objective'),
                  timezone: message(locale, 'schedules.create.timezone'),
                  submit: message(locale, 'schedules.create.submit'),
                  submitting: message(locale, 'schedules.create.submitting'),
                },
                failed: message(locale, 'schedules.failed'),
                unreachable: message(locale, 'schedules.unreachable'),
              }}
            />
          </Panel>
        </div>
      ) : null}
    </>
  );
}
