import type { ReactNode } from 'react';

import { Badge, DetectorStateChip } from '@/components/status';
import { formatNumber, timestamp } from '@/i18n/format';
import { message } from '@/i18n/messages';
import type { SurfaceContext } from '../context';
import { DetectorControls } from '../detector-controls';
import {
  emptyBecause,
  firstCause,
  readSetupState,
  setupCause,
  watchingCause,
} from '../emptiness';
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
 * The "Continuous observation" tab of Signals: what is being watched for,
 * how well it is covered, and what it last found.
 *
 * Each row carries its own description rather than pointing at documentation:
 * the rationale for a threshold is what somebody needs at the moment they are
 * deciding whether the threshold is wrong, and a file they would have to go and
 * find is a file they will not.
 *
 * Coverage is the column that turns "this detector exists" into "this detector
 * is looking at 84 of 92 things", which are very different claims.
 *
 * **An empty table here is not "no source connected".** Sources answer before
 * a single detector ever appears — what is missing when this panel is empty
 * is the shipped detector set being switched on
 * (`policies.observation.guardian.enabled`), which is a single flag set in
 * Configuration. `watchingCause` already names that fact for screens
 * *downstream* of detection, such as Incidents, and sends them here to fix
 * it; reused verbatim on this tab it would send an operator back to the page
 * they are already reading, so its destination is rewritten to
 * Configuration, at the node this viewer holds. Checked after the setup
 * cause rather than before, unlike downstream screens: a deployment with an
 * unfinished checklist also reads as zero live detectors, and "turn on
 * continuous observation" is not the next step for somebody who has not
 * finished the wizard yet.
 *
 * The scheduled-investigation half of this file moved to the Settings
 * surface that absorbed it (`surfaces/settings/schedules-destinations.tsx`):
 * a recurring investigation runs on a clock rather than a detector, so it now
 * sits beside where its results end up rather than beside what watches the
 * estate on its own.
 */

/** The "Continuous observation" tab: what fires, and what covers it. */
export async function ObservationTab(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, viewer, zone } = context;
  const init = authorised(credential);

  const [detectors, setup] = await Promise.all([
    panelRead('/v1/detectors', () => read('/v1/detectors', init)),
    readSetupState(credential),
  ]);
  const records = list(dataOf(detectors), 'detectors');
  const liveDetectors = records.filter((record) => flag(record, 'enabled')).length;

  // Where the guardian toggle actually lives now: Alert intake's own advanced
  // section, which resolves the viewer's own node itself — the same node the
  // retired editor's fallback used to compute here by hand.
  const configurationHref = '/settings/alert-intake';
  const watching = watchingCause(locale, liveDetectors);
  const cause = firstCause(
    setupCause(locale, setup),
    watching === null ? null : { ...watching, href: configurationHref },
  );

  return (
    <Panel
      title={message(locale, 'detectors.list.title')}
      state={stateOf(detectors, records.length === 0)}
      dependency={dependencyOf(detectors)}
      labels={panelLabels(locale, message(locale, 'detectors.list.title'))}
      empty={emptyBecause(
        {
          heading: message(locale, 'detectors.empty.heading'),
          body: message(locale, 'detectors.empty.body'),
          actionLabel: message(locale, 'detectors.empty.action'),
          href: configurationHref,
        },
        cause,
      )}
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
                      <DetectorStateChip
                        locale={locale}
                        enabled={flag(record, 'enabled')}
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
                          unreachable: message(locale, 'detectors.control.unreachable'),
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
  );
}
