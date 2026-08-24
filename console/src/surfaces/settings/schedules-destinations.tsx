import type { ReactNode } from 'react';

import { Link } from '@/components/action';
import { resolveCta } from '@/design/empty-state';
import { message, type MessageKey } from '@/i18n/messages';
import { may } from '@/session/viewer';
import { SettingsPageHeader } from '@/shell/area';
import { settingsPageFor } from '@/shell/routes';
import type { SurfaceContext } from '../context';
import { AdvancedConfigSection } from '../advanced-config-section';
import { emptyBecause, readSetupState, setupCause } from '../emptiness';
import { INVESTIGATION_STEP } from '../first-run/plan';
import { panelLabels } from '../labels';
import { Panel, type PanelEmpty } from '../panel';
import {
  authorised,
  dataOf,
  dependencyOf,
  list,
  panelRead,
  read,
  stateOf,
  text,
} from '../read';
import { Resend } from '../resend';
import {
  Schedules,
  type ScheduleFrequency,
  type ScheduleRecord,
  type Weekday,
} from '../schedules';
import { placedTree } from '../tree';
import { readViewState, resolveNode, type FilterName } from '../url-state';
import { timestamp } from '@/i18n/format';

/**
 * Schedules & destinations: the investigations that run on a clock, and
 * where an alert ends up once it has one.
 *
 * Two mechanisms an operator checks for the same reason — "what runs without
 * a person starting it" — sharing one page for the same reason `data.tsx`
 * used to share the old Signals tabs with detection: they are both halves of
 * one pipe, and the pipe is what an operator is actually tracing when
 * something did or did not happen on schedule.
 *
 * **The Destinations CTA is the defect this feature exists to close.** The
 * empty state used to tell an operator to connect an integration "in the
 * catalogue" and then open the raw configuration editor when they pressed
 * the button — two different answers to "where do I fix this" on the same
 * screen. Every path through this file's empty state now resolves through
 * `resolveCta`, which is checked against the route manifest at the point it
 * is built rather than trusted as a string.
 */

const ID = 'settings-schedules-destinations';

/** The permission the gateway requires to re-send a failed delivery. */
const WRITE = 'config.write';

/** Who may see or change this team's scheduled investigations. */
const SCHEDULE_MANAGE = 'schedule.manage';

const DESTINATIONS_FILTERS: readonly FilterName[] = ['node'];

/**
 * The `transit` section is exactly two fields — `rules` and `destinations` —
 * so the shared advanced section's own path-prefix filter covers both with
 * no risk of also drawing a control for a field this page does not own.
 */
const TRANSIT_ADVANCED_PREFIX = 'transit.';

/**
 * The three `surfaces` fields this page owns — its own chat channels, report
 * destinations and notification sinks. Deliberately *not* the bare
 * `surfaces.` prefix: that would also reach `surfaces.notification_policy.*`
 * (owned by Notifications) and `surfaces.console.tutorial_dismissed` (a
 * machine field with no form by decision) — two fields this page does not
 * own and must not offer a second, competing control for.
 */
const SURFACES_DESTINATIONS_PREFIXES: readonly string[] = [
  'surfaces.channels',
  'surfaces.report_destinations',
  'surfaces.notification_sinks',
];

/**
 * The five list fields this page owns, named so the effective-value table can
 * show what each one resolves to and where it was set.
 *
 * Every one is an array the schema describes an entry shape for, so the
 * `ConfigEditor` inside the section draws it as an `ObjectList` — the same
 * control the raw editor used, on the page that owns the subject rather than
 * in a generic list of the whole schema.
 */
const TRANSIT_ADVANCED_FIELD_LIST: readonly {
  readonly path: string;
  readonly label: MessageKey;
}[] = [
  {
    path: 'transit.rules',
    label: 'settings.schedulesDestinations.advanced.field.transitRules',
  },
  {
    path: 'transit.destinations',
    label: 'settings.schedulesDestinations.advanced.field.transitDestinations',
  },
];

const SURFACES_ADVANCED_FIELD_LIST: readonly {
  readonly path: string;
  readonly label: MessageKey;
}[] = [
  {
    path: 'surfaces.channels',
    label: 'settings.schedulesDestinations.advanced.field.channels',
  },
  {
    path: 'surfaces.report_destinations',
    label: 'settings.schedulesDestinations.advanced.field.reportDestinations',
  },
  {
    path: 'surfaces.notification_sinks',
    label: 'settings.schedulesDestinations.advanced.field.notificationSinks',
  },
];

/** `data` read as a bare array, and an empty one when it is not. */
function rowsOf(data: unknown): readonly unknown[] {
  return Array.isArray(data) ? data : [];
}

/** Every frequency preset's own word, keyed the way `Schedules` expects. */
function frequencyOptions(
  locale: Parameters<typeof message>[0],
): Readonly<Record<ScheduleFrequency, string>> {
  return {
    custom: message(locale, 'schedules.create.frequency.custom'),
    daily: message(locale, 'schedules.create.frequency.daily'),
    weekdays: message(locale, 'schedules.create.frequency.weekdays'),
    weekly: message(locale, 'schedules.create.frequency.weekly'),
    monthly: message(locale, 'schedules.create.frequency.monthly'),
  };
}

/** Every weekday's own word, keyed the way `Schedules` expects. */
function weekdayOptions(
  locale: Parameters<typeof message>[0],
): Readonly<Record<Weekday, string>> {
  return {
    monday: message(locale, 'schedules.create.weekday.monday'),
    tuesday: message(locale, 'schedules.create.weekday.tuesday'),
    wednesday: message(locale, 'schedules.create.weekday.wednesday'),
    thursday: message(locale, 'schedules.create.weekday.thursday'),
    friday: message(locale, 'schedules.create.weekday.friday'),
    saturday: message(locale, 'schedules.create.weekday.saturday'),
    sunday: message(locale, 'schedules.create.weekday.sunday'),
  };
}

/** The scheduled-investigations half of the page — absent for a viewer who may not manage them. */
async function schedulesSection(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, now, viewer, zone } = context;
  const init = authorised(credential);

  if (!may(viewer, SCHEDULE_MANAGE)) return null;

  const schedules = await panelRead('/v1/schedules', () => read('/v1/schedules', init));
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
        enabled: Boolean(Reflect.get(Object(row), 'enabled')),
        nextRun: nextRunAt === '' ? null : timestamp(locale, nextRunAt, now, zone),
      };
    },
  );

  return (
    <Panel
      title={message(locale, 'schedules.title')}
      state={stateOf(schedules, false)}
      dependency={dependencyOf(schedules)}
      labels={panelLabels(locale, message(locale, 'schedules.title'))}
      empty={{
        heading: message(locale, 'schedules.empty.heading'),
        body: message(locale, 'schedules.empty.body'),
        actionLabel: message(locale, 'schedules.empty.action'),
        href: '#schedule-create',
      }}
    >
      <p className="text-meta text-muted mb-3">
        {message(locale, 'schedules.caption')}
      </p>

      {scheduleRecords.length === 0 ? (
        <div
          data-testid="schedules-empty"
          className="mb-4 flex flex-col items-start gap-1 rounded-2 edge border-border bg-sunken px-3 py-2 text-small"
        >
          <p className="text-strong">{message(locale, 'schedules.empty.heading')}</p>
          <p className="text-muted">{message(locale, 'schedules.empty.body')}</p>
          <Link href="#schedule-create">
            {message(locale, 'schedules.empty.action')}
          </Link>
        </div>
      ) : null}

      <div id="schedule-create">
        <Schedules
          schedules={scheduleRecords}
          viewer={viewer}
          locale={locale}
          zone={zone}
          now={now}
          labels={{
            column: {
              name: message(locale, 'schedules.column.name'),
              cron: message(locale, 'schedules.column.cron'),
              objective: message(locale, 'schedules.column.objective'),
              timezone: message(locale, 'schedules.column.timezone'),
              nextRun: message(locale, 'schedules.column.nextRun'),
              enabled: message(locale, 'schedules.column.enabled'),
            },
            // Templates, deliberately un-interpolated here: the clock and the
            // day are per row, and the catalogue is read once for the table.
            frequencyText: {
              daily: message(locale, 'schedules.frequency.daily'),
              weekdays: message(locale, 'schedules.frequency.weekdays'),
              weekly: message(locale, 'schedules.frequency.weekly'),
              monthly: message(locale, 'schedules.frequency.monthly'),
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
              help: {
                jobId: message(locale, 'schedules.create.jobIdHelp'),
                name: message(locale, 'schedules.create.nameHelp'),
                cron: message(locale, 'schedules.create.cronHelp'),
                objective: message(locale, 'schedules.create.objectiveHelp'),
                timezone: message(locale, 'schedules.create.timezoneHelp'),
              },
              frequency: message(locale, 'schedules.create.frequency'),
              frequencyHelp: message(locale, 'schedules.create.frequencyHelp'),
              frequencyOptions: frequencyOptions(locale),
              weekday: message(locale, 'schedules.create.weekday'),
              weekdayOptions: weekdayOptions(locale),
              time: message(locale, 'schedules.create.time'),
              name: message(locale, 'schedules.create.name'),
              cron: message(locale, 'schedules.create.cron'),
              objective: message(locale, 'schedules.create.objective'),
              timezone: message(locale, 'schedules.create.timezone'),
              submit: message(locale, 'schedules.create.submit'),
              submitting: message(locale, 'schedules.create.submitting'),
              created: message(locale, 'schedules.create.created'),
              previewing: message(locale, 'schedules.create.previewing'),
              previewLabel: message(locale, 'schedules.create.previewLabel'),
            },
            failed: message(locale, 'schedules.failed'),
            unreachable: message(locale, 'schedules.unreachable'),
          }}
        />
      </div>
    </Panel>
  );
}

/** The destinations half of the page: where a result goes, and why one cannot. */
async function destinationsSection(context: SurfaceContext): Promise<ReactNode> {
  const { credential, locale, viewer } = context;
  const init = authorised(credential);

  const [destinations, deliveries, setup] = await Promise.all([
    panelRead('/v1/transit/destinations', () => read('/v1/transit/destinations', init)),
    panelRead('/v1/transit/deliveries', () => read('/v1/transit/deliveries', init)),
    readSetupState(credential),
  ]);
  const cause = setupCause(locale, setup, INVESTIGATION_STEP);

  const destinationRows = list(dataOf(destinations), 'destinations');
  const ledger = rowsOf(dataOf(deliveries));
  const outboundRows = ledger.filter((row) => text(row, 'direction') === 'outbound');

  // Where the CTA contract applies: the catalogue, filtered to the category
  // that fixes it — never `view=`, which would exclude precisely the vendors
  // an operator with nothing connected needs to see.
  const catalogueCta = resolveCta({
    route: '/integrations',
    query: { category: 'communication' },
  });

  // The destination column already has a cause more specific than the setup
  // checklist when the deployment names one itself — which channel is missing
  // and where to add it — and that beats the generic "finish the setup"
  // sentence rather than being replaced by it.
  const unconfigurableReason = text(dataOf(destinations), 'unconfigurable_reason');
  const destinationsEmpty: PanelEmpty =
    unconfigurableReason === ''
      ? emptyBecause(
          {
            heading: message(locale, 'data.delivery.empty.heading'),
            body: message(locale, 'data.delivery.empty.body'),
            actionLabel: message(locale, 'data.delivery.empty.action'),
            href: '/configuration',
          },
          cause,
        )
      : {
          heading: message(locale, 'data.delivery.empty.heading'),
          body: unconfigurableReason,
          actionLabel: message(locale, 'data.delivery.unconfigurable.action'),
          href: catalogueCta.href,
        };

  return (
    <Panel
      title={message(locale, 'data.delivery.title')}
      state={stateOf(destinations, destinationRows.length === 0)}
      dependency={dependencyOf(destinations)}
      labels={panelLabels(locale, message(locale, 'data.delivery.title'))}
      empty={destinationsEmpty}
    >
      <ul className="flex flex-col gap-3" data-testid="destinations">
        {destinationRows.map((destination) => {
          const channel = text(destination, 'channel');
          const reason = text(destination, 'unconfigurable_reason');
          return (
            <li
              key={text(destination, 'destination_id')}
              data-testid="destination"
              data-destination={text(destination, 'destination_id')}
              className="flex flex-col gap-1"
            >
              <span className="text-small text-strong">
                {text(destination, 'destination_id')}
              </span>
              <span className="text-meta text-muted">
                {channel} · {text(destination, 'detail')}
              </span>
              <span className="text-meta text-muted" data-testid="destination-events">
                {list(destination, 'events')
                  .map((event) => String(event))
                  .join(', ')}
              </span>
              <span className="text-meta text-muted" data-testid="destination-masking">
                {message(locale, 'data.delivery.masking')}{' '}
                {text(destination, 'masking_policy')}
              </span>
              {reason === '' ? null : (
                <span className="flex flex-wrap items-center gap-2">
                  <span
                    className="text-meta text-danger"
                    data-testid="destination-unusable"
                  >
                    {reason}
                  </span>
                  {channel === '' ? null : (
                    <a
                      href={`/integrations/${encodeURIComponent(channel)}`}
                      data-testid="destination-credential-link"
                      className="text-accent underline underline-offset-2 motion-hover hover:opacity-80 text-meta"
                    >
                      {message(locale, 'data.delivery.unusable.link')}
                    </a>
                  )}
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <ul className="flex flex-col gap-2" data-testid="outbound-failures">
        {outboundRows
          .filter((row) => text(row, 'outcome') === 'failed')
          .map((row) => (
            <li
              key={text(row, 'delivery_id')}
              data-testid="failed-delivery"
              className="flex flex-col gap-1"
            >
              <span className="text-meta text-danger">
                {text(row, 'source')} — {text(row, 'reason')}
              </span>
              {may(viewer, WRITE) ? (
                <Resend
                  deliveryId={text(row, 'delivery_id')}
                  labels={{
                    resend: message(locale, 'data.delivery.resend'),
                    resending: message(locale, 'data.delivery.resending'),
                    delivered: message(locale, 'data.delivery.resent'),
                    failed: message(locale, 'data.delivery.resendFailed'),
                    unreachable: message(locale, 'data.simulate.unreachable'),
                  }}
                />
              ) : null}
            </li>
          ))}
      </ul>
    </Panel>
  );
}

/**
 * The two configuration-schema groups this page owns but had no control for:
 * the routing rules and delivery destinations `transit` declares, and the
 * chat channels, report destinations and notification sinks `surfaces`
 * declares. Both are arrays the schema describes an entry shape for, so the
 * same `ConfigEditor` every advanced section already uses draws them as an
 * `ObjectList` — add, remove, reorder — the moment a page scopes itself to
 * the right prefix. Collapsed by default, like every advanced section.
 *
 * Does its own read of `/v1/config`, `/v1/config/{node_id}` and (only when
 * writable) `/v1/config/{node_id}/fields`, exactly as every other advanced
 * section on this console already does — this page had none of that
 * machinery before, because everything else on it reads its own endpoint
 * (`/v1/schedules`, `/v1/transit/destinations`) rather than the
 * configuration document.
 */
async function advancedDestinationsSection(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { credential, locale, viewer, search } = context;
  const state = readViewState(search, DESTINATIONS_FILTERS);
  const init = authorised(credential);
  const configWritable = may(viewer, WRITE);

  const tree = await panelRead('/v1/config', () => read('/v1/config', init));
  const nodeId = resolveNode(state, viewer, placedTree(dataOf(tree)));

  const nothing = { status: 'ready' as const, data: {} as unknown };
  // Read regardless of `configWritable`: the advanced sections' own
  // effective-value tables show every viewer of this page what a field
  // resolves to, not only one who may change it.
  const configFields =
    nodeId === ''
      ? nothing
      : await panelRead<unknown>('/v1/config/{node_id}/fields', () =>
          read('/v1/config/{node_id}/fields', { ...init, params: { node_id: nodeId } }),
        );

  const named = (
    entries: readonly { readonly path: string; readonly label: MessageKey }[],
  ): readonly { readonly path: string; readonly label: string }[] =>
    entries.map(({ path, label }) => ({ path, label: message(locale, label) }));

  return (
    <div className="flex flex-col gap-3">
      <AdvancedConfigSection
        title={message(locale, 'settings.schedulesDestinations.advanced.transit.title')}
        prefix={TRANSIT_ADVANCED_PREFIX}
        nodeId={nodeId}
        locale={locale}
        writable={configWritable}
        fields={named(TRANSIT_ADVANCED_FIELD_LIST)}
        rawFields={dataOf(configFields)}
      />

      <AdvancedConfigSection
        title={message(
          locale,
          'settings.schedulesDestinations.advanced.surfaces.title',
        )}
        prefix={SURFACES_DESTINATIONS_PREFIXES}
        testId="advanced-config-surfaces-destinations"
        nodeId={nodeId}
        locale={locale}
        writable={configWritable}
        fields={named(SURFACES_ADVANCED_FIELD_LIST)}
        rawFields={dataOf(configFields)}
      />
    </div>
  );
}

/** The whole `/settings/schedules-destinations` page. */
export async function SchedulesDestinationsScreen(
  context: SurfaceContext,
): Promise<ReactNode> {
  const { locale } = context;
  return (
    <>
      <SettingsPageHeader page={settingsPageFor(ID)} locale={locale} />
      {await schedulesSection(context)}
      <div className="mt-4">{await destinationsSection(context)}</div>
      <div className="mt-5">{await advancedDestinationsSection(context)}</div>
    </>
  );
}
